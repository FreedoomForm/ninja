"""
Ninja Userbot - Native Windows Application
============================================
Telegram Auto-Reply with AI
One standalone EXE - no external dependencies
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import asyncio
import json
import os
import sys
import subprocess
import time
import socket
import base64
import re
import queue
from datetime import datetime, timedelta
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

# GUI imports
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False

# Telegram
from telethon import TelegramClient, events
from telethon.tl.types import User, MessageMediaGeo, MessageMediaGeoLive, MessageMediaPhoto, DocumentAttributeSticker

# HTTP client
import httpx

# ===========================================================================
# CONFIGURATION
# ===========================================================================
APP_NAME = "Ninja Userbot"
VERSION = "4.0"

# Data directory
if sys.platform == 'win32':
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Ninja"
else:
    DATA_DIR = Path.home() / ".ninja"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
LEADS_FILE = DATA_DIR / "leads.json"
ORDERS_FILE = DATA_DIR / "orders.json"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# AI Proxy settings
AI_PROXY_PORT = 3000

# ===========================================================================
# COMPANY INFO
# ===========================================================================
COMPANY_INFO = """
КОМПАНИЯ: Sog'lom taom (Соғлом таом) - здоровое питание с доставкой
ЛОКАЦИЯ: Ташкент, Сергели район
ГРАФИК: пн-пт, суббота - выходной

КАЛОРИИ И ЦЕНЫ:
- 1000–1200 ккал — 84 000 сум
- 1400–1600 ккал — 98 000 сум
- 1800–2000 ккал — 112 000 сум
- 2200–2500 ккал — 126 000 сум

ДОСТАВКА: 17:00–22:00
ЗАКАЗ: До 21:00 за день до доставки

КАРТЫ:
- Humo: 9860010112421465
- Uzum: 4916990324223715
- Uzcard: 5614681209925290
- Получатель: Xodjimuratov Bahodir
"""

DEFAULT_SYSTEM_PROMPT = """Ты Бахром, сотрудник компании Sog'lom taom из Ташкента.
Отвечаешь на сообщения клиентов в Telegram дружелюбно и профессионально.
Общаешься на узбекском и русском языках.

""" + COMPANY_INFO + """

