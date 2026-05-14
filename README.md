# 🥷 Ninja Userbot - Standalone Windows EXE

**Telegram Userbot** с AI автоответчиком для Sog'lom taom. Один EXE файл - без внешних зависимостей!

## Особенности

- 🤖 **AI автоответчик** - отвечает как реальный сотрудник
- 🖼️ **Распознавание изображений** - чеки, стикеры через Mistral Vision
- 📍 **Геолокация** - обработка координат клиентов
- 📱 **Нативный Windows UI** - без браузера, без веб-сервера
- ⚡ **Один EXE файл** - ничего больше не нужно!

## Быстрый старт

1. **Скачайте** `Ninja.exe` из Releases
2. **Запустите** EXE файл
3. **Настройте**:
   - API ID и API Hash с [my.telegram.org](https://my.telegram.org)
   - Mistral API Key с [console.mistral.ai](https://console.mistral.ai) (бесплатно)
4. **Войдите** в Telegram (телефон + код)
5. **Запустите бота**

## Требования

- Windows 10/11
- Telegram аккаунт
- Mistral API ключ (бесплатный на console.mistral.ai)

## Как работает

```
[Telegram сообщение] → [Ninja.exe] → [Mistral AI] → [Ответ клиенту]
                           ↓
                    [Vision API] (если изображение)
```

## AI отвечает как Бахром

Сотрудник компании Sog'lom taom:
- Знает цены и калории
- Говорит на русском и узбекском
- Обрабатывает чеки и локации
- Вежливый и профессиональный

## Цены

| Калории | Цена |
|---------|------|
| 1000-1200 | 84,000 сум |
| 1400-1600 | 98,000 сум |
| 1800-2000 | 112,000 сум |
| 2200-2500 | 126,000 сум |

## Безопасность

- Данные хранятся в `%LOCALAPPDATA%\Ninja\`
- Сессия Telegram локальная
- Не передавайте API ключи третьим лицам

## Для разработчиков

### Сборка из исходников

```bash
git clone https://github.com/FreedoomForm/ninja.git
cd ninja/app
pip install -r requirements.txt
python ninja_gui.py
```

### Создание EXE

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name Ninja ninja_gui.py
```

## Лицензия

MIT
