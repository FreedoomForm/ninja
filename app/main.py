"""
Ninja Auto-Reply - Native Windows Application
----------------------------------------------
Telegram auto-reply bot with Mistral AI and Native Window GUI
Uses pywebview for a real native desktop window (no browser needed)
"""

import asyncio
import json
import logging
import os
import sys
import threading
import webview
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("NINJA_DATA_DIR", Path.home() / ".ninja"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.txt"
LOGS_FILE = DATA_DIR / "logs.json"
DEBUG_LOG = DATA_DIR / "debug.log"

DEFAULT_CONFIG = {
    "api_id": "36244324",
    "api_hash": "15657d847ab4b8ae111ade8e2cbca51f",
    "mistral_key": "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v",
    "mistral_model": "mistral-medium-latest",
    "system_prompt": "You are the personal AI assistant replying on behalf of the account owner in Telegram private chats. Be friendly, concise, and natural. Reply in the same language the user wrote in.",
}

HISTORY_LIMIT = 12
_history: dict[int, list[dict]] = {}
message_logs: list[dict] = []


def debug(msg: str) -> None:
    """Log to debug file"""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} | {msg}\n")
    except:
        pass


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        config[key] = value
        except Exception:
            pass
    return config


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")


def load_logs() -> list:
    if LOGS_FILE.exists():
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_logs() -> None:
    try:
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(message_logs[-500:], f, indent=2)
    except Exception:
        pass


async def mistral_chat(messages: list[dict], api_key: str, model: str) -> str:
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 400}
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def push_history(chat_id: int, role: str, content: str) -> None:
    buf = _history.setdefault(chat_id, [])
    buf.append({"role": role, "content": content})
    if len(buf) > HISTORY_LIMIT:
        del buf[0 : len(buf) - HISTORY_LIMIT]


def build_messages(chat_id: int, system_prompt: str) -> list[dict]:
    return [{"role": "system", "content": system_prompt}] + _history.get(chat_id, [])


def add_log(message: str, sender: str = "System", direction: str = "system") -> None:
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "sender": sender,
        "message": message[:200],
        "direction": direction
    }
    message_logs.append(entry)
    save_logs()
    debug(f"[{direction}] {sender}: {message}")


