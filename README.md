# 🥷 Ninja Bot

**Native Windows desktop application** for Telegram auto-reply using Mistral AI.

## Features

- ✅ **Native Windows App** - No browser, no console, just a desktop window
- ✅ **Telegram Userbot** - Auto-replies to private messages as your account
- ✅ **Mistral AI** - Smart AI responses
- ✅ **Portable EXE** - No installation required

## Download

Download `NinjaBot.exe` from [Releases](https://github.com/FreedoomForm/ninja/releases/latest)

## Usage

1. Run `NinjaBot.exe`
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

- **Electron** - Native desktop application
- **GramJS** - Telegram client for Node.js
- **Mistral AI** - AI responses

## Build from Source

```bash
cd desktop-app
npm install
npm run build
```

The portable EXE will be in `desktop-app/dist/NinjaBot.exe`
