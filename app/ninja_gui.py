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
import shutil
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
VERSION = "4.1"

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

AI_PROXY_PORT = 3000

# ===========================================================================
# COMPANY INFO
# ===========================================================================
COMPANY_INFO = """
КОМПАНИЯ: Sog'lom taom - здоровое питание с доставкой
ЛОКАЦИЯ: Ташкент, Сергели район

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
# AI PROXY MANAGER
# ===========================================================================
class AIProxyManager:
    """Manages the AI Proxy server with proper Node.js detection"""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self.process = None
        self.running = False
        self.proxy_dir = None
        self.node_exe = None
        self._find_paths()

    def _find_paths(self):
        """Find Node.js and ai-proxy directory"""
        # Find Node.js
        node_paths = []
        
        if getattr(sys, 'frozen', False):
            # Running as EXE
            exe_dir = Path(sys.executable).parent
            node_paths.append(exe_dir / "node" / "node.exe")
            node_paths.append(exe_dir / "node-portable" / "node.exe")
            node_paths.append(exe_dir.parent / "node" / "node.exe")
        
        # System Node.js
        node_paths.append(Path("node.exe"))
        node_paths.append(Path("node"))
        
        # Check PATH
        node_in_path = shutil.which("node")
        if node_in_path:
            node_paths.append(Path(node_in_path))
        
        for path in node_paths:
            if path and path.exists():
                self.node_exe = str(path)
                break
        
        # Find ai-proxy directory
        proxy_paths = []
        
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            proxy_paths.append(exe_dir / "ai-proxy")
            proxy_paths.append(exe_dir.parent / "ai-proxy")
        
        proxy_paths.append(Path(__file__).parent.parent / "ai-proxy")
        proxy_paths.append(Path.cwd() / "ai-proxy")
        
        for path in proxy_paths:
            if path.exists() and (path / "package.json").exists():
                self.proxy_dir = path
                break

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

        # Check Node.js
        if not self.node_exe:
            if self.status_callback:
                self.status_callback("⚠️ Node.js не найден - проверьте установку")
            return False

        # Check proxy directory
        if not self.proxy_dir:
            if self.status_callback:
                self.status_callback("⚠️ ai-proxy папка не найдена")
            return False

        if self.status_callback:
            self.status_callback(f"🚀 Запуск AI Proxy (node: {self.node_exe})...")

        try:
            # Check if standalone server exists
            server_js = self.proxy_dir / "server.js"
            standalone = self.proxy_dir / ".next" / "standalone" / "server.js"
            
            if standalone.exists():
                # Use standalone build
                cmd = [self.node_exe, str(standalone)]
                cwd = standalone.parent
            elif server_js.exists():
                cmd = [self.node_exe, "server.js"]
                cwd = self.proxy_dir
            else:
                # Try npm
                npm_cmd = shutil.which("npm") or "npm"
                cmd = [npm_cmd, "run", "start"]
                cwd = self.proxy_dir

            self.process = subprocess.Popen(
                cmd, cwd=str(cwd),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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
                
                # Check if process died
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                    if self.status_callback:
                        self.status_callback(f"❌ AI Proxy упал: {stderr[:100]}")
                    return False

            if self.status_callback:
                self.status_callback("❌ AI Proxy не запустился за 30 сек")
            return False

        except Exception as e:
            if self.status_callback:
                self.status_callback(f"❌ Ошибка: {str(e)[:100]}")
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

        messages_with_time = messages.copy()
        if messages_with_time and messages_with_time[0]["role"] == "system":
            messages_with_time[0] = {
                "role": "system", 
                "content": messages_with_time[0]["content"] + time_context
            }

        # Try proxy
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.proxy_url,
                    json={"messages": messages_with_time, "model": model, "temperature": 0.7}
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise Exception(f"AI API ошибка: {e}")

    async def vision(self, image_base64: str) -> str:
        """Analyze image"""
        mistral_key = self.config.get("mistral_key", "")

        # Try Mistral Vision API if key available
        if mistral_key:
            try:
                url = "https://api.mistral.ai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"}
                
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Опиши изображение кратко. Если чек - сумма, если стикер - эмоция."},
                        {"type": "image_url", "image_url": {"url": image_base64}}
                    ]
                }]

                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.post(url, headers=headers, 
                                         json={"model": "pixtral-12b-2409", "messages": messages})
                    if r.status_code == 200:
                        return r.json()["choices"][0]["message"]["content"].strip()
            except:
                pass

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
        self._client_ready = False

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
            return True
        api_id = self.config.get("api_id", "")
        api_hash = self.config.get("api_hash", "")
        if not api_id or not api_hash:
            raise Exception("Настройте API ID и API Hash")
        self.client = TelegramClient(str(SESSION_PATH), int(api_id), api_hash)
        await self.client.connect()
        self._client_ready = True
        return True

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
                if not self.client:
                    callback("error", "Сначала нажмите 'Войти'")
                    return
                await self.client.sign_in(phone, code, phone_code_hash=self.phone_code_hash)
                me = await self.client.get_me()
                callback("signed_in", me.first_name if me else "")
            except Exception as e:
                callback("error", str(e))
        asyncio.run_coroutine_threadsafe(_sign_in(), self.loop)

    def start_bot(self, callback):
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
                        return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
            return None
        except:
            return None

    async def _process_message(self, event, sender: User):
        chat_id = event.chat_id
        text = event.text or ""
        sender_name = sender.first_name or "Unknown"

        image_base64 = None
        media_description = ""
        has_image = False
        has_location = False

        # Handle location
        if isinstance(event.media, (MessageMediaGeo, MessageMediaGeoLive)):
            has_location = True
            lat = event.media.geo.lat
            lon = event.media.geo.long
            media_description = f"Координаты: {lat:.4f}, {lon:.4f}"
            self.message_callback("location", {"sender": sender_name, "lat": lat, "lon": lon})

        # Handle image
        elif isinstance(event.media, MessageMediaPhoto):
            has_image = True
            image_base64 = await self._download_image(event)
            if image_base64:
                media_description = await self.ai_client.vision(image_base64)
                self.message_callback("image", {"sender": sender_name, "desc": media_description})

        # Build message
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        enriched_text = f"[MEDIA: {media_description}]\n{text}" if media_description else text

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
            response = await self.ai_client.chat(messages)
            await event.reply(response)
            self.conversation_history[chat_id].append({"role": "assistant", "content": response})
            self.message_callback("message", {"sender": "AI", "text": response[:200], "direction": "out"})
        except Exception as e:
            self.message_callback("error", f"AI: {e}")


# ===========================================================================
# MAIN APPLICATION
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

    def setup_ui(self):
        if CTK_AVAILABLE:
            self.setup_ctk_ui()
        else:
            self.setup_tk_ui()

    def setup_ctk_ui(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("900x650")

        main = ctk.CTkFrame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Header
        header = ctk.CTkFrame(main, height=50)
        header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header, text="🥷 Ninja Userbot", font=("", 18, "bold")).pack(side="left", padx=10)
        self.status_label = ctk.CTkLabel(header, text="⏹ Offline", text_color="gray")
        self.status_label.pack(side="right", padx=10)

        # Stats
        stats = ctk.CTkFrame(main)
        stats.pack(fill="x", pady=(0, 10))
        self.stat_labels = {}
        for text in ["Статус", "Сообщений", "Аккаунт"]:
            f = ctk.CTkFrame(stats, width=120)
            f.pack(side="left", padx=5, pady=5)
            f.pack_propagate(False)
            v = ctk.CTkLabel(f, text="0" if text != "Статус" else "Stopped", font=("", 14, "bold"), text_color="#10b981")
            v.pack(pady=(10, 0))
            ctk.CTkLabel(f, text=text, font=("", 10), text_color="gray").pack()
            self.stat_labels[text] = v

        # Tabs
        self.notebook = ctk.CTkTabview(main)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.add("🎮 Управление")
        self.notebook.add("⚙️ Настройки")
        
        self.setup_control_tab()
        self.setup_settings_tab()

    def setup_control_tab(self):
        tab = self.notebook.tab("🎮 Управление")
        
        # Auth
        auth = ctk.CTkFrame(tab)
        auth.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(auth, text="📱 Авторизация Telegram", font=("", 13, "bold")).pack(pady=10)
        
        r1 = ctk.CTkFrame(auth, fg_color="transparent")
        r1.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r1, text="Телефон:", width=80).pack(side="left")
        self.phone_entry = ctk.CTkEntry(r1, width=180, placeholder_text="+998...")
        self.phone_entry.pack(side="left", padx=10)
        self.phone_entry.insert(0, self.config.get("phone", ""))
        ctk.CTkButton(r1, text="🔑 Войти", command=self.start_auth, width=90).pack(side="left")
        
        r2 = ctk.CTkFrame(auth, fg_color="transparent")
        r2.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(r2, text="Код:", width=80).pack(side="left")
        self.code_entry = ctk.CTkEntry(r2, width=80, placeholder_text="12345")
        self.code_entry.pack(side="left", padx=10)
        ctk.CTkButton(r2, text="OK", command=self.submit_code, width=50).pack(side="left")

        # Control
        ctrl = ctk.CTkFrame(tab)
        ctrl.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(ctrl, text="🤖 Управление ботом", font=("", 13, "bold")).pack(pady=10)
        
        btns = ctk.CTkFrame(ctrl, fg_color="transparent")
        btns.pack(pady=10)
        self.start_btn = ctk.CTkButton(btns, text="▶️ Запустить", command=self.start_bot, width=150, height=40, fg_color="#10b981")
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = ctk.CTkButton(btns, text="⏹️ Остановить", command=self.stop_bot, width=150, height=40, fg_color="#ef4444", state="disabled")
        self.stop_btn.pack(side="left", padx=10)

        # Logs
        logs = ctk.CTkFrame(tab)
        logs.pack(fill="both", expand=True, pady=10, padx=10)
        ctk.CTkLabel(logs, text="📋 Логи", font=("", 12, "bold")).pack(anchor="w", padx=10, pady=5)
        self.logs_text = ctk.CTkTextbox(logs, height=150)
        self.logs_text.pack(fill="both", expand=True, padx=10, pady=5)

    def setup_settings_tab(self):
        tab = self.notebook.tab("⚙️ Настройки")
        scroll = ctk.CTkScrollableFrame(tab)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # Telegram
        ctk.CTkLabel(scroll, text="📱 Telegram (my.telegram.org)", font=("", 13, "bold"), text_color="#10b981").pack(anchor="w", pady=(10, 5))
        
        r1 = ctk.CTkFrame(scroll, fg_color="transparent")
        r1.pack(fill="x", pady=3)
        ctk.CTkLabel(r1, text="API ID:", width=100).pack(side="left")
        self.api_id_entry = ctk.CTkEntry(r1, width=280)
        self.api_id_entry.pack(side="left", padx=10)
        self.api_id_entry.insert(0, self.config.get("api_id", ""))
        
        r2 = ctk.CTkFrame(scroll, fg_color="transparent")
        r2.pack(fill="x", pady=3)
        ctk.CTkLabel(r2, text="API Hash:", width=100).pack(side="left")
        self.api_hash_entry = ctk.CTkEntry(r2, width=280, show="*")
        self.api_hash_entry.pack(side="left", padx=10)
        self.api_hash_entry.insert(0, self.config.get("api_hash", ""))

        # Mistral
        ctk.CTkLabel(scroll, text="🤖 Mistral Vision API (опционально)", font=("", 13, "bold"), text_color="#10b981").pack(anchor="w", pady=(20, 5))
        r3 = ctk.CTkFrame(scroll, fg_color="transparent")
        r3.pack(fill="x", pady=3)
        ctk.CTkLabel(r3, text="API Key:", width=100).pack(side="left")
        self.mistral_key_entry = ctk.CTkEntry(r3, width=280, show="*")
        self.mistral_key_entry.pack(side="left", padx=10)
        self.mistral_key_entry.insert(0, self.config.get("mistral_key", ""))

        # Prompt
        ctk.CTkLabel(scroll, text="💬 Системный промпт", font=("", 13, "bold"), text_color="#10b981").pack(anchor="w", pady=(20, 5))
        self.prompt_text = ctk.CTkTextbox(scroll, height=200)
        self.prompt_text.pack(fill="x", pady=5)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        ctk.CTkButton(scroll, text="💾 Сохранить", command=self.save_settings, width=140, height=35).pack(pady=15)

    def setup_tk_ui(self):
        self.root = tk.Tk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("850x600")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        control = ttk.Frame(notebook)
        notebook.add(control, text="Управление")
        
        auth = ttk.LabelFrame(control, text="Авторизация")
        auth.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(auth, text="Телефон:").grid(row=0, column=0, padx=5, pady=5)
        self.phone_entry = ttk.Entry(auth, width=20)
        self.phone_entry.grid(row=0, column=1, padx=5, pady=5)
        self.phone_entry.insert(0, self.config.get("phone", ""))
        ttk.Button(auth, text="Войти", command=self.start_auth).grid(row=0, column=2, padx=5)
        
        ttk.Label(auth, text="Код:").grid(row=1, column=0, padx=5, pady=5)
        self.code_entry = ttk.Entry(auth, width=10)
        self.code_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(auth, text="OK", command=self.submit_code).grid(row=1, column=2, padx=5)

        ctrl = ttk.LabelFrame(control, text="Управление")
        ctrl.pack(fill="x", padx=10, pady=10)
        self.start_btn = ttk.Button(ctrl, text="▶️ Запустить", command=self.start_bot)
        self.start_btn.pack(side="left", padx=10, pady=10)
        self.stop_btn = ttk.Button(ctrl, text="⏹️ Остановить", command=self.stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)

        self.logs_text = scrolledtext.ScrolledText(control)
        self.logs_text.pack(fill="both", expand=True, padx=10, pady=10)

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
        
        ttk.Label(settings, text="Промпт:").pack(anchor="w", padx=10, pady=10)
        self.prompt_text = scrolledtext.ScrolledText(settings, height=12)
        self.prompt_text.pack(fill="both", expand=True, padx=10)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        
        ttk.Button(settings, text="Сохранить", command=self.save_settings).pack(pady=10)

        self.status_label = ttk.Label(self.root, text="Готов")
        self.status_label.pack(fill="x", side="bottom")

    # Actions
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
            messagebox.showerror("Ошибка", "Настройте API ID и API Hash")
            return
        self.bot.config = self.config
        self.bot.start_bot(lambda s, d: self.message_queue.put(("bot_start", (s, d))))

    def stop_bot(self):
        self.bot.stop_bot()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="⏹ Offline")
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
        
        icon = "🖼️ " if has_image else "📍 " if has_location else ""
        line = f"[{log.timestamp}] {sender}: {icon}{text}\n"
        
        self.logs_text.insert("end", line)
        self.logs_text.see("end")
        
        if "Сообщений" in self.stat_labels:
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
                        self.add_log("System", f"✅ Вход: {info}", "system")
                    elif status == "error":
                        self.add_log("Error", info, "system")
                        messagebox.showerror("Ошибка", info)
                        
                elif msg_type == "bot_start":
                    status, info = data
                    if status == "started":
                        self.start_btn.configure(state="disabled")
                        self.stop_btn.configure(state="normal")
                        self.status_label.configure(text="🟢 Online")
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
                    self.add_log(data["sender"], f"🖼️ {data['desc'][:80]}", "in", has_image=True)
                    
                elif msg_type == "error":
                    self.add_log("Error", str(data), "system")
                    
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_messages)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = NinjaApp()
    app.run()
