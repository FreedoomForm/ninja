"""
Ninja Userbot - Standalone Windows EXE
======================================
Telegram Auto-Reply with AI
NO external dependencies - everything in one EXE
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import asyncio
import json
import os
import sys
import base64
import shutil
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

# Hide console on Windows
if sys.platform == 'win32':
    try:
        import ctypes
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            ctypes.windll.user32.ShowWindow(console, 0)
    except:
        pass

# GUI
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False

# Telegram
from telethon import TelegramClient, events
from telethon.tl.types import User, MessageMediaGeo, MessageMediaGeoLive, MessageMediaPhoto, DocumentAttributeSticker

# HTTP
import httpx

# ===========================================================================
# CONFIG
# ===========================================================================
APP_NAME = "Ninja Userbot"
VERSION = "5.0"

# Data directory
if sys.platform == 'win32':
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Ninja"
else:
    DATA_DIR = Path.home() / ".ninja"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# COMPANY INFO
# ===========================================================================
COMPANY_INFO = """
Sog'lom taom - здоровое питание, Ташкент

ЦЕНЫ:
- 1000-1200 ккал: 84 000 сум
- 1400-1600 ккал: 98 000 сум  
- 1800-2000 ккал: 112 000 сум
- 2200-2500 ккал: 126 000 сум

ДОСТАВКА: 17:00-22:00, заказ до 21:00

КАРТЫ:
- Humo: 9860010112421465
- Uzum: 4916990324223715
- Uzcard: 5614681209925290
"""

DEFAULT_SYSTEM_PROMPT = """Ты Бахром, сотрудник Sog'lom taom (доставка здорового питания в Ташкенте).
Отвечаешь на сообщения клиентов в Telegram на русском и узбекском языках.
Будь дружелюбным, кратким и профессиональным.
Используй "Сиз" для новых клиентов.

""" + COMPANY_INFO + """