Правила:
- Ты НЕ бот, ты реальный человек
- Отвечай кратко и по делу
- Используй "Сиз" для новых клиентов
- При получении чека - подтверди и спроси дату доставки
- При получении локации - спроси точный адрес
"""

DEFAULT_CONFIG = {
    "api_id": "",
    "api_hash": "",
    "phone": "",
    "mistral_key": "",
    "mistral_model": "pixtral-12b-2409",
    "text_model": "mistral-medium-latest",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "ai_model": "glm-4",
}

DAYS_RU = {
    'monday': 'понедельник', 'tuesday': 'вторник', 'wednesday': 'среда',
    'thursday': 'четверг', 'friday': 'пятница', 'saturday': 'суббота', 'sunday': 'воскресенье'
}

PRICE_MAP = {
    "1000-1200": 84000, "1400-1600": 98000,
    "1800-2000": 112000, "2200-2500": 126000,
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


@dataclass
class Lead:
    id: str
    timestamp: str
    client_name: str
    summary: str
    confidence: float = 0.5
    urgency: str = "medium"


# ===========================================================================
# AI PROXY MANAGER
# ===========================================================================
class AIProxyManager:
    """Manages the AI Proxy server"""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self.process = None
        self.running = False
        self.proxy_dir = self._find_proxy_dir()

    def _find_proxy_dir(self) -> Optional[Path]:
        """Find ai-proxy directory"""
        # Check common locations
        locations = []
        
        if getattr(sys, 'frozen', False):
            # Running as EXE
            exe_dir = Path(sys.executable).parent
            locations.append(exe_dir / "ai-proxy")
            locations.append(exe_dir.parent / "ai-proxy")
        
        # Running as script
        locations.append(Path(__file__).parent.parent / "ai-proxy")
        locations.append(Path.cwd() / "ai-proxy")
        
        for loc in locations:
            if loc.exists() and (loc / "package.json").exists():
                return loc
        return None

    def is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return False
        except:
            return True

    def check_api_available(self) -> bool:
        try:
            r = httpx.get(f"http://localhost:{AI_PROXY_PORT}/api/ai", timeout=2)
            return r.status_code == 200
        except:
            return False

    def start(self) -> bool:
        # Check if already running
        if self.is_port_in_use(AI_PROXY_PORT) and self.check_api_available():
            if self.status_callback:
                self.status_callback("✅ AI Proxy уже запущен")
            return True

        if not self.proxy_dir:
            if self.status_callback:
                self.status_callback("⚠️ AI Proxy не найден - используется прямой API")
            return False

        if self.status_callback:
            self.status_callback("🚀 Запуск AI Proxy...")

        try:
            # Try node server.js first, then npm
            server_js = self.proxy_dir / "server.js"
            if server_js.exists():
                cmd = ["node", "server.js"]
            else:
                cmd = ["npm", "run", "start"]

            self.process = subprocess.Popen(
                cmd, cwd=str(self.proxy_dir),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Wait for startup
            for i in range(30):
                time.sleep(1)
                if self.check_api_available():
                    self.running = True
                    if self.status_callback:
                        self.status_callback("✅ AI Proxy запущен!")
                    return True

            if self.status_callback:
                self.status_callback("❌ AI Proxy не запустился")
            return False

        except Exception as e:
            if self.status_callback:
                self.status_callback(f"❌ Ошибка: {e}")
            return False

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
        self.running = False


# ===========================================================================
# AI CLIENT
# ===========================================================================
class AIClient:
    """Client for AI API - z-ai-web-sdk or Mistral"""

    def __init__(self, config: dict):
        self.config = config
        self.proxy_url = f"http://localhost:{AI_PROXY_PORT}/api/ai"
        self.vision_url = f"http://localhost:{AI_PROXY_PORT}/api/ai/vision"

    async def chat(self, messages: list, model: str = "glm-4") -> str:
        """Send chat completion request"""
        now = datetime.now()
        time_context = f"\n\n[ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')} ({DAYS_RU.get(now.strftime('%A').lower(), '')})]"
        time_context += f"\n[ДЕДЛАЙН: 21:00]"
        if now.hour >= 21:
            time_context += "\n[ВНИМАНИЕ: После 21:00!]"

        messages_with_time = messages.copy()
        if messages_with_time and messages_with_time[0]["role"] == "system":
            messages_with_time[0] = {
                "role": "system", 
                "content": messages_with_time[0]["content"] + time_context
            }

        # Try proxy first
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.proxy_url,
                    json={"messages": messages_with_time, "model": model, "temperature": 0.7}
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
        except:
            pass

        raise Exception("AI API недоступен. Проверьте AI Proxy.")

    async def vision(self, image_base64: str) -> str:
        """Analyze image"""
        mistral_key = self.config.get("mistral_key", "")
        mistral_model = self.config.get("mistral_model", "pixtral-12b-2409")

        # Try Mistral Vision API
        if mistral_key:
            try:
                url = "https://api.mistral.ai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"}
                
                prompt = "Опиши это изображение. Если чек - укажи сумму. Если стикер - опиши эмоцию. Отвечай кратко."
                
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_base64}}
                    ]
                }]

                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(url, headers=headers, json={"model": mistral_model, "messages": messages})
                    if r.status_code == 200:
                        return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"Mistral Vision error: {e}")

        # Try proxy vision
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(self.vision_url, json={"image_base64": image_base64})
                if r.status_code == 200:
                    return r.json().get("description", "изображение")
        except:
            pass

        return "изображение"


# ===========================================================================
# BOT MANAGER
# ===========================================================================
class BotManager:
    """Manages Telegram client"""

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

    def start_async_thread(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

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
                    callback("authorized", me.first_name if me else "")
                    return
                result = await self.client.send_code_request(phone)
                self.phone_code_hash = result.phone_code_hash
                callback("code_sent", "")
            except Exception as e:
                callback("error", str(e))

        if not self.loop:
            self.start_async_thread()
        asyncio.run_coroutine_threadsafe(_connect(), self.loop)

    def sign_in(self, phone: str, code: str, callback):
        async def _sign_in():
            try:
                await self.client.sign_in(phone, code, phone_code_hash=self.phone_code_hash)
                me = await self.client.get_me()
                callback("signed_in", me.first_name if me else "")
            except Exception as e:
                callback("error", str(e))
        asyncio.run_coroutine_threadsafe(_sign_in(), self.loop)

    def start_bot(self, callback):
        async def _start():
            try:
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

    def stop_bot(self):
        self.running = False

    async def _download_image(self, event) -> Optional[str]:
        try:
            if not event.media:
                return None
            if isinstance(event.media, MessageMediaPhoto):
                photo = event.media.photo
                if photo:
                    file_path = await self.client.download_media(photo, IMAGES_DIR)
                    with open(file_path, "rb") as f:
                        image_data = f.read()
                    ext = Path(file_path).suffix.lower()
                    mime_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
                    mime_type = mime_types.get(ext, 'image/jpeg')
                    return f"data:{mime_type};base64,{base64.b64encode(image_data).decode('utf-8')}"
            return None
        except:
            return None

    async def _process_message(self, event, sender: User):
        chat_id = event.chat_id
        text = event.text or ""
        sender_name = sender.first_name or "Unknown"

        image_base64 = None
        media_type = "text"
        media_description = ""
        has_image = False
        has_location = False

        # Handle location
        if isinstance(event.media, (MessageMediaGeo, MessageMediaGeoLive)):
            media_type = "location"
            has_location = True
            lat = event.media.geo.lat
            lon = event.media.geo.long
            media_description = f"Координаты: {lat:.4f}, {lon:.4f}"
            self.message_callback("location", {"sender": sender_name, "lat": lat, "lon": lon})

        # Handle image
        elif isinstance(event.media, MessageMediaPhoto):
            media_type = "image"
            has_image = True
            image_base64 = await self._download_image(event)
            if image_base64:
                media_description = await self.ai_client.vision(image_base64)
                self.message_callback("image", {"sender": sender_name, "desc": media_description})

        # Handle sticker
        elif event.media and hasattr(event.media, 'document'):
            doc = event.media.document
            if doc:
                is_sticker = any(isinstance(a, DocumentAttributeSticker) for a in doc.attributes)
                if is_sticker:
                    media_type = "sticker"
                    has_image = True
                    file_path = await self.client.download_media(doc, IMAGES_DIR)
                    try:
                        from PIL import Image
                        img = Image.open(file_path)
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                        import io
                        buf = io.BytesIO()
                        img.save(buf, format='JPEG', quality=85)
                        image_base64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
                    except:
                        with open(file_path, "rb") as f:
                            image_base64 = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
                    
                    if image_base64:
                        media_description = await self.ai_client.vision(image_base64)

        # Build message
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        enriched_text = text
        if media_description:
            enriched_text = f"[{media_type.upper()}: {media_description}]\n{text}"

        self.conversation_history[chat_id].append({"role": "user", "content": enriched_text})
        if len(self.conversation_history[chat_id]) > 20:
            self.conversation_history[chat_id] = self.conversation_history[chat_id][-20:]

        messages = [{"role": "system", "content": self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT)}]
        messages.extend(self.conversation_history[chat_id])

        self.message_callback("message", {
            "sender": sender_name, "text": enriched_text[:200], 
            "direction": "in", "has_image": has_image, "has_location": has_location
        })

        try:
            response = await self.ai_client.chat(messages, self.config.get("ai_model", "glm-4"))
            await event.reply(response)
            self.conversation_history[chat_id].append({"role": "assistant", "content": response})
            self.message_callback("message", {"sender": "AI", "text": response[:200], "direction": "out"})
        except Exception as e:
            self.message_callback("error", f"AI Error: {e}")


# ===========================================================================
# MAIN APPLICATION - Simple Clean UI
# ===========================================================================
class NinjaApp:
    """Main Application"""

    def __init__(self):
        self.config = self.load_config()
        self.message_queue = queue.Queue()
        self.messages: List[MessageLog] = []
        self.load_data()

        self.ai_client = AIClient(self.config)
        self.ai_proxy = AIProxyManager(self._on_proxy_status)
        self.bot = BotManager(self.config, self._on_bot_message, self.ai_client)

        self.message_count = len(self.messages)
        self.bot_username = ""

        self.setup_ui()
        self.root.after(100, self.process_messages)
        self.root.after(500, self.start_ai_proxy)

    def _on_proxy_status(self, status: str):
        self.message_queue.put(("proxy_status", status))

    def _on_bot_message(self, msg_type, data):
        self.message_queue.put((msg_type, data))

    def load_config(self) -> dict:
        cfg = DEFAULT_CONFIG.copy()
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except:
                pass
        return cfg

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def load_data(self):
        if LOGS_FILE.exists():
            try:
                with open(LOGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.messages = [MessageLog(**m) for m in data[-500:]]
            except:
                pass

    def save_data(self):
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in self.messages[-500:]], f, ensure_ascii=False)

    # =======================================================================
    # UI - Using ONLY pack() everywhere to avoid grid/pack conflicts
    # =======================================================================
    def setup_ui(self):
        if CTK_AVAILABLE:
            self.setup_ctk_ui()
        else:
            self.setup_tk_ui()

    def setup_ctk_ui(self):
        """Clean UI using only pack()"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("950x700")

        # Main container - all pack
        main = ctk.CTkFrame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Header
        header = ctk.CTkFrame(main, height=50)
        header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(header, text="🥷 Ninja Userbot", font=("", 20, "bold")).pack(side="left", padx=10)
        
        self.status_label = ctk.CTkLabel(header, text="⏹ Offline", text_color="gray")
        self.status_label.pack(side="right", padx=10)

        # Info
        info = ctk.CTkLabel(main, text="Telegram Userbot для Sog'lom taom - автоответчик с AI", 
                           text_color="#6b7280", font=("", 11))
        info.pack(anchor="w", pady=(0, 10))

        # Stats
        stats = ctk.CTkFrame(main)
        stats.pack(fill="x", pady=(0, 10))

        self.stat_labels = {}
        for text, color in [("Статус", "#10b981"), ("Сообщений", "#10b981"), ("Аккаунт", "#10b981")]:
            frame = ctk.CTkFrame(stats, width=120)
            frame.pack(side="left", padx=5, pady=5)
            frame.pack_propagate(False)
            
            val = ctk.CTkLabel(frame, text="0", font=("", 16, "bold"), text_color=color)
            val.pack(pady=(10, 0))
            ctk.CTkLabel(frame, text=text, font=("", 10), text_color="gray").pack()
            self.stat_labels[text] = val

        # Notebook for tabs
        if CTK_AVAILABLE:
            self.notebook = ctk.CTkTabview(main)
            self.notebook.pack(fill="both", expand=True)
            
            self.notebook.add("🎮 Управление")
            self.notebook.add("⚙️ Настройки")
            self.notebook.add("📋 Логи")
            
            self.setup_control_tab()
            self.setup_settings_tab()
            self.setup_logs_tab()
        else:
            self.setup_tk_ui()

    def setup_control_tab(self):
        """Control tab"""
        tab = self.notebook.tab("🎮 Управление")
        
        # Auth frame
        auth_frame = ctk.CTkFrame(tab)
        auth_frame.pack(fill="x", pady=10, padx=10)
        
        ctk.CTkLabel(auth_frame, text="📱 Авторизация Telegram", font=("", 14, "bold")).pack(pady=10)
        
        row1 = ctk.CTkFrame(auth_frame, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(row1, text="Телефон:", width=80).pack(side="left")
        self.phone_entry = ctk.CTkEntry(row1, width=200, placeholder_text="+998...")
        self.phone_entry.pack(side="left", padx=10)
        self.phone_entry.insert(0, self.config.get("phone", ""))
        ctk.CTkButton(row1, text="🔑 Войти", command=self.start_auth, width=100).pack(side="left")
        
        row2 = ctk.CTkFrame(auth_frame, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(row2, text="Код:", width=80).pack(side="left")
        self.code_entry = ctk.CTkEntry(row2, width=100, placeholder_text="12345")
        self.code_entry.pack(side="left", padx=10)
        ctk.CTkButton(row2, text="OK", command=self.submit_code, width=60).pack(side="left")

        # Control frame
        ctrl_frame = ctk.CTkFrame(tab)
        ctrl_frame.pack(fill="x", pady=10, padx=10)
        
        ctk.CTkLabel(ctrl_frame, text="🤖 Управление ботом", font=("", 14, "bold")).pack(pady=10)
        
        btn_row = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        btn_row.pack(pady=10)
        
        self.start_btn = ctk.CTkButton(btn_row, text="▶️ Запустить бота", command=self.start_bot,
                                       width=180, height=40, fg_color="#10b981")
        self.start_btn.pack(side="left", padx=10)
        
        self.stop_btn = ctk.CTkButton(btn_row, text="⏹️ Остановить", command=self.stop_bot,
                                      width=180, height=40, fg_color="#ef4444", state="disabled")
        self.stop_btn.pack(side="left", padx=10)

        # Logs preview
        logs_frame = ctk.CTkFrame(tab)
        logs_frame.pack(fill="both", expand=True, pady=10, padx=10)
        
        ctk.CTkLabel(logs_frame, text="📋 Логи", font=("", 12, "bold")).pack(anchor="w", padx=10, pady=5)
        
        self.logs_text = ctk.CTkTextbox(logs_frame, height=200)
        self.logs_text.pack(fill="both", expand=True, padx=10, pady=10)

    def setup_settings_tab(self):
        """Settings tab"""
        tab = self.notebook.tab("⚙️ Настройки")
        
        scroll = ctk.CTkScrollableFrame(tab)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Telegram
        ctk.CTkLabel(scroll, text="📱 Telegram", font=("", 14, "bold"), text_color="#10b981").pack(anchor="w", pady=(10, 5))
        
        r1 = ctk.CTkFrame(scroll, fg_color="transparent")
        r1.pack(fill="x", pady=3)
        ctk.CTkLabel(r1, text="API ID:", width=100).pack(side="left")
        self.api_id_entry = ctk.CTkEntry(r1, width=300)
        self.api_id_entry.pack(side="left", padx=10)
        self.api_id_entry.insert(0, self.config.get("api_id", ""))
        
        r2 = ctk.CTkFrame(scroll, fg_color="transparent")
        r2.pack(fill="x", pady=3)
        ctk.CTkLabel(r2, text="API Hash:", width=100).pack(side="left")
        self.api_hash_entry = ctk.CTkEntry(r2, width=300, show="*")
        self.api_hash_entry.pack(side="left", padx=10)
        self.api_hash_entry.insert(0, self.config.get("api_hash", ""))
        
        ctk.CTkLabel(r2, text="(my.telegram.org)", text_color="gray", font=("", 10)).pack(side="left")

        # Mistral
        ctk.CTkLabel(scroll, text="🤖 Mistral AI (Vision)", font=("", 14, "bold"), text_color="#10b981").pack(anchor="w", pady=(20, 5))
        
        r3 = ctk.CTkFrame(scroll, fg_color="transparent")
        r3.pack(fill="x", pady=3)
        ctk.CTkLabel(r3, text="API Key:", width=100).pack(side="left")
        self.mistral_key_entry = ctk.CTkEntry(r3, width=300, show="*")
        self.mistral_key_entry.pack(side="left", padx=10)
        self.mistral_key_entry.insert(0, self.config.get("mistral_key", ""))

        # Prompt
        ctk.CTkLabel(scroll, text="💬 Системный промпт", font=("", 14, "bold"), text_color="#10b981").pack(anchor="w", pady=(20, 5))
        
        self.prompt_text = ctk.CTkTextbox(scroll, height=250)
        self.prompt_text.pack(fill="x", pady=5)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        # Save
        ctk.CTkButton(scroll, text="💾 Сохранить", command=self.save_settings, width=150, height=40).pack(pady=20)

    def setup_logs_tab(self):
        """Full logs tab"""
        tab = self.notebook.tab("📋 Логи")
        
        self.full_logs = ctk.CTkTextbox(tab)
        self.full_logs.pack(fill="both", expand=True, padx=10, pady=10)

    def setup_tk_ui(self):
        """Fallback tkinter UI"""
        self.root = tk.Tk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("900x700")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Control tab
        control = ttk.Frame(notebook)
        notebook.add(control, text="Управление")
        
        # Auth
        auth_frame = ttk.LabelFrame(control, text="Авторизация")
        auth_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(auth_frame, text="Телефон:").grid(row=0, column=0, padx=5, pady=5)
        self.phone_entry = ttk.Entry(auth_frame, width=20)
        self.phone_entry.grid(row=0, column=1, padx=5, pady=5)
        self.phone_entry.insert(0, self.config.get("phone", ""))
        ttk.Button(auth_frame, text="Войти", command=self.start_auth).grid(row=0, column=2, padx=5)
        
        ttk.Label(auth_frame, text="Код:").grid(row=1, column=0, padx=5, pady=5)
        self.code_entry = ttk.Entry(auth_frame, width=10)
        self.code_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(auth_frame, text="OK", command=self.submit_code).grid(row=1, column=2, padx=5)

        # Control
        ctrl_frame = ttk.LabelFrame(control, text="Управление")
        ctrl_frame.pack(fill="x", padx=10, pady=10)
        
        self.start_btn = ttk.Button(ctrl_frame, text="▶️ Запустить", command=self.start_bot)
        self.start_btn.pack(side="left", padx=10, pady=10)
        self.stop_btn = ttk.Button(ctrl_frame, text="⏹️ Остановить", command=self.stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)

        # Logs
        self.logs_text = scrolledtext.ScrolledText(control)
        self.logs_text.pack(fill="both", expand=True, padx=10, pady=10)

        # Settings tab
        settings = ttk.Frame(notebook)
        notebook.add(settings, text="Настройки")
        
        ttk.Label(settings, text="API ID:").pack(anchor="w", padx=10, pady=5)
        self.api_id_entry = ttk.Entry(settings, width=40)
        self.api_id_entry.pack(anchor="w", padx=10)
        self.api_id_entry.insert(0, self.config.get("api_id", ""))
        
        ttk.Label(settings, text="API Hash:").pack(anchor="w", padx=10, pady=5)
        self.api_hash_entry = ttk.Entry(settings, width=40, show="*")
        self.api_hash_entry.pack(anchor="w", padx=10)
        self.api_hash_entry.insert(0, self.config.get("api_hash", ""))
        
        ttk.Label(settings, text="Системный промпт:").pack(anchor="w", padx=10, pady=10)
        self.prompt_text = scrolledtext.ScrolledText(settings, height=15)
        self.prompt_text.pack(fill="both", expand=True, padx=10)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        
        ttk.Button(settings, text="Сохранить", command=self.save_settings).pack(pady=10)

        self.status_label = ttk.Label(self.root, text="Готов")
        self.status_label.pack(fill="x", side="bottom")

    # =======================================================================
    # ACTIONS
    # =======================================================================
    def start_ai_proxy(self):
        self.add_log("System", "🚀 Запуск AI Proxy...", "system")
        threading.Thread(target=self.ai_proxy.start, daemon=True).start()

    def start_auth(self):
        phone = self.phone_entry.get().strip()
        if not phone:
            messagebox.showerror("Ошибка", "Введите номер телефона")
            return
        self.config["phone"] = phone
        self.save_config()
        self.bot.config = self.config
        self.bot.connect(phone, lambda s, d: self.message_queue.put(("auth", (s, d))))

    def submit_code(self):
        code = self.code_entry.get().strip()
        phone = self.phone_entry.get().strip()
        if not code:
            return
        self.bot.sign_in(phone, code, lambda s, d: self.message_queue.put(("auth", (s, d))))

    def start_bot(self):
        api_id = self.config.get("api_id", "")
        api_hash = self.config.get("api_hash", "")
        if not api_id or not api_hash:
            messagebox.showerror("Ошибка", "Настройте API ID и API Hash в настройках")
            return
        self.bot.config = self.config
        self.bot.start_bot(lambda s, d: self.message_queue.put(("bot_start", (s, d))))

    def stop_bot(self):
        self.bot.stop_bot()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="⏹ Offline", text_color="gray")
        self.add_log("System", "Бот остановлен", "system")

    def save_settings(self):
        self.config["api_id"] = self.api_id_entry.get().strip()
        self.config["api_hash"] = self.api_hash_entry.get().strip()
        self.config["mistral_key"] = self.mistral_key_entry.get().strip() if hasattr(self, 'mistral_key_entry') else ""
        self.config["system_prompt"] = self.prompt_text.get("1.0", "end").strip()
        self.save_config()
        self.bot.config = self.config
        self.ai_client.config = self.config
        self.add_log("System", "✅ Настройки сохранены", "system")
        messagebox.showinfo("Сохранено", "Настройки сохранены!")

    def add_log(self, sender: str, text: str, direction: str, has_image: bool = False, has_location: bool = False):
        log = MessageLog(
            id=datetime.now().strftime("%Y%m%d%H%M%S%f"),
            timestamp=datetime.now().strftime("%H:%M:%S"),
            sender=sender, text=text, direction=direction,
            has_image=has_image, has_location=has_location
        )
        self.messages.append(log)
        self.save_data()
        self.message_count = len(self.messages)
        
        # Update UI
        icon = "🖼️ " if has_image else "📍 " if has_location else ""
        line = f"[{log.timestamp}] {sender}: {icon}{text}\n"
        
        self.logs_text.insert("end", line)
        self.logs_text.see("end")
        
        if hasattr(self, 'full_logs'):
            self.full_logs.insert("end", line)
            self.full_logs.see("end")
        
        if "Статус" in self.stat_labels:
            self.stat_labels["Сообщений"].configure(text=str(self.message_count))

    def process_messages(self):
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()
                
                if msg_type == "proxy_status":
                    self.add_log("AI Proxy", data, "system")
                    
                elif msg_type == "auth":
                    status, info = data
                    if status == "authorized":
                        self.bot_username = info
                        self.stat_labels["Аккаунт"].configure(text=info[:12])
                        self.add_log("System", f"✅ Авторизован: {info}", "system")
                    elif status == "code_sent":
                        self.add_log("System", "📱 Код отправлен в Telegram", "system")
                        messagebox.showinfo("Код", "Код отправлен в Telegram!")
                    elif status == "signed_in":
                        self.bot_username = info
                        self.stat_labels["Аккаунт"].configure(text=info[:12])
                        self.add_log("System", f"✅ Вход выполнен: {info}", "system")
                    elif status == "error":
                        self.add_log("Error", info, "system")
                        messagebox.showerror("Ошибка", info)
                        
                elif msg_type == "bot_start":
                    status, info = data
                    if status == "started":
                        self.start_btn.configure(state="disabled")
                        self.stop_btn.configure(state="normal")
                        self.status_label.configure(text="🟢 Online", text_color="#10b981")
                        self.stat_labels["Статус"].configure(text="Running")
                        self.add_log("System", "✅ Бот запущен!", "system")
                    elif status == "error":
                        self.add_log("Error", info, "system")
                        messagebox.showerror("Ошибка", info)
                        
                elif msg_type == "message":
                    self.add_log(data["sender"], data["text"], data["direction"],
                                data.get("has_image", False), data.get("has_location", False))
                    
                elif msg_type == "location":
                    self.add_log(data["sender"], f"📍 {data['lat']:.4f}, {data['lon']:.4f}", "in", has_location=True)
                    
                elif msg_type == "image":
                    self.add_log(data["sender"], f"🖼️ {data['desc'][:100]}", "in", has_image=True)
                    
                elif msg_type == "error":
                    self.add_log("Error", str(data), "system")
                    
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_messages)

    def run(self):
        self.root.mainloop()


# ===========================================================================
# MAIN
# ===========================================================================
if __name__ == "__main__":
    app = NinjaApp()
    app.run()
