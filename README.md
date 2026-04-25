# Ninja — Telegram Auto-Reply for Windows

A tiny `ninja.exe` (built automatically by GitHub Actions) that, on first
launch, downloads embedded Python + the backend script and starts
auto-replying to your Telegram private messages with **Mistral AI**.

Inspired by [`chigwell/telegram-mcp`](https://github.com/chigwell/telegram-mcp);
uses [Telethon](https://docs.telethon.dev/) under the hood.

---

## 🖥️ Desktop App (NEW!)

Native Windows application with beautiful UI:

```
ninja/desktop-app/
├── main.js        # Electron main process
├── preload.js     # Secure IPC bridge
├── renderer.js    # UI logic
├── index.html     # Main UI
├── styles.css     # Styling
└── package.json   # Dependencies
```

### Build Desktop App:

```powershell
cd ninja/desktop-app
npm install
npm run build
```

This creates `Ninja Bot Setup.exe` installer in `dist/` folder.

### Features:
- 🎮 Control Tab: Start/Stop bot
- ⚙️ Settings Tab: Configure API keys
- 📋 Logs Tab: View message history
- 🎨 Modern dark theme UI

---

## How it works

```
ninja.exe  ──first run──►  %LOCALAPPDATA%\Ninja\
                              ├── python\          (embeddable Python 3.11)
                              ├── app\
                              │     ├── main.py
                              │     └── requirements.txt
                              └── .installed
```

1. **`ninja.exe`** is a ~7 MB PyInstaller bootstrap (`bootstrap/launcher.py`).
2. On first launch it downloads:
   - Embeddable Python 3.11
   - `pip`
   - `app/main.py` + `app/requirements.txt` from this repo (`raw.githubusercontent.com`)
   - Telethon + httpx + flask + flask-cors
3. It then runs `main.py`, which:
   - Starts Flask web server on port 58765
   - Logs you into Telegram (interactive on first run — phone + code)
   - Listens for incoming **private** messages
   - Sends them to Mistral and replies automatically
   - Keeps a small per-chat memory so conversations make sense

Subsequent launches reuse the same install and the saved session.

---

## Get the EXE

After every push to `main`, GitHub Actions builds `ninja.exe` and attaches
it to the rolling **`latest`** release:

➡️ <https://github.com/FreedoomForm/ninja/releases/latest>

Download `ninja.exe` and double-click. The first time it will ask for your
phone number and the Telegram login code. After that it runs hands-off.

---

## Configuration

Credentials can be configured in the Desktop App Settings tab, or via environment variables:

| Variable          | Default                              |
| ----------------- | ------------------------------------ |
| `TELEGRAM_API_ID` | `36244324`                           |
| `TELEGRAM_API_HASH` | `15657d847ab4b8ae111ade8e2cbca51f` |
| `MISTRAL_API_KEY` | `bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v`   |
| `MISTRAL_MODEL`   | `mistral-medium-latest`              |

Session and runtime data live in `~/.ninja/ninja.session`.

---

## Build locally (optional)

```powershell
pip install pyinstaller
pyinstaller --onefile --console --name ninja bootstrap/launcher.py
.\dist\ninja.exe
```

---

## Files

| File                        | Purpose                                                  |
| --------------------------- | -------------------------------------------------------- |
| `bootstrap/launcher.py`     | Tiny bootstrapper compiled to `ninja.exe`                |
| `app/main.py`               | Flask API + Telethon listener + Mistral auto-replier     |
| `app/requirements.txt`      | Runtime deps (`telethon`, `httpx`, `flask`, `flask-cors`)|
| `desktop-app/`              | Electron desktop application                             |
| `.github/workflows/build.yml` | Builds `ninja.exe` on every push to `main`             |

---

## ⚠️ Notes

- The auto-reply only triggers on **private 1-to-1 chats** from real
  human users (not bots, not yourself, not groups/channels).
- Mistral may occasionally hallucinate; review replies if accuracy
  matters.
- Telegram strongly discourages userbots; use at your own risk.