При получении чека - подтверди и спроси дату доставки.
При получении локации - спроси точный адрес.
"""


DEFAULT_CONFIG = {
    "api_id": "",
    "api_hash": "",
    "phone": "",
    "mistral_key": "",  # API ключ для AI
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
}

DAYS_RU = {
    'monday': 'понедельник', 'tuesday': 'вторник', 'wednesday': 'среда',
    'thursday': 'четверг', 'friday': 'пятница', 'saturday': 'суббота', 'sunday': 'воскресенье'
}


# ===========================================================================
# DATA CLASSES
# ===========================================================================
@dataclass
class MessageLog:
    id: str
    timestamp: str
    sender: str
    text: str
    direction: str
    has_image: bool = False
    has_location: bool = False


# ===========================================================================
# AI CLIENT - Direct API calls, no proxy needed!
# ===========================================================================
class AIClient:
    """Direct AI API client - works without any external dependencies"""

    def __init__(self, config: dict):
        self.config = config
        self.mistral_key = config.get("mistral_key", "")

    async def chat(self, messages: list) -> str:
        """Chat completion via Mistral API"""
        if not self.mistral_key:
            raise Exception("Укажите Mistral API Key в настройках")
        
        now = datetime.now()
        time_context = f"\n\n[ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')} ({DAYS_RU.get(now.strftime('%A').lower(), '')})]"
        
        messages_with_time = messages.copy()
        if messages_with_time and messages_with_time[0]["role"] == "system":
            messages_with_time[0] = {
                "role": "system", 
                "content": messages_with_time[0]["content"] + time_context
            }

        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.mistral_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "mistral-small-latest",  # Быстрая и дешёвая модель
            "messages": messages_with_time,
            "temperature": 0.7,
            "max_tokens": 1000
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                error = response.text[:200]
                raise Exception(f"Mistral API error: {response.status_code} - {error}")

    async def vision(self, image_base64: str) -> str:
        """Image analysis via Mistral Vision (Pixtral)"""
        if not self.mistral_key:
            return "[изображение - укажите API ключ]"
        
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.mistral_key}",
            "Content-Type": "application/json"
        }
        
        prompt = "Опиши это изображение кратко на русском. Если это чек - укажи сумму. Если стикер - опиши эмоцию."

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_base64}}
            ]
        }]
        
        payload = {
            "model": "pixtral-12b-2409",  # Vision модель
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 500
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Vision error: {e}")
        
        return "изображение"


# ===========================================================================
# BOT MANAGER
# ===========================================================================
class BotManager:
    """Telegram client manager"""

    def __init__(self, config: dict, message_callback, ai_client: AIClient):
        self.config = config
        self.message_callback = message_callback
        self.ai_client = ai_client
        self.client: Optional[TelegramClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = False
        self.conversation_history: Dict[int, list] = {}
        self.phone_code_hash = None
        self._thread = None

    def _start_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _ensure_loop(self):
        if not self._thread or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._start_loop, daemon=True)
            self._thread.start()

    async def _create_client(self):
        if self.client:
            return
        api_id = self.config.get("api_id", "")
        api_hash = self.config.get("api_hash", "")
        if not api_id or not api_hash:
            raise Exception("Настройте API ID и API Hash")
        self.client = TelegramClient(str(SESSION_PATH), int(api_id), api_hash)
        await self.client.connect()

    def connect(self, phone: str, callback):
        async def _connect():
            try:
                await self._create_client()
                if await self.client.is_user_authorized():
                    me = await self.client.get_me()
                    callback("authorized", me.first_name or "")
                    return
                result = await self.client.send_code_request(phone)
                self.phone_code_hash = result.phone_code_hash
                callback("code_sent", "")
            except Exception as e:
                callback("error", str(e))
        
        self._ensure_loop()
        asyncio.run_coroutine_threadsafe(_connect(), self.loop)

    def sign_in(self, phone: str, code: str, callback):
        async def _sign_in():
            try:
                if not self.client:
                    callback("error", "Сначала нажмите Войти")
                    return
                await self.client.sign_in(phone, code, phone_code_hash=self.phone_code_hash)
                me = await self.client.get_me()
                callback("signed_in", me.first_name or "")
            except Exception as e:
                callback("error", str(e))
        
        asyncio.run_coroutine_threadsafe(_sign_in(), self.loop)

    def start(self, callback):
        async def _start():
            try:
                if not self.client:
                    callback("error", "Сначала авторизуйтесь")
                    return
                
                @self.client.on(events.NewMessage(incoming=True))
                async def handler(event):
                    if not self.running:
                        return
                    try:
                        sender = await event.get_sender()
                        if isinstance(sender, User) and not sender.bot:
                            await self._process_message(event, sender)
                    except Exception as e:
                        self.message_callback("error", str(e))
                
                self.running = True
                callback("started", "")
                while self.running:
                    await asyncio.sleep(1)
            except Exception as e:
                callback("error", str(e))
        
        asyncio.run_coroutine_threadsafe(_start(), self.loop)

    def stop(self):
        self.running = False

    async def _download_image(self, event) -> Optional[str]:
        try:
            if not event.media or not isinstance(event.media, MessageMediaPhoto):
                return None
            file_path = await self.client.download_media(event.media.photo, IMAGES_DIR)
            with open(file_path, "rb") as f:
                return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
        except:
            return None

    async def _process_message(self, event, sender: User):
        chat_id = event.chat_id
        text = event.text or ""
        name = sender.first_name or "User"

        media_desc = ""
        has_image = False
        has_location = False

        # Location
        if isinstance(event.media, (MessageMediaGeo, MessageMediaGeoLive)):
            has_location = True
            lat, lon = event.media.geo.lat, event.media.geo.long
            media_desc = f"[ЛОКАЦИЯ: {lat:.4f}, {lon:.4f}]"
            self.message_callback("location", {"sender": name, "lat": lat, "lon": lon})

        # Image
        elif isinstance(event.media, MessageMediaPhoto):
            has_image = True
            img = await self._download_image(event)
            if img:
                media_desc = await self.ai_client.vision(img)
                self.message_callback("image", {"sender": name, "desc": media_desc})

        # Sticker
        elif event.media and hasattr(event.media, 'document'):
            for attr in (event.media.document.attributes or []):
                if isinstance(attr, DocumentAttributeSticker):
                    media_desc = f"[СТИКЕР: {attr.alt or ''}]"
                    break

        # History
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        full_text = f"{media_desc}\n{text}" if media_desc else text
        self.conversation_history[chat_id].append({"role": "user", "content": full_text})
        
        if len(self.conversation_history[chat_id]) > 20:
            self.conversation_history[chat_id] = self.conversation_history[chat_id][-20:]

        msgs = [{"role": "system", "content": self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT)}]
        msgs.extend(self.conversation_history[chat_id])

        self.message_callback("message", {"sender": name, "text": full_text[:200], "direction": "in", 
                                          "has_image": has_image, "has_location": has_location})

        try:
            response = await self.ai_client.chat(msgs)
            await event.reply(response)
            self.conversation_history[chat_id].append({"role": "assistant", "content": response})
            self.message_callback("message", {"sender": "AI", "text": response[:200], "direction": "out"})
        except Exception as e:
            self.message_callback("error", f"AI: {e}")


# ===========================================================================
# APP
# ===========================================================================
class NinjaApp:
    def __init__(self):
        self.config = self._load_config()
        self.queue = queue.Queue()
        self.logs: List[MessageLog] = []
        self._load_logs()
        
        self.ai = AIClient(self.config)
        self.bot = BotManager(self.config, lambda t, d: self.queue.put((t, d)), self.ai)
        
        self.msg_count = len(self.logs)
        self.username = ""
        
        self._setup_ui()
        self.root.after(100, self._process)
        self._log("System", "🚀 Готов к работе", "system")

    def _load_config(self) -> dict:
        cfg = DEFAULT_CONFIG.copy()
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except:
                pass
        return cfg

    def _save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def _load_logs(self):
        if LOGS_FILE.exists():
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    self.logs = [MessageLog(**m) for m in json.load(f)[-500:]]
            except:
                pass

    def _save_logs(self):
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in self.logs[-500:]], f, ensure_ascii=False)

    def _setup_ui(self):
        if CTK_AVAILABLE:
            self._setup_ctk()
        else:
            self._setup_tk()

    def _setup_ctk(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.root = ctk.CTk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("850x600")
        
        main = ctk.CTkFrame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Header
        h = ctk.CTkFrame(main, height=40)
        h.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(h, text="🥷 Ninja Userbot", font=("", 16, "bold")).pack(side="left", padx=10)
        ctk.CTkLabel(h, text="Standalone EXE", text_color="#10b981", font=("", 11)).pack(side="left")
        self.status = ctk.CTkLabel(h, text="⏹ Offline", text_color="gray")
        self.status.pack(side="right", padx=10)
        
        # Stats
        stats = ctk.CTkFrame(main)
        stats.pack(fill="x", pady=(0, 10))
        self.stat_labels = {}
        for t in ["Статус", "Сообщений", "Аккаунт"]:
            f = ctk.CTkFrame(stats, width=100)
            f.pack(side="left", padx=5, pady=5)
            f.pack_propagate(False)
            v = ctk.CTkLabel(f, text="0" if t != "Статус" else "Stopped", font=("", 12, "bold"), text_color="#10b981")
            v.pack(pady=(8, 0))
            ctk.CTkLabel(f, text=t, font=("", 9), text_color="gray").pack()
            self.stat_labels[t] = v
        
        # Tabs
        tabs = ctk.CTkTabview(main)
        tabs.pack(fill="both", expand=True)
        tabs.add("🎮 Управление")
        tabs.add("⚙️ Настройки")
        
        # Control Tab
        t1 = tabs.tab("🎮 Управление")
        
        # Auth
        a = ctk.CTkFrame(t1)
        a.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(a, text="📱 Telegram", font=("", 12, "bold")).pack(pady=8)
        
        r1 = ctk.CTkFrame(a, fg_color="transparent")
        r1.pack(fill="x", padx=15, pady=3)
        ctk.CTkLabel(r1, text="Телефон:", width=70).pack(side="left")
        self.phone = ctk.CTkEntry(r1, width=150, placeholder_text="+998...")
        self.phone.pack(side="left", padx=10)
        self.phone.insert(0, self.config.get("phone", ""))
        ctk.CTkButton(r1, text="Войти", width=70, command=self._auth).pack(side="left")
        
        r2 = ctk.CTkFrame(a, fg_color="transparent")
        r2.pack(fill="x", padx=15, pady=3)
        ctk.CTkLabel(r2, text="Код:", width=70).pack(side="left")
        self.code = ctk.CTkEntry(r2, width=70, placeholder_text="12345")
        self.code.pack(side="left", padx=10)
        ctk.CTkButton(r2, text="OK", width=50, command=self._code).pack(side="left")
        
        # Bot control
        b = ctk.CTkFrame(t1)
        b.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(b, text="🤖 Бот", font=("", 12, "bold")).pack(pady=8)
        
        btns = ctk.CTkFrame(b, fg_color="transparent")
        btns.pack(pady=5)
        self.start_btn = ctk.CTkButton(btns, text="▶️ Запустить", width=140, height=35, fg_color="#10b981", command=self._start)
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = ctk.CTkButton(btns, text="⏹️ Стоп", width=140, height=35, fg_color="#ef4444", state="disabled", command=self._stop)
        self.stop_btn.pack(side="left", padx=10)
        
        # Logs
        ctk.CTkLabel(t1, text="📋 Логи", font=("", 11, "bold")).pack(anchor="w", padx=15, pady=(10, 5))
        self.logs_text = ctk.CTkTextbox(t1, height=120)
        self.logs_text.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Settings Tab
        t2 = tabs.tab("⚙️ Настройки")
        s = ctk.CTkScrollableFrame(t2)
        s.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(s, text="📱 Telegram (my.telegram.org)", font=("", 12, "bold"), text_color="#10b981").pack(anchor="w", pady=(5, 5))
        
        r1 = ctk.CTkFrame(s, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="API ID:", width=90).pack(side="left")
        self.api_id = ctk.CTkEntry(r1, width=250)
        self.api_id.pack(side="left", padx=10)
        self.api_id.insert(0, self.config.get("api_id", ""))
        
        r2 = ctk.CTkFrame(s, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text="API Hash:", width=90).pack(side="left")
        self.api_hash = ctk.CTkEntry(r2, width=250, show="*")
        self.api_hash.pack(side="left", padx=10)
        self.api_hash.insert(0, self.config.get("api_hash", ""))
        
        ctk.CTkLabel(s, text="🤖 Mistral AI (console.mistral.ai)", font=("", 12, "bold"), text_color="#10b981").pack(anchor="w", pady=(15, 5))
        
        r3 = ctk.CTkFrame(s, fg_color="transparent")
        r3.pack(fill="x", pady=2)
        ctk.CTkLabel(r3, text="API Key:", width=90).pack(side="left")
        self.mistral = ctk.CTkEntry(r3, width=250, show="*")
        self.mistral.pack(side="left", padx=10)
        self.mistral.insert(0, self.config.get("mistral_key", ""))
        
        ctk.CTkLabel(s, text="💬 Промпт", font=("", 12, "bold"), text_color="#10b981").pack(anchor="w", pady=(15, 5))
        self.prompt = ctk.CTkTextbox(s, height=180)
        self.prompt.pack(fill="x", pady=5)
        self.prompt.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        
        ctk.CTkButton(s, text="💾 Сохранить", width=120, height=35, command=self._save).pack(pady=15)

    def _setup_tk(self):
        self.root = tk.Tk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("800x550")
        
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Control
        c = ttk.Frame(nb)
        nb.add(c, text="Управление")
        
        a = ttk.LabelFrame(c, text="Авторизация")
        a.pack(fill="x", padx=10, pady=10)
        ttk.Label(a, text="Телефон:").grid(row=0, column=0, padx=5, pady=5)
        self.phone = ttk.Entry(a, width=15)
        self.phone.grid(row=0, column=1, padx=5, pady=5)
        self.phone.insert(0, self.config.get("phone", ""))
        ttk.Button(a, text="Войти", command=self._auth).grid(row=0, column=2, padx=5)
        
        ttk.Label(a, text="Код:").grid(row=1, column=0, padx=5, pady=5)
        self.code = ttk.Entry(a, width=8)
        self.code.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(a, text="OK", command=self._code).grid(row=1, column=2, padx=5)
        
        b = ttk.LabelFrame(c, text="Бот")
        b.pack(fill="x", padx=10, pady=10)
        self.start_btn = ttk.Button(b, text="▶️ Запустить", command=self._start)
        self.start_btn.pack(side="left", padx=10, pady=10)
        self.stop_btn = ttk.Button(b, text="⏹️ Стоп", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)
        
        self.logs_text = scrolledtext.ScrolledText(c, height=10)
        self.logs_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Settings
        s = ttk.Frame(nb)
        nb.add(s, text="Настройки")
        
        ttk.Label(s, text="API ID:").pack(anchor="w", padx=10, pady=3)
        self.api_id = ttk.Entry(s, width=35)
        self.api_id.pack(anchor="w", padx=10)
        self.api_id.insert(0, self.config.get("api_id", ""))
        
        ttk.Label(s, text="API Hash:").pack(anchor="w", padx=10, pady=3)
        self.api_hash = ttk.Entry(s, width=35, show="*")
        self.api_hash.pack(anchor="w", padx=10)
        self.api_hash.insert(0, self.config.get("api_hash", ""))
        
        ttk.Label(s, text="Mistral API Key:").pack(anchor="w", padx=10, pady=3)
        self.mistral = ttk.Entry(s, width=35, show="*")
        self.mistral.pack(anchor="w", padx=10)
        self.mistral.insert(0, self.config.get("mistral_key", ""))
        
        ttk.Label(s, text="Промпт:").pack(anchor="w", padx=10, pady=10)
        self.prompt = scrolledtext.ScrolledText(s, height=10)
        self.prompt.pack(fill="both", expand=True, padx=10)
        self.prompt.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        
        ttk.Button(s, text="Сохранить", command=self._save).pack(pady=10)
        
        self.status = ttk.Label(self.root, text="⏹ Offline")
        self.status.pack(fill="x", side="bottom")

    def _log(self, sender: str, text: str, direction: str, img=False, loc=False):
        log = MessageLog(datetime.now().strftime("%Y%m%d%H%M%S%f"), datetime.now().strftime("%H:%M:%S"), 
                        sender, text, direction, img, loc)
        self.logs.append(log)
        self._save_logs()
        self.msg_count = len(self.logs)
        
        icon = "🖼️ " if img else "📍 " if loc else ""
        line = f"[{log.timestamp}] {sender}: {icon}{text}\n"
        self.logs_text.insert("end", line)
        self.logs_text.see("end")
        
        if "Сообщений" in self.stat_labels:
            self.stat_labels["Сообщений"].configure(text=str(self.msg_count))

    def _process(self):
        try:
            while True:
                t, d = self.queue.get_nowait()
                if t == "auth":
                    s, i = d
                    if s == "authorized":
                        self.username = i
                        self.stat_labels["Аккаунт"].configure(text=i[:10])
                        self._log("System", f"✅ Авторизован: {i}", "system")
                    elif s == "code_sent":
                        self._log("System", "📱 Код отправлен", "system")
                        messagebox.showinfo("Код", "Код отправлен в Telegram!")
                    elif s == "signed_in":
                        self.username = i
                        self.stat_labels["Аккаунт"].configure(text=i[:10])
                        self._log("System", f"✅ Вход: {i}", "system")
                    elif s == "error":
                        self._log("Error", i, "system")
                        messagebox.showerror("Ошибка", i)
                elif t == "bot_start":
                    s, i = d
                    if s == "started":
                        self.start_btn.configure(state="disabled")
                        self.stop_btn.configure(state="normal")
                        self.status.configure(text="🟢 Online")
                        self.stat_labels["Статус"].configure(text="Running")
                        self._log("System", "✅ Бот запущен!", "system")
                    elif s == "error":
                        self._log("Error", i, "system")
                        messagebox.showerror("Ошибка", i)
                elif t == "message":
                    self._log(d["sender"], d["text"], d["direction"], d.get("has_image", False), d.get("has_location", False))
                elif t == "location":
                    self._log(d["sender"], f"📍 {d['lat']:.4f}, {d['lon']:.4f}", "in", loc=True)
                elif t == "image":
                    self._log(d["sender"], f"🖼️ {d['desc'][:60]}", "in", img=True)
                elif t == "error":
                    self._log("Error", str(d), "system")
        except queue.Empty:
            pass
        self.root.after(100, self._process)

    def _auth(self):
        p = self.phone.get().strip()
        if not p:
            messagebox.showerror("Ошибка", "Введите телефон")
            return
        self.config["phone"] = p
        self._save_config()
        self.bot.config = self.config
        self.bot.connect(p, lambda s, i: self.queue.put(("auth", (s, i))))

    def _code(self):
        c = self.code.get().strip()
        p = self.phone.get().strip()
        if not c:
            return
        self.bot.sign_in(p, c, lambda s, i: self.queue.put(("auth", (s, i))))

    def _start(self):
        if not self.config.get("api_id") or not self.config.get("api_hash"):
            messagebox.showerror("Ошибка", "Настройте API ID и Hash")
            return
        if not self.config.get("mistral_key"):
            messagebox.showwarning("Внимание", "Рекомендуется указать Mistral API Key для работы AI")
        self.bot.config = self.config
        self.bot.start(lambda s, i: self.queue.put(("bot_start", (s, i))))

    def _stop(self):
        self.bot.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="⏹ Offline")
        self.stat_labels["Статус"].configure(text="Stopped")
        self._log("System", "Бот остановлен", "system")

    def _save(self):
        self.config["api_id"] = self.api_id.get().strip()
        self.config["api_hash"] = self.api_hash.get().strip()
        self.config["mistral_key"] = self.mistral.get().strip()
        self.config["system_prompt"] = self.prompt.get("1.0", "end").strip()
        self._save_config()
        self.bot.config = self.config
        self.ai.mistral_key = self.config["mistral_key"]
        self._log("System", "✅ Сохранено", "system")
        messagebox.showinfo("OK", "Настройки сохранены!")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    NinjaApp().run()