# ---------------------------------------------------------------------------
# Telegram Bot
# ---------------------------------------------------------------------------
class TelegramBot:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.running = False
        self.config = load_config()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.username: Optional[str] = None
        self.message_count = 0

    async def reply_to_message(self, chat_id: int, sender: User, text: str) -> None:
        sender_name = sender.first_name or sender.last_name or str(sender.id)
        add_log(text, sender_name, "incoming")
        debug(f"Incoming from {sender_name}: {text[:50]}...")
        
        push_history(chat_id, "user", text)
        
        try:
            add_log("Getting AI response...", "System", "system")
            async with self.client.action(chat_id, "typing"):
                reply = await mistral_chat(
                    build_messages(chat_id, self.config["system_prompt"]),
                    self.config["mistral_key"],
                    self.config["mistral_model"]
                )
            debug(f"AI Response: {reply[:50]}...")
        except Exception as e:
            add_log(f"Mistral Error: {e}", "System", "error")
            debug(f"ERROR Mistral: {e}")
            return
        
        try:
            push_history(chat_id, "assistant", reply)
            add_log("Sending to Telegram...", "System", "system")
            await self.client.send_message(chat_id, reply)
            self.message_count += 1
            add_log(reply, sender_name, "outgoing")
            debug(f"Message sent to {sender_name}!")
        except Exception as e:
            add_log(f"Send Error: {e}", "System", "error")
            debug(f"ERROR Send: {e}")

    async def run_bot(self):
        try:
            self.client = TelegramClient(
                str(SESSION_PATH),
                int(self.config["api_id"]),
                self.config["api_hash"]
            )

            @self.client.on(events.NewMessage)
            async def handler(event):
                if event.message.out or not event.is_private:
                    return
                sender = await event.get_sender()
                if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                    return
                text = (event.message.text or "").strip()
                if not text:
                    return
                await self.reply_to_message(event.chat_id, sender, text)

            await self.client.start()
            
            me = await self.client.get_me()
            self.username = f"@{me.username}" if me.username else me.first_name
            self.running = True
            add_log(f"Logged in as {self.username}", "System", "success")
            
            add_log("Checking messages...", "System", "system")
            unread_count = 0
            
            async for dialog in self.client.iter_dialogs(limit=100):
                try:
                    entity = dialog.entity
                    
                    if not isinstance(entity, User):
                        continue
                    if entity.is_self or getattr(entity, 'bot', False):
                        continue
                    
                    sender_name = entity.first_name or entity.last_name or str(entity.id)
                    
                    if dialog.unread_count > 0:
                        add_log(f"Found {dialog.unread_count} unread from {sender_name}", "System", "system")
                        
                        async for message in self.client.iter_messages(
                            dialog.entity, 
                            limit=dialog.unread_count,
                            reverse=True
                        ):
                            if not message.out and message.text:
                                await self.reply_to_message(dialog.id, entity, message.text.strip())
                                unread_count += 1
                        
                        await self.client.send_read_acknowledge(dialog.entity)
                    
                    else:
                        async for message in self.client.iter_messages(dialog.entity, limit=1):
                            if message and not message.out and message.text:
                                msg_time = message.date.replace(tzinfo=None) if message.date.tzinfo else message.date
                                if datetime.utcnow() - msg_time < timedelta(hours=24):
                                    add_log(f"Replying to last message from {sender_name}", "System", "system")
                                    await self.reply_to_message(dialog.id, entity, message.text.strip())
                                    unread_count += 1
                            break
                            
                except Exception as e:
                    add_log(f"Error: {e}", "System", "error")
                    continue
            
            if unread_count > 0:
                add_log(f"Processed {unread_count} messages", "System", "success")
            else:
                add_log("No messages to process", "System", "system")
            
            add_log("Bot is running! Waiting for new messages...", "System", "success")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            add_log(f"Error: {e}", "System", "error")
            self.running = False
            debug(f"Bot error: {e}")

    def start(self):
        if self.running:
            return
        
        add_log("Starting bot...", "System", "system")
        
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self.run_bot())
            finally:
                self.loop.close()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        if self.client and self.loop:
            async def disconnect():
                await self.client.disconnect()
            if self.loop.is_running():
                asyncio.run_coroutine_threadsafe(disconnect(), self.loop)
        self.running = False
        add_log("Bot stopped", "System", "info")


# ---------------------------------------------------------------------------
# Native Window GUI with pywebview
# ---------------------------------------------------------------------------
class Api:
    """API exposed to the webview window"""
    
    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self.window = None
        global message_logs
        message_logs = load_logs()
    
    def get_status(self):
        """Get bot status"""
        return {
            "running": self.bot.running,
            "username": self.bot.username or "-",
            "message_count": self.bot.message_count
        }
    
    def get_logs(self):
        """Get all logs"""
        return message_logs[-100:]  # Last 100
    
    def start_bot(self):
        """Start the bot"""
        self.bot.start()
        return {"success": True}
    
    def stop_bot(self):
        """Stop the bot"""
        self.bot.stop()
        return {"success": True}
    
    def get_config(self):
        """Get configuration"""
        return {
            "api_id": self.bot.config.get("api_id", ""),
            "api_hash": self.bot.config.get("api_hash", ""),
            "mistral_key": self.bot.config.get("mistral_key", ""),
            "mistral_model": self.bot.config.get("mistral_model", ""),
            "system_prompt": self.bot.config.get("system_prompt", "")
        }
    
    def save_config(self, api_id, api_hash, mistral_key, mistral_model, system_prompt):
        """Save configuration"""
        self.bot.config["api_id"] = api_id
        self.bot.config["api_hash"] = api_hash
        self.bot.config["mistral_key"] = mistral_key
        self.bot.config["mistral_model"] = mistral_model
        self.bot.config["system_prompt"] = system_prompt
        save_config(self.bot.config)
        return {"success": True}


