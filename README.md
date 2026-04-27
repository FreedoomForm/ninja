# 🥷 Ninja Userbot

**Telegram Userbot** с AI автоответчиком (Mistral AI) и поддержкой изображений.

## Что это?

Это **юзербот** — работает как ВАШ Telegram аккаунт, а не как бот.

- Автоответ на личные сообщения
- **AI видит историю переписки (контекст) — последние 20 сообщений**
- **Поддержка изображений через Mistral Vision API**
- Веб UI для управления

## Новое! Vision Edition

Теперь AI может обрабатывать изображения:
- 📷 Автоматическое распознавание и описание изображений
- 🖼️ AI отвечает в контексте полученных картинок
- 🔄 История включает как текст, так и изображения (последние 20 сообщений)

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
4. Выберите модели:
   - **Vision Model** — для обработки изображений (Pixtral 12B рекомендуется)
   - **Text Model** — для текстовых сообщений (Mistral Medium)
5. Нажмите **Запустить**
6. При первом запуске введите номер телефона и код подтверждения в терминале

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
                                     [Mistral AI Vision]
```

Когда кто-то пишет вам в личку:
1. Telethon получает сообщение (текст и/или изображение)
2. Сообщение + история переписки (до 20 сообщений) отправляются в Mistral AI
   - Если есть изображение → используется Pixtral (Vision Model)
   - Если только текст → используется Mistral (Text Model)
3. AI генерирует ответ с учётом контекста
4. Telethon отправляет ответ от вашего имени

## API Endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/status` | GET | Статус бота |
| `/api/config` | GET/POST | Конфигурация |
| `/api/start` | POST | Запустить бота |
| `/api/stop` | POST | Остановить бота |
| `/api/logs` | GET/DELETE | Логи сообщений |
| `/api/history/{chat_id}` | GET | История чата из Telegram |
| `/api/conversation/{chat_id}` | GET | Контекст переписки в памяти |

## Модели Mistral AI

### Vision Models (для изображений)
- **pixtral-12b-2409** — рекомендуется, быстрый и точный
- **pixtral-large-latest** — более мощный, но медленнее

### Text Models (для текста)
- **mistral-medium-latest** — оптимальный баланс
- **mistral-small-latest** — быстрый, для простых ответов
- **mistral-large-latest** — самый умный

## Безопасность

- Сессия хранится локально в `~/.ninja-data/`
- Изображения временно скачиваются и удаляются после обработки
- Никому не давайте API ID, API Hash и файлы сессии
- Юзербот имеет полный доступ к вашему аккаунту

## Требования

- Python 3.9+
- Telegram аккаунт
- Mistral AI API ключ
