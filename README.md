# 🥷 Ninja Userbot

**Telegram Userbot** с AI автоответчиком (Mistral AI).

## Что это?

Это **юзербот** — работает как ВАШ Telegram аккаунт, а не как бот.

- Автоответ на личные сообщения
- AI видит историю переписки (контекст)
- Веб UI для управления

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/FreedoomForm/ninja.git
cd ninja

# Запустить
./run.sh
```

Или вручную:

```bash
cd app
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

## Использование

1. Откройте `app/web/index.html` в браузере
2. Введите API ID и Hash с [my.telegram.org](https://my.telegram.org)
3. Введите Mistral API Key с [console.mistral.ai](https://console.mistral.ai)
4. Нажмите **Запустить**
5. При первом запуске введите номер телефона и код подтверждения в терминале

## Файлы

```
ninja/
├── app/
│   ├── main.py           # Python backend (FastAPI + Telethon)
│   ├── requirements.txt  # Зависимости
│   └── web/
│       └── index.html    # Веб UI
├── run.sh                # Скрипт запуска
└── README.md
```

## Как это работает

```
[Браузер] <---> [FastAPI :3030] <---> [Telethon] <---> [Telegram]
                                     [Mistral AI]
```

Когда кто-то пишет вам в личку:
1. Telethon получает сообщение
2. Сообщение + история переписки отправляются в Mistral AI
3. AI генерирует ответ
4. Telethon отправляет ответ от вашего имени

## Безопасность

- Сессия хранится локально в `~/.ninja-data/`
- Никому не давайте API ID, API Hash и файлы сессии
- Юзербот имеет полный доступ к вашему аккаунту