# HTML for the native window
HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Ninja Bot</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            margin-bottom: 15px;
        }
        .header h1 { display: flex; align-items: center; gap: 10px; font-size: 20px; }
        .header h1 span { font-size: 28px; }
        .status-badge {
            padding: 6px 14px;
            border-radius: 16px;
            font-weight: 600;
            font-size: 13px;
        }
        .status-online { background: #10b981; }
        .status-offline { background: #6b7280; }
        
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px; }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        }
        .stat-card .value { font-size: 22px; font-weight: bold; color: #10b981; }
        .stat-card .label { color: #9ca3af; font-size: 12px; margin-top: 4px; }
        
        .tabs { display: flex; gap: 5px; margin-bottom: 15px; }
        .tab {
            padding: 10px 20px;
            background: rgba(255,255,255,0.05);
            border: none;
            color: #9ca3af;
            cursor: pointer;
            border-radius: 8px;
            font-size: 13px;
            transition: all 0.2s;
        }
        .tab.active { background: #10b981; color: #fff; }
        .tab:hover { background: rgba(255,255,255,0.1); }
        
        .content {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 15px;
            min-height: 300px;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary { background: #10b981; color: #fff; }
        .btn-primary:hover { background: #059669; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-danger:hover { background: #dc2626; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .control-buttons { display: flex; gap: 10px; margin-bottom: 15px; }
        
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 6px; color: #9ca3af; font-size: 13px; }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 10px;
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 6px;
            color: #fff;
            font-size: 13px;
        }
        .form-group input:focus, .form-group textarea:focus {
            outline: none;
            border-color: #10b981;
        }
        .form-group small { color: #6b7280; font-size: 11px; }
        
        .logs { max-height: 280px; overflow-y: auto; }
        .log-entry {
            padding: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            display: flex;
            gap: 10px;
            font-size: 12px;
        }
        .log-entry:last-child { border-bottom: none; }
        .log-time { color: #6b7280; min-width: 50px; }
        .log-sender { color: #10b981; min-width: 80px; font-weight: 500; }
        .log-message { color: #e5e7eb; flex: 1; }
        .log-incoming { border-left: 3px solid #3b82f6; }
        .log-outgoing { border-left: 3px solid #10b981; }
        .log-system { border-left: 3px solid #6b7280; }
        .log-error { border-left: 3px solid #ef4444; }
        .log-success { border-left: 3px solid #10b981; }
        
        .empty-state { text-align: center; padding: 40px 20px; color: #6b7280; }
        .empty-state .icon { font-size: 40px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1><span>🥷</span> Ninja Bot</h1>
        <div id="statusBadge" class="status-badge status-offline">Offline</div>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div id="statStatus" class="value">Stopped</div>
            <div class="label">Status</div>
        </div>
        <div class="stat-card">
            <div id="statMessages" class="value">0</div>
            <div class="label">Messages</div>
        </div>
        <div class="stat-card">
            <div id="statUser" class="value">-</div>
            <div class="label">Account</div>
        </div>
    </div>
    
    <div class="tabs">
        <button class="tab active" onclick="showTab('control')">🎮 Control</button>
        <button class="tab" onclick="showTab('settings')">⚙️ Settings</button>
        <button class="tab" onclick="showTab('logs')">📋 Logs</button>
    </div>
    
    <div class="content">
        <div id="tab-control" class="tab-content active">
            <div class="control-buttons">
                <button id="startBtn" class="btn btn-primary" onclick="startBot()">▶️ Start Bot</button>
                <button id="stopBtn" class="btn btn-danger" onclick="stopBot()" disabled>⏹️ Stop Bot</button>
            </div>
            <div class="logs" id="controlLogs"></div>
        </div>
        
        <div id="tab-settings" class="tab-content">
            <div class="form-group">
                <label>Telegram API ID</label>
                <input type="text" id="apiId" placeholder="12345678">
                <small>Get from <a href="#" style="color:#10b981">my.telegram.org</a></small>
            </div>
            <div class="form-group">
                <label>Telegram API Hash</label>
                <input type="password" id="apiHash" placeholder="Enter your API hash">
            </div>
            <div class="form-group">
                <label>Mistral API Key</label>
                <input type="password" id="mistralKey" placeholder="Enter your Mistral API key">
                <small>Get from <a href="#" style="color:#10b981">console.mistral.ai</a></small>
            </div>
            <div class="form-group">
                <label>Mistral Model</label>
                <input type="text" id="mistralModel" placeholder="mistral-small-latest">
            </div>
            <div class="form-group">
                <label>System Prompt</label>
                <textarea id="systemPrompt" rows="3" placeholder="Instructions for the AI..."></textarea>
            </div>
            <button class="btn btn-primary" onclick="saveConfig()">💾 Save Settings</button>
        </div>
        
        <div id="tab-logs" class="tab-content">
            <div style="margin-bottom: 10px;">
                <button class="btn" onclick="clearLogs()" style="background:#374151;">Clear Logs</button>
            </div>
            <div class="logs" id="logsList"></div>
        </div>
    </div>

    <script>
        function showTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('tab-' + tabName).classList.add('active');
        }
        
        async function updateStatus() {
            const data = await pywebview.api.get_status();
            document.getElementById('statusBadge').textContent = data.running ? 'Online' : 'Offline';
            document.getElementById('statusBadge').className = 'status-badge ' + (data.running ? 'status-online' : 'status-offline');
            document.getElementById('statStatus').textContent = data.running ? 'Running' : 'Stopped';
            document.getElementById('statMessages').textContent = data.message_count;
            document.getElementById('statUser').textContent = data.username || '-';
            document.getElementById('startBtn').disabled = data.running;
            document.getElementById('stopBtn').disabled = !data.running;
        }
        
        async function loadConfig() {
            const data = await pywebview.api.get_config();
            document.getElementById('apiId').value = data.api_id || '';
            document.getElementById('apiHash').value = data.api_hash || '';
            document.getElementById('mistralKey').value = data.mistral_key || '';
            document.getElementById('mistralModel').value = data.mistral_model || '';
            document.getElementById('systemPrompt').value = data.system_prompt || '';
        }
        
        async function saveConfig() {
            await pywebview.api.save_config(
                document.getElementById('apiId').value,
                document.getElementById('apiHash').value,
                document.getElementById('mistralKey').value,
                document.getElementById('mistralModel').value,
                document.getElementById('systemPrompt').value
            );
            alert('Settings saved!');
        }
        
        async function startBot() {
            await pywebview.api.start_bot();
            updateStatus();
        }
        
        async function stopBot() {
            await pywebview.api.stop_bot();
            updateStatus();
        }
        
        async function loadLogs() {
            const data = await pywebview.api.get_logs();
            const html = data.reverse().map(log => {
                const cls = 'log-entry log-' + log.direction;
                return '<div class="' + cls + '">' +
                    '<span class="log-time">' + log.timestamp + '</span>' +
                    '<span class="log-sender">' + log.sender + '</span>' +
                    '<span class="log-message">' + log.message + '</span>' +
                    '</div>';
            }).join('');
            document.getElementById('logsList').innerHTML = html || '<div class="empty-state"><div class="icon">📋</div><p>No logs yet</p></div>';
            document.getElementById('controlLogs').innerHTML = html || '<div class="empty-state"><div class="icon">💬</div><p>Messages will appear here</p></div>';
        }
        
        async function clearLogs() {
            // Just refresh for now
            loadLogs();
        }
        
        // Initialize
        loadConfig();
        updateStatus();
        loadLogs();
        setInterval(() => { updateStatus(); loadLogs(); }, 2000);
    </script>
</body>
</html>
"""


def main():
    debug("=" * 50)
    debug("Ninja Bot Starting (Native Window)")
    debug("=" * 50)
    
    # Create bot
    bot = TelegramBot()
    
    # Create API
    api = Api(bot)
    
    # Create native window
    window = webview.create_window(
        "🥷 Ninja Bot",
        html=HTML,
        js_api=api,
        width=550,
        height=600,
        resizable=True,
        frameless=False,
        easy_drag=True
    )
    
    api.window = window
    
    debug("Starting native window...")
    
    # Start webview (this blocks until window is closed)
    webview.start(debug=False)
    
    # Cleanup
    if bot.running:
        bot.stop()
    
    debug("Application closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
