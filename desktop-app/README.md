# Ninja Bot Desktop App

Native Windows application built with Electron + JavaScript.

## Architecture

```
┌─────────────────────────────────────────┐
│           Electron App (.exe)           │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌────────────────┐  │
│  │   Renderer  │◄──►│   Main Process │  │
│  │  (HTML/CSS) │    │   (Node.js)    │  │
│  └─────────────┘    └───────┬────────┘  │
│                             │           │
│                             ▼           │
│                    ┌────────────────┐   │
│                    │ Python Backend │   │
│                    │    (Flask)     │   │
│                    └────────────────┘   │
└─────────────────────────────────────────┘
```

## Development

### Prerequisites
- Node.js 18+
- Python 3.11+

### Install Dependencies
```bash
cd ninja-desktop
npm install
```

### Run in Development
```bash
npm start
```

## Build for Windows

### 1. Install dependencies
```bash
npm install
```

### 2. Build executable
```bash
npm run build
```

The executable will be in `dist/` folder.

### 3. For distribution
The built installer will be:
- `dist/Ninja Bot Setup 1.0.0.exe` - Windows installer

## Project Structure

```
ninja-desktop/
├── main.js        # Electron main process
├── preload.js     # Secure IPC bridge
├── renderer.js    # UI logic
├── index.html     # Main UI
├── styles.css     # Styling
├── package.json   # Dependencies
└── README.md      # This file
```

## Features

- 🎮 **Control Tab**: Start/Stop bot, view activity
- ⚙️ **Settings Tab**: Configure API credentials
- 📋 **Logs Tab**: View message history
- 🔄 **Real-time Updates**: Auto-refresh every 3 seconds
- 🎨 **Modern UI**: Dark theme, smooth animations

## How It Works

1. Electron app starts
2. User can start Python backend from UI
3. Backend runs Flask server on port 58765
4. UI communicates with backend via HTTP API
5. Bot handles Telegram messages with Mistral AI

## Troubleshooting

### "Python backend is not running"
Click "Start Backend" button to launch the Python server.

### "Cannot connect"
Make sure Python is installed and accessible from PATH.

### Build errors
Run `npm install` first to install all dependencies.
