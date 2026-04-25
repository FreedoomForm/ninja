"""
Ninja Auto-Reply - Native Windows Application
Uses eel for native window with HTML UI and Python backend
"""

import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Fix for embedded Python - ensure pkg_resources is available
try:
    import pkg_resources
except ImportError:
    print("ERROR: setuptools/pkg_resources not installed!")
    print("Please run: pip install setuptools")
    input("Press Enter to exit...")
    sys.exit(1)

import eel
import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User

# ---------------------------------------------------------------------------
# Configuration
# Use same directory as launcher (%LOCALAPPDATA%\Ninja)
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Ninja"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.txt"
LOGS_FILE = DATA_DIR / "logs.json"
DEBUG_LOG = DATA_DIR / "debug.log"

DEFAULT_CONFIG = {
    "api_id": "",
    "api_hash": "",
    "mistral_key": "",
    "mistral_model": "mistral-medium-latest",
    "system_prompt": "You are the personal AI assistant replying on behalf of the account owner in Telegram private chats. Be friendly, concise, and natural. Reply in the same language the user wrote in.",
}

HISTORY_LIMIT = 12
_history: dict[int, list[dict]] = {}
message_logs: list[dict] = []

# Bot state
bot = None


def debug_log(msg: str) -> None:
    """Write to debug log file"""
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
        except Exception as e:
            debug_log(f"Load config error: {e}")
    return config


def save_config(config: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
    except Exception as e:
        debug_log(f"Save config error: {e}")


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
    debug_log(f"[{direction}] {sender}: {message}")


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
        
        push_history(chat_id, "user", text)
        
        try:
            add_log("Getting AI response...", "System", "system")
            async with self.client.action(chat_id, "typing"):
                reply = await mistral_chat(
                    build_messages(chat_id, self.config["system_prompt"]),
                    self.config["mistral_key"],
                    self.config["mistral_model"]
                )
        except Exception as e:
            add_log(f"Mistral Error: {e}", "System", "error")
            return
        
        try:
            push_history(chat_id, "assistant", reply)
            add_log("Sending to Telegram...", "System", "system")
            await self.client.send_message(chat_id, reply)
            self.message_count += 1
            add_log(reply, sender_name, "outgoing")
        except Exception as e:
            add_log(f"Send Error: {e}", "System", "error")

    async def run_bot(self):
        try:
            # Validate config
            if not self.config.get("api_id") or not self.config.get("api_hash"):
                add_log("ERROR: Please configure API ID and API Hash in Settings", "System", "error")
                return
            
            if not self.config.get("mistral_key"):
                add_log("ERROR: Please configure Mistral API Key in Settings", "System", "error")
                return
            
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
            debug_log(f"Bot error: {e}")
            self.running = False

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
# Eel API Functions
# ---------------------------------------------------------------------------
@eel.expose
def get_status():
    if bot is None:
        return {"running": False, "username": None, "message_count": 0}
    return {
        "running": bot.running,
        "username": bot.username,
        "message_count": bot.message_count
    }


@eel.expose
def get_config():
    config = load_config()
    return {
        "api_id": config.get("api_id", ""),
        "api_hash": config.get("api_hash", ""),
        "mistral_key": config.get("mistral_key", ""),
        "mistral_model": config.get("mistral_model", ""),
        "system_prompt": config.get("system_prompt", "")
    }


@eel.expose
def save_config_api(config):
    global bot
    save_config(config)
    if bot:
        bot.config = load_config()
    return {"success": True}


@eel.expose
def start_bot():
    global bot
    if bot is None:
        bot = TelegramBot()
    bot.start()
    return {"success": True}


@eel.expose
def stop_bot():
    global bot
    if bot:
        bot.stop()
    return {"success": True}


@eel.expose
def get_logs():
    return message_logs[-100:]


@eel.expose
def clear_logs():
    global message_logs
    message_logs = []
    save_logs()
    return {"success": True}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global message_logs
    message_logs = load_logs()
    
    debug_log("=" * 50)
    debug_log("Ninja Bot Starting (eel)")
    debug_log(f"Python: {sys.executable}")
    debug_log(f"Working dir: {os.getcwd()}")
    debug_log("=" * 50)
    
    # Initialize eel with web folder
    web_dir = Path(__file__).parent / "web"
    debug_log(f"Web directory: {web_dir}")
    debug_log(f"Web dir exists: {web_dir.exists()}")
    
    if not web_dir.exists():
        debug_log("ERROR: Web directory not found!")
        print(f"ERROR: Web directory not found: {web_dir}")
        input("Press Enter to exit...")
        return
    
    eel.init(str(web_dir))
    
    # Start the app - try chrome first, then edge, then default browser
    try:
        debug_log("Starting with Chrome app mode...")
        eel.start(
            "index.html",
            size=(550, 650),
            resizable=True,
            mode="chrome-app"
        )
    except Exception as e:
        debug_log(f"Chrome failed: {e}, trying Edge...")
        try:
            eel.start(
                "index.html",
                size=(550, 650),
                resizable=True,
                mode="edge"
            )
        except Exception as e2:
            debug_log(f"Edge failed: {e2}, trying default browser...")
            try:
                eel.start(
                    "index.html",
                    size=(550, 650),
                    resizable=True
                )
            except Exception as e3:
                debug_log(f"All modes failed: {e3}")
                print(f"ERROR: Could not start UI: {e3}")
                input("Press Enter to exit...")


if __name__ == "__main__":
    main()
