"""
Ninja Auto-Reply - Native Windows Application
----------------------------------------------
Telegram auto-reply bot with Mistral AI and Native Windows GUI
Uses Win32 API via ctypes (no external GUI dependencies needed)
"""

import asyncio
import ctypes
import ctypes.wintypes as wintypes
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User

# ---------------------------------------------------------------------------
# Win32 API Constants
# ---------------------------------------------------------------------------
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_PAINT = 0x000F
WM_DESTROY = 0x0002

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_VISIBLE = 0x10000000
WS_VSCROLL = 0x00200000
WS_BORDER = 0x00800000
WS_CHILD = 0x40000000

BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001

SS_LEFT = 0x00000000

LBS_NOTIFY = 0x00000001
LBS_NOINTEGRALHEIGHT = 0x01000000

ES_MULTILINE = 0x0004
ES_READONLY = 0x0800
ES_AUTOVSCROLL = 0x0040

CW_USEDEFAULT = -2147483648

IDC_ARROW = 32512
COLOR_BTNFACE = 15

SW_SHOW = 5
SW_SHOWDEFAULT = 10

MB_ICONINFORMATION = 0x40
MB_YESNO = 0x04
IDYES = 6

# Timer ID
TIMER_ID = 1

# ---------------------------------------------------------------------------
# Win32 API Functions
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

