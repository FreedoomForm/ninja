# 🥷 Ninja Bot

**Native Windows desktop application** for Telegram auto-reply using Mistral AI.

## Features

- ✅ **Native Windows App** - No browser, no console, just a desktop window
- ✅ **Telegram Userbot** - Auto-replies to private messages as your account
- ✅ **Mistral AI** - Smart AI responses
- ✅ **Portable EXE** - No installation required

## Download

Download `ninja.exe` from [Releases](https://github.com/FreedoomForm/ninja/releases/latest)

## Usage

1. Run `ninja.exe`
2. Enter your Telegram API credentials (get from [my.telegram.org](https://my.telegram.org))
3. Enter your Mistral API key (get from [console.mistral.ai](https://console.mistral.ai))
4. Click **Start Bot**
5. On first run, enter your phone number and verification code
6. The bot will auto-reply to messages using AI!

## Configuration

| Setting | Description |
|---------|-------------|
| API ID | Telegram API ID from my.telegram.org |
| API Hash | Telegram API Hash from my.telegram.org |
| Mistral Key | API key from console.mistral.ai |
| Mistral Model | AI model to use (default: mistral-medium-latest) |
| System Prompt | Instructions for the AI |

## Tech Stack

- **Python + Eel** - Native desktop application (Chrome app mode)
- **Telethon** - Telegram client for Python
- **Mistral AI** - AI responses

## Build from Source

### Prerequisites
- Python 3.11+
- PyInstaller: `pip install pyinstaller`

### Build EXE

```bash
cd ninja/bootstrap
pyinstaller --onefile --noconsole --name ninja launcher.py
```

The portable EXE will be in `dist/ninja.exe`

### Directory Structure

```
ninja/
├── bootstrap/
│   └── launcher.py      # Entry point (compiled to ninja.exe)
├── app/
│   ├── main.py          # Main application
│   ├── requirements.txt # Python dependencies
│   └── web/
│       └── index.html   # UI
└── README.md
```

## How it Works

1. `ninja.exe` (launcher.py compiled with PyInstaller) starts first
2. It downloads embedded Python to `%LOCALAPPDATA%\Ninja\python\`
3. Installs dependencies (telethon, eel, httpx, setuptools)
4. Downloads the latest `main.py` and `web/index.html` from GitHub
5. Launches the app with `CREATE_NO_WINDOW` flag (no console)

## Troubleshooting

### App won't start
- Check `%LOCALAPPDATA%\Ninja\launcher.log` for errors
- Check `%LOCALAPPDATA%\Ninja\install.log` for installation errors
- Delete `%LOCALAPPDATA%\Ninja\.installed` to force reinstall

### Login issues
- Make sure API ID and Hash are correct
- Check `%LOCALAPPDATA%\Ninja\debug.log` for details

### pkg_resources error
- The launcher should install setuptools automatically
- If it fails, manually run:
  ```
  %LOCALAPPDATA%\Ninja\python\python.exe -m pip install setuptools
  ```
