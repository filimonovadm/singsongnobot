# singsongnobot — Agent Context

Telegram-бот @singsongnobot («Просто песня»). Принимает текстовый запрос,
ищет трек в Яндекс Музыке, скачивает MP3 и отправляет в чат. Сохраняет
в S3 после каждой отдачи.

## Инфраструктура

| Ресурс | Значение |
|--------|----------|
| Telegram bot | @singsongnobot, token в `TG_TOKEN` (GitHub Secret) |
| YCF function | `d4e9drfr7vr5ubmg9nnk` |
| YC folder | `b1g7scs6lgrf9ijk4dff` |
| YC cloud | `b1g0og5epa4gl51a0d7f` |
| S3 bucket tracks | `singsongnobot-tracks` |
| S3 bucket tfstate | `singsongnobot-tfstate` |
| GitHub repo | https://github.com/filimonovadm/singsongnobot |
| SA deploy | `ajearql5kugafb67p02n` (singsongnobot-deploy), роль serverless.functions.admin |
| SA storage | `ajev12nglllf4g6gdlm0` (singsongnobot-storage), роль storage.editor |

Bucket и SA storage **управляются вне Terraform** (созданы вручную через yc CLI).

## GitHub Secrets

`TG_TOKEN`, `YM_TOKEN`, `YC_SA_KEY`, `YC_FOLDER_ID`, `YC_FUNCTION_ID`,
`TF_SA_KEY`, `TF_S3_ACCESS_KEY`, `TF_S3_SECRET_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`

## Структура проекта

```
index.py          — YCF handler (единственный точка входа)
requirements.txt  — зависимости: pyTelegramBotAPI, yandex-music, requests, boto3
terraform/
  main.tf         — YCF function + IAM public invoke binding, S3 backend
  variables.tf    — folder_id, tg_token, ym_token, sa_key_file, s3_access_key, s3_secret_key
  outputs.tf      — function_id, invoke_url, tracks_bucket
.github/workflows/deploy.yml  — terraform apply при push в master
```

## Поток данных в index.py

```
handler(event) → parse Telegram update → _search_and_send()
  → _get_ym_client() [синглтон]
  → client.search(query, type_='track')
  → track.download_bytes(codec='mp3', bitrate_in_kbps=192)
       ↳ fallback: get_download_info() → max bitrate mp3
  → _save_to_s3(key, bytes) [синглтон S3 client]
  → bot.send_audio(chat_id, audio=BytesIO(...), ...)
```

## Env vars в функции (задаются через Terraform)

| Переменная | Откуда |
|------------|--------|
| `TG_TOKEN` | GitHub Secret → TF_VAR |
| `YM_TOKEN` | GitHub Secret → TF_VAR |
| `S3_BUCKET` | литерал `"singsongnobot-tracks"` в main.tf |
| `S3_ACCESS_KEY` | GitHub Secret → TF_VAR |
| `S3_SECRET_KEY` | GitHub Secret → TF_VAR |

## Deploy

Push в `master` → GitHub Actions → `terraform apply` → новая версия YCF.
Webhook установлен на `https://functions.yandexcloud.net/d4e9drfr7vr5ubmg9nnk`.

## Токены и аутентификация

- **YM OAuth token** формата `y0_...` — получен через Device Flow
  (`Client().request_device_code()` → подтверждение на ya.ru/device)
- **Session_id** (`.yandex.ru`) — HttpOnly cookie, для прямых API-запросов
- YCF runtime: `python312`, 512 MB, timeout 25s

## Правила кода

Применяется `.opencode/rules/python-formatting.md`:
- Одинарные кавычки для строковых литералов
- Макс. 79 символов на строку
- Двойной отступ в `def`-аргументах (PEP 8 E131)
- Comprehension с `if` — всегда многострочный
- Логирование через `%`, не f-string

## Яндекс Музыка API (yandex-music==2.2.0)

```python
client = Client(token).init()
result = client.search(query, type_='track')
track = result.tracks.results[0]
audio_bytes = track.download_bytes(codec='mp3', bitrate_in_kbps=192)
# fallback:
infos = track.get_download_info()
info = max([i for i in infos if i.codec == 'mp3'], key=lambda i: i.bitrate_in_kbps)
audio_bytes = info.download_bytes()
```

## YC CLI — полезные команды

```bash
# Посмотреть логи функции
yc serverless function logs d4e9drfr7vr5ubmg9nnk --follow

# Список объектов в S3
yc storage s3api list-objects --bucket singsongnobot-tracks

# Вызвать функцию вручную
yc serverless function invoke d4e9drfr7vr5ubmg9nnk --data '{...}'
```
