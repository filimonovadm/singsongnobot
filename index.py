import io
import json
import logging
import os

import boto3
import telebot
from telebot import types
from yandex_music import Client
from yandex_music.exceptions import InvalidBitrateError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TG_TOKEN = os.environ['TG_TOKEN']
YM_TOKEN = os.environ['YM_TOKEN']
S3_BUCKET = os.environ.get('S3_BUCKET')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')

_ym_client: Client | None = None
_s3_client = None

MAX_RESULTS = 5


def _get_s3():
    global _s3_client
    if _s3_client is None and S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY:
        _s3_client = boto3.client(
            's3',
            endpoint_url='https://storage.yandexcloud.net',
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name='ru-central1',
        )
    return _s3_client


def _save_to_s3(key: str, data: bytes) -> None:
    s3 = _get_s3()
    if s3 is None:
        return
    try:
        s3.put_object(
            Bucket=S3_BUCKET, Key=key, Body=data, ContentType='audio/mpeg')
    except Exception:
        logger.exception('Failed to save track to S3: %s', key)


def _get_ym_client() -> Client:
    global _ym_client
    if _ym_client is None:
        _ym_client = Client(YM_TOKEN).init()
    return _ym_client


def _track_label(track) -> str:
    artists = ', '.join(a.name for a in (track.artists or []))
    return f'{artists} — {track.title}' if artists else track.title


def _send_track_list(
        bot: telebot.TeleBot, chat_id: int, query: str) -> None:
    client = _get_ym_client()

    result = client.search(query, type_='track')
    if not result or not result.tracks or not result.tracks.results:
        bot.send_message(chat_id, 'Ничего не нашёл 😔')
        return

    tracks = result.tracks.results[:MAX_RESULTS]

    keyboard = types.InlineKeyboardMarkup()
    for track in tracks:
        label = _track_label(track)
        keyboard.add(types.InlineKeyboardButton(
            text=label,
            callback_data=str(track.id),
        ))

    bot.send_message(
        chat_id,
        f'Нашёл {len(tracks)} трека(-ов). Выбери:',
        reply_markup=keyboard,
    )


def _download_and_send(
        bot: telebot.TeleBot,
        chat_id: int,
        track_id: int,
        message_id: int) -> None:
    client = _get_ym_client()

    tracks = client.tracks([track_id])
    if not tracks:
        bot.send_message(chat_id, 'Трек не найден.')
        return

    track = tracks[0]

    if not track.available:
        bot.send_message(
            chat_id,
            f'Трек «{track.title}» недоступен в вашем регионе.',
        )
        return

    artists = ', '.join(a.name for a in (track.artists or []))
    if artists:
        caption = f'🎵 {artists} — {track.title}'
    else:
        caption = f'🎵 {track.title}'

    audio_bytes: bytes | None = None
    try:
        audio_bytes = track.download_bytes(codec='mp3', bitrate_in_kbps=192)
    except (InvalidBitrateError, Exception):
        infos = track.get_download_info()
        if not infos:
            bot.send_message(
                chat_id, f'Не удалось скачать «{track.title}».')
            return
        mp3_infos = [
            i for i in infos
            if i.codec == 'mp3'
        ]
        info = (
            max(mp3_infos, key=lambda i: i.bitrate_in_kbps)
            if mp3_infos else infos[0]
        )
        audio_bytes = info.download_bytes()

    if not audio_bytes:
        bot.send_message(
            chat_id, f'Не удалось скачать «{track.title}».')
        return

    if artists:
        s3_key = f'{artists} — {track.title}.mp3'
    else:
        s3_key = f'{track.title}.mp3'
    _save_to_s3(s3_key, audio_bytes)

    duration = track.duration_ms // 1000 if track.duration_ms else None
    performer = artists or None

    try:
        bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception:
        pass

    bot.send_audio(
        chat_id,
        audio=io.BytesIO(audio_bytes),
        caption=caption,
        duration=duration,
        performer=performer,
        title=track.title,
    )


def handler(event: dict, context) -> dict:
    try:
        body_raw = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_raw = base64.b64decode(body_raw).decode('utf-8')

        update_data = json.loads(body_raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.error('Failed to parse body: %s', e)
        return {'statusCode': 200, 'body': 'ok'}

    bot = telebot.TeleBot(TG_TOKEN, threaded=False)

    # callback_query — пользователь нажал кнопку с треком
    callback = update_data.get('callback_query')
    if callback:
        callback_id = callback.get('id')
        chat_id = callback['message']['chat']['id']
        message_id = callback['message']['message_id']
        track_id_str = callback.get('data', '')

        try:
            bot.answer_callback_query(callback_id)
        except Exception:
            pass

        if track_id_str.isdigit():
            try:
                bot.send_chat_action(chat_id, 'upload_document')
            except Exception:
                pass
            try:
                _download_and_send(
                    bot, chat_id, int(track_id_str), message_id)
            except Exception as e:
                logger.exception(
                    'Error downloading track %s: %s', track_id_str, e)
                try:
                    bot.send_message(
                        chat_id, 'Произошла ошибка. Попробуй ещё раз.')
                except Exception:
                    pass

        return {'statusCode': 200, 'body': 'ok'}

    # message — текстовый запрос
    message = update_data.get('message') or update_data.get('edited_message')
    if not message:
        return {'statusCode': 200, 'body': 'ok'}

    chat_id: int = message['chat']['id']
    text: str = message.get('text', '').strip()

    if not text:
        return {'statusCode': 200, 'body': 'ok'}

    if text.startswith('/start') or text.startswith('/help'):
        try:
            bot.send_message(
                chat_id,
                'Привет! Отправь название трека или «Исполнитель — Трек»,'
                ' и я пришлю список для выбора.',
            )
        except Exception:
            pass
        return {'statusCode': 200, 'body': 'ok'}

    if text.startswith('/'):
        return {'statusCode': 200, 'body': 'ok'}

    try:
        bot.send_chat_action(chat_id, 'typing')
    except Exception:
        pass

    try:
        _send_track_list(bot, chat_id, text)
    except Exception as e:
        logger.exception('Error while processing query %r: %s', text, e)
        try:
            bot.send_message(
                chat_id, 'Произошла ошибка. Попробуй ещё раз.')
        except Exception:
            pass

    return {'statusCode': 200, 'body': 'ok'}
