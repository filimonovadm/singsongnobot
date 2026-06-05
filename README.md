<p align="center">
  <img src="avatar.png" width="160" alt="Просто песня">
</p>

<h1 align="center">Просто песня</h1>

<p align="center">
  <a href="https://t.me/singsongnobot">@singsongnobot</a>
</p>

---

Напиши боту что хочешь услышать — он найдёт несколько вариантов, ты выберешь нужный, и через секунду MP3 уже у тебя.

Вот и всё.

---

## Архитектура доставки апдейтов

Бот живёт в Yandex Cloud Function. Telegram доставляет апдейты не напрямую
в функцию, а через промежуточный прокси:

```
Telegram  ──►  прокси  ──►  functions.yandexcloud.net
```

Прямой маршрут от инфраструктуры Telegram до Yandex Cloud деградировал:
входящие соединения упираются в таймаут на TCP-handshake. Прокси доступен
и для Telegram, и для Yandex Cloud, поэтому доставка снова работает.

Бот ничего не знает про прокси. Меняется только webhook URL на стороне
Telegram (через `setWebhook`). Исходящие ответы бота (`send_audio`) идут из
Yandex Cloud напрямую в Telegram — этот маршрут стабилен и прокси не требует.

Webhook URL хранится только на серверах Telegram (привязан к токену бота),
в коде и инфраструктуре его нет. Прочитать текущее состояние:

```bash
curl "https://api.telegram.org/bot$TG_TOKEN/getWebhookInfo"
```

Адрес прокси и скрипт восстановления webhook не хранятся в репозитории —
это детали приватной инфраструктуры.