WNDPROC = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.c_void_p
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("NINJA_DATA_DIR", Path.home() / ".ninja"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.txt"
LOGS_FILE = DATA_DIR / "logs.json"

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ninja")


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
        print(f"[DEBUG] Incoming from {sender_name}: {text[:50]}...")
        
        push_history(chat_id, "user", text)
        
        try:
            add_log("Getting AI response...", "System", "system")
            async with self.client.action(chat_id, "typing"):
                reply = await mistral_chat(
                    build_messages(chat_id, self.config["system_prompt"]),
                    self.config["mistral_key"],
                    self.config["mistral_model"]
                )
            print(f"[DEBUG] AI Response: {reply[:50]}...")
        except Exception as e:
            add_log(f"Mistral Error: {e}", "System", "error")
            print(f"[ERROR] Mistral: {e}")
            return
        
        try:
            push_history(chat_id, "assistant", reply)
            add_log("Sending to Telegram...", "System", "system")
            await self.client.send_message(chat_id, reply)
            self.message_count += 1
            add_log(reply, sender_name, "outgoing")
            print(f"[DEBUG] Message sent to {sender_name}!")
        except Exception as e:
            add_log(f"Send Error: {e}", "System", "error")
            print(f"[ERROR] Send: {e}")

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

    def start(self):
        if self.running:
            return
        
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
# Native Windows GUI
# ---------------------------------------------------------------------------
class NativeWindow:
    """Native Windows GUI using Win32 API via ctypes"""
    
    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self.hwnd = None
        self.hwnd_status = None
        self.hwnd_start_btn = None
        self.hwnd_stop_btn = None
        self.hwnd_log_list = None
        self.hwnd_user_label = None
        self.hwnd_msg_label = None
        self.running = True
        
        # Register window class
        self.wndclass = wintypes.WNDCLASSW()
        self.wndclass.lpszClassName = "NinjaBotClass"
        self.wndclass.lpfnWndProc = WNDPROC(self.wnd_proc)
        self.wndclass.hInstance = kernel32.GetModuleHandleW(None)
        self.wndclass.hCursor = user32.LoadCursorW(None, IDC_ARROW)
        self.wndclass.hbrBackground = (gdi32.GetStockObject(4),)  # LTGRAY_BRUSH
        
        user32.RegisterClassW(ctypes.byref(self.wndclass))
        
        # Load logs
        global message_logs
        message_logs = load_logs()
    
    def wnd_proc(self, hwnd, msg, wparam, lparam):
        """Window procedure - handles all window events"""
        if msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == 1:  # Start button
                self.on_start()
            elif cmd == 2:  # Stop button
                self.on_stop()
        elif msg == WM_TIMER:
            self.update_ui()
        elif msg == WM_CLOSE:
            self.running = False
            user32.KillTimer(hwnd, TIMER_ID)
            user32.DestroyWindow(hwnd)
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    
    def create_window(self):
        """Create the main window and all controls"""
        hinst = kernel32.GetModuleHandleW(None)
        
        # Main window
        self.hwnd = user32.CreateWindowExW(
            0, "NinjaBotClass", "Ninja Bot - Telegram Auto-Reply",
            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_VISIBLE,
            CW_USEDEFAULT, CW_USEDEFAULT, 500, 450,
            None, None, hinst, None
        )
        
        # Status label
        self.hwnd_status = user32.CreateWindowExW(
            0, "STATIC", "Status: Stopped",
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            20, 20, 200, 25,
            self.hwnd, None, hinst, None
        )
        
        # User label
        self.hwnd_user_label = user32.CreateWindowExW(
            0, "STATIC", "Account: -",
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            20, 50, 200, 25,
            self.hwnd, None, hinst, None
        )
        
        # Message count label
        self.hwnd_msg_label = user32.CreateWindowExW(
            0, "STATIC", "Messages: 0",
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            20, 80, 200, 25,
            self.hwnd, None, hinst, None
        )
        
        # Start button
        self.hwnd_start_btn = user32.CreateWindowExW(
            0, "BUTTON", "Start Bot",
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            250, 20, 100, 35,
            self.hwnd, 1, hinst, None
        )
        
        # Stop button (disabled initially)
        self.hwnd_stop_btn = user32.CreateWindowExW(
            0, "BUTTON", "Stop Bot",
            WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            360, 20, 100, 35,
            self.hwnd, 2, hinst, None
        )
        user32.EnableWindow(self.hwnd_stop_btn, False)
        
        # Log listbox
        user32.CreateWindowExW(
            0, "STATIC", "Activity Log:",
            WS_CHILD | WS_VISIBLE | SS_LEFT,
            20, 120, 200, 25,
            self.hwnd, None, hinst, None
        )
        
        self.hwnd_log_list = user32.CreateWindowExW(
            0x200,  # WS_EX_CLIENTEDGE
            "LISTBOX", "",
            WS_CHILD | WS_VISIBLE | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT | WS_BORDER,
            20, 145, 440, 250,
            self.hwnd, None, hinst, None
        )
        
        # Set timer for UI updates
        user32.SetTimer(self.hwnd, TIMER_ID, 1000, None)
        
        return self.hwnd
    
    def on_start(self):
        """Handle start button click"""
        add_log("Starting bot...", "System", "system")
        self.bot.start()
    
    def on_stop(self):
        """Handle stop button click"""
        self.bot.stop()
    
    def update_ui(self):
        """Update UI elements based on bot state"""
        if not self.running:
            return
        
        # Update status
        if self.bot.running:
            status = "Status: Running"
            user32.SetWindowTextW(self.hwnd_status, status)
            user32.EnableWindow(self.hwnd_start_btn, False)
            user32.EnableWindow(self.hwnd_stop_btn, True)
        else:
            status = "Status: Stopped"
            user32.SetWindowTextW(self.hwnd_status, status)
            user32.EnableWindow(self.hwnd_start_btn, True)
            user32.EnableWindow(self.hwnd_stop_btn, False)
        
        # Update user
        user = f"Account: {self.bot.username}" if self.bot.username else "Account: -"
        user32.SetWindowTextW(self.hwnd_user_label, user)
        
        # Update message count
        user32.SetWindowTextW(self.hwnd_msg_label, f"Messages: {self.bot.message_count}")
        
        # Update log list
        # Only add new logs
        current_count = user32.SendMessageW(self.hwnd_log_list, 0x018B, 0, 0)  # LB_GETCOUNT
        new_logs = message_logs[current_count:]
        for log_entry in new_logs:
            text = f"[{log_entry['timestamp']}] {log_entry['sender']}: {log_entry['message']}"
            user32.SendMessageW(self.hwnd_log_list, 0x0180, 0, text)  # LB_ADDSTRING
        
        # Scroll to bottom if new logs added
        if new_logs:
            count = user32.SendMessageW(self.hwnd_log_list, 0x018B, 0, 0)  # LB_GETCOUNT
            user32.SendMessageW(self.hwnd_log_list, 0x197, count - 1, 0)  # LB_SETCURSEL
    
    def run(self):
        """Main message loop"""
        self.create_window()
        
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        
        return msg.wParam


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main():
    print("=" * 50)
    print(" Ninja Bot - Native Windows Application ")
    print("=" * 50)
    
    bot = TelegramBot()
    window = NativeWindow(bot)
    
    print("Starting native Windows GUI...")
    window.run()
    
    # Cleanup
    if bot.running:
        bot.stop()
    
    print("Application closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
