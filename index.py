import io
import json
import logging
import os

import boto3
import telebot
from yandex_music import Client
from yandex_music.exceptions import InvalidBitrateError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TG_TOKEN = os.environ["TG_TOKEN"]
YM_TOKEN = os.environ["YM_TOKEN"]
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")

_ym_client: Client | None = None
_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None and S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY:
        _s3_client = boto3.client(
            "s3",
            endpoint_url="https://storage.yandexcloud.net",
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name="ru-central1",
        )
    return _s3_client


def _save_to_s3(key: str, data: bytes) -> None:
    s3 = _get_s3()
    if s3 is None:
        return
    try:
        s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType="audio/mpeg")
    except Exception:
        logger.exception("Failed to save track to S3: %s", key)


def _get_ym_client() -> Client:
    global _ym_client
    if _ym_client is None:
        _ym_client = Client(YM_TOKEN).init()
    return _ym_client


def _search_and_send(bot: telebot.TeleBot, chat_id: int, query: str) -> None:
    client = _get_ym_client()

    result = client.search(query, type_="track")
    if not result or not result.tracks or not result.tracks.results:
        bot.send_message(chat_id, "Ничего не нашёл 😔")
        return

    track = result.tracks.results[0]

    if not track.available:
        bot.send_message(chat_id, f"Трек «{track.title}» недоступен в вашем регионе.")
        return

    artists = ", ".join(a.name for a in (track.artists or []))
    caption = f"🎵 {artists} — {track.title}" if artists else f"🎵 {track.title}"

    audio_bytes: bytes | None = None
    try:
        audio_bytes = track.download_bytes(codec="mp3", bitrate_in_kbps=192)
    except (InvalidBitrateError, Exception):
        infos = track.get_download_info()
        if not infos:
            bot.send_message(chat_id, f"Не удалось скачать «{track.title}».")
            return
        mp3_infos = [i for i in infos if i.codec == "mp3"]
        info = max(mp3_infos, key=lambda i: i.bitrate_in_kbps) if mp3_infos else infos[0]
        audio_bytes = info.download_bytes()

    if not audio_bytes:
        bot.send_message(chat_id, f"Не удалось скачать «{track.title}».")
        return

    s3_key = f"{artists} — {track.title}.mp3" if artists else f"{track.title}.mp3"
    _save_to_s3(s3_key, audio_bytes)

    duration = track.duration_ms // 1000 if track.duration_ms else None
    performer = artists or None
    title = track.title

    bot.send_audio(
        chat_id,
        audio=io.BytesIO(audio_bytes),
        caption=caption,
        duration=duration,
        performer=performer,
        title=title,
    )


def handler(event: dict, context) -> dict:
    try:
        body_raw = event.get("body", "{}")
        if event.get("isBase64Encoded"):
            import base64
            body_raw = base64.b64decode(body_raw).decode("utf-8")

        update_data = json.loads(body_raw)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to parse body: %s", e)
        return {"statusCode": 200, "body": "ok"}

    bot = telebot.TeleBot(TG_TOKEN, threaded=False)

    message = update_data.get("message") or update_data.get("edited_message")
    if not message:
        return {"statusCode": 200, "body": "ok"}

    chat_id: int = message["chat"]["id"]
    text: str = message.get("text", "").strip()

    if not text:
        return {"statusCode": 200, "body": "ok"}

    if text.startswith("/start") or text.startswith("/help"):
        bot.send_message(
            chat_id,
            "Привет! Отправь мне название трека или «Исполнитель — Трек», и я пришлю MP3.",
        )
        return {"statusCode": 200, "body": "ok"}

    if text.startswith("/"):
        return {"statusCode": 200, "body": "ok"}

    try:
        _search_and_send(bot, chat_id, text)
    except Exception as e:
        logger.exception("Error while processing query %r: %s", text, e)
        bot.send_message(chat_id, "Произошла ошибка. Попробуй ещё раз.")

    return {"statusCode": 200, "body": "ok"}
