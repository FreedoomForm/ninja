"""
Ninja Userbot - Professional Native Windows Application
========================================================
Telegram Auto-Reply with AI using z-ai-web-sdk
Beautiful native Windows UI with all features
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
import queue
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
import webbrowser

# GUI imports
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False

# Telegram
from telethon import TelegramClient, events
from telethon.tl.types import User, MessageMediaPhoto, MessageMediaGeo

# HTTP client
import httpx

# ---------------------------------------------------------------------------
# Hide Console
# ---------------------------------------------------------------------------
if sys.platform == 'win32':
    try:
        import ctypes
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            ctypes.windll.user32.ShowWindow(console, 0)
    except:
        pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_NAME = "Ninja Userbot"
VERSION = "2.0"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Ninja"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
LEADS_FILE = DATA_DIR / "leads.json"
ORDERS_FILE = DATA_DIR / "orders.json"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# AI Proxy
AI_PROXY_PORT = 3000
AI_PROXY_URL = f"http://localhost:{AI_PROXY_PORT}/api/ai"

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class Message:
    id: str
    timestamp: str
    chat_id: int
    sender: str
    text: str
    direction: str  # in/out
    ai_response: bool = False

@dataclass
class Lead:
    id: str
    timestamp: str
    chat_id: int
    client_name: str
    summary: str
    status: str = "new"

@dataclass
class Order:
    id: str
    chat_id: int
    client_name: str
    phone: str = ""
    address: str = ""
    calories: str = ""
    price: int = 0
    status: str = "pending"

# ---------------------------------------------------------------------------
# Company Configuration
# ---------------------------------------------------------------------------
COMPANY_INFO = """
КОМПАНИЯ: Sog'lom taom (Соғлом таом) - здоровое питание с доставкой
ЛОКАЦИЯ: Ташкент, Сергели район
ГРАФИК: пн-пт, шанба - день уборки

ПАКЕТЫ: Классик, Индивидуал, Диабет

ЦЕНЫ:
- 1000–1200 ккал — 84 000 сум
- 1400–1600 ккал — 98 000 сум
- 1800–2000 ккал — 112 000 сум
- 2200–2500 ккал — 126 000 сум

ДОСТАВКА: 17:00–22:00
ЗАКАЗ: До 21:00 за день до доставки
"""

DEFAULT_SYSTEM_PROMPT = """Ты Бахром, 35-летний сотрудник компании Sog'lom taom из Ташкента.
Отвечаешь на сообщения клиентов в Telegram дружелюбно и профессионально.
Общаешься на узбекском и русском языках.
Используешь "Сиз" для новых клиентов, "Сен" для постоянных.

""" + COMPANY_INFO

DEFAULT_CONFIG = {
    "api_id": "36244324",
    "api_hash": "15657d847ab4b8ae111ade8e2cbca51f",
    "phone": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "ai_model": "glm-4",
}

# ---------------------------------------------------------------------------
# AI Proxy Manager
# ---------------------------------------------------------------------------
class AIProxyManager:
    """Manages the AI Proxy server (Next.js with z-ai-web-sdk)"""

    def __init__(self, proxy_dir: Path, status_callback=None):
        self.proxy_dir = proxy_dir
        self.status_callback = status_callback
        self.process = None
        self.running = False

    def is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return False
        except:
            return True

    def check_api_available(self) -> bool:
        """Check if AI API is responding"""
        try:
            import httpx
            r = httpx.get(f"http://localhost:{AI_PROXY_PORT}/api/ai", timeout=2)
            return r.status_code == 200
        except:
            return False

    def start(self) -> bool:
        """Start the AI Proxy server"""
        if self.is_port_in_use(AI_PROXY_PORT) and self.check_api_available():
            if self.status_callback:
                self.status_callback("✅ AI Proxy уже запущен")
            return True

        if not self.proxy_dir.exists():
            if self.status_callback:
                self.status_callback(f"❌ AI Proxy не найден: {self.proxy_dir}")
            return False

        if self.status_callback:
            self.status_callback("🚀 Запуск AI Proxy...")

        try:
            # Check for standalone build (server.js)
            server_js = self.proxy_dir / "server.js"
            if server_js.exists():
                # Use standalone server
                cmd = ["node", "server.js"]
            else:
                # Use npm (development/regular build)
                cmd = ["npm", "run", "start"]

            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.proxy_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Wait for server to start
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
        """Stop the AI Proxy server"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
        self.running = False

# ---------------------------------------------------------------------------
# AI Client
# ---------------------------------------------------------------------------
class AIClient:
    """Client for AI API calls"""

    def __init__(self, base_url: str = AI_PROXY_URL):
        self.base_url = base_url

    async def chat(self, messages: list, model: str = "glm-4") -> str:
        """Send chat completion request"""
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.base_url,
                json={
                    "messages": messages,
                    "model": model,
                    "temperature": 0.7,
                    "max_tokens": 1000,
                }
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                raise Exception(f"AI API Error: {response.status_code}")

# ---------------------------------------------------------------------------
# Telegram Bot Manager
# ---------------------------------------------------------------------------
class BotManager:
    """Manages Telegram client with single event loop"""

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
        self.me = None

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
        self.client = TelegramClient(
            str(SESSION_PATH),
            int(self.config.get("api_id", "0")),
            self.config.get("api_hash", "")
        )
        await self.client.connect()

    def connect(self, phone: str, callback):
        async def _connect():
            try:
                await self._create_client()
                if await self.client.is_user_authorized():
                    self.me = await self.client.get_me()
                    callback("authorized", self.me.first_name if self.me else "")
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
                self.me = await self.client.get_me()
                callback("signed_in", self.me.first_name if self.me else "")
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

    async def _process_message(self, event, sender: User):
        chat_id = event.chat_id
        text = event.text or ""
        sender_name = sender.first_name or "Unknown"

        # Log incoming message
        self.message_callback("message", {
            "chat_id": chat_id,
            "sender": sender_name,
            "text": text,
            "direction": "in"
        })

        # Build conversation
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        self.conversation_history[chat_id].append({"role": "user", "content": text})

        messages = [{"role": "system", "content": self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT)}]
        messages.extend(self.conversation_history[chat_id][-15:])

        try:
            response = await self.ai_client.chat(
                messages,
                self.config.get("ai_model", "glm-4")
            )
            await event.reply(response)
            self.conversation_history[chat_id].append({"role": "assistant", "content": response})

            # Log outgoing message
            self.message_callback("message", {
                "chat_id": chat_id,
                "sender": "AI",
                "text": response,
                "direction": "out"
            })
        except Exception as e:
            self.message_callback("error", f"AI Error: {e}")


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
class NinjaApp:
    """Main Application with Professional Windows UI"""

    def __init__(self):
        self.config = self.load_config()
        self.message_queue = queue.Queue()

        # Data storage
        self.messages: List[Message] = []
        self.leads: List[Lead] = []
        self.orders: List[Order] = []
        self.load_data()

        # AI Client
        self.ai_client = AIClient()

        # AI Proxy Manager - look for ai-proxy next to EXE or in app directory
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE
            exe_dir = Path(sys.executable).parent
            proxy_dir = exe_dir / "ai-proxy"
        else:
            # Running as script
            proxy_dir = Path(__file__).parent.parent / "ai-proxy"

        self.ai_proxy = AIProxyManager(proxy_dir, self._on_proxy_status)

        # Bot Manager
        self.bot = BotManager(self.config, self._on_bot_message, self.ai_client)

        # Statistics
        self.message_count = 0
        self.lead_count = 0

        # Create UI
        self.setup_ui()

        # Start message processor
        self.root.after(100, self.process_messages)

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
                    self.messages = [Message(**m) for m in data[-500:]]
            except:
                pass

        if LEADS_FILE.exists():
            try:
                with open(LEADS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.leads = [Lead(**l) for l in data]
            except:
                pass

    def save_data(self):
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in self.messages[-500:]], f, indent=2, ensure_ascii=False)

        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(l) for l in self.leads], f, indent=2, ensure_ascii=False)

    # ========================================================================
    # UI Setup
    # ========================================================================
    def setup_ui(self):
        """Setup professional Windows UI"""
        if CTK_AVAILABLE:
            self.setup_ctk_ui()
        else:
            self.setup_tk_ui()

    def setup_ctk_ui(self):
        """Setup CustomTkinter UI (Modern Windows 11 style)"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        # Configure grid
        self.root.grid_columnconfigure(0, weight=0)  # Sidebar
        self.root.grid_columnconfigure(1, weight=1)  # Main content
        self.root.grid_rowconfigure(0, weight=1)

        # ===== LEFT SIDEBAR =====
        self.sidebar = ctk.CTkFrame(self.root, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Logo
        ctk.CTkLabel(
            self.sidebar,
            text="🥷 NINJA",
            font=("", 24, "bold")
        ).pack(pady=20)

        # Navigation buttons
        self.nav_buttons = {}
        nav_items = [
            ("🏠 Главная", "main"),
            ("💬 Сообщения", "messages"),
            ("👥 Лиды", "leads"),
            ("📦 Заказы", "orders"),
            ("⚙️ Настройки", "settings"),
        ]

        for text, key in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                command=lambda k=key: self.show_panel(k),
                height=45,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "#DCE4EE"),
                hover_color=("gray70", "gray30"),
                corner_radius=10
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = btn

        # Status section at bottom of sidebar
        self.status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        # AI Proxy Status
        self.proxy_status_var = ctk.StringVar(value="⏹️ AI Proxy: Остановлен")
        ctk.CTkLabel(
            self.status_frame,
            textvariable=self.proxy_status_var,
            font=("", 12)
        ).pack(anchor="w")

        # Bot Status
        self.bot_status_var = ctk.StringVar(value="⏹️ Бот: Остановлен")
        ctk.CTkLabel(
            self.status_frame,
            textvariable=self.bot_status_var,
            font=("", 12)
        ).pack(anchor="w", pady=5)

        # Stats
        self.stats_var = ctk.StringVar(value="📊 0 сообщений | 0 лидов")
        ctk.CTkLabel(
            self.status_frame,
            textvariable=self.stats_var,
            font=("", 12)
        ).pack(anchor="w")

        # ===== RIGHT CONTENT AREA =====
        self.content = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        # Create panels
        self.panels = {}
        self.setup_main_panel()
        self.setup_messages_panel()
        self.setup_leads_panel()
        self.setup_orders_panel()
        self.setup_settings_panel()

        # Show main panel
        self.show_panel("main")

    def setup_main_panel(self):
        """Main dashboard panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")

        # Title
        ctk.CTkLabel(
            panel,
            text="🏠 Главная панель",
            font=("", 28, "bold")
        ).pack(pady=20)

        # Auth Card
        auth_card = ctk.CTkFrame(panel)
        auth_card.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            auth_card,
            text="📱 Авторизация Telegram",
            font=("", 18, "bold")
        ).pack(pady=10)

        # Phone input
        phone_frame = ctk.CTkFrame(auth_card, fg_color="transparent")
        phone_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(phone_frame, text="Номер телефона:", width=150).pack(side="left")
        self.phone_entry = ctk.CTkEntry(phone_frame, width=250, placeholder_text="+998...")
        self.phone_entry.pack(side="left", padx=10)
        self.phone_entry.insert(0, self.config.get("phone", ""))

        self.auth_btn = ctk.CTkButton(
            auth_card,
            text="🔑 Войти в Telegram",
            command=self.start_auth,
            width=200,
            height=40
        )
        self.auth_btn.pack(pady=10)

        # Code input frame
        self.code_frame = ctk.CTkFrame(auth_card, fg_color="transparent")
        ctk.CTkLabel(self.code_frame, text="Код из Telegram:").pack(side="left")
        self.code_entry = ctk.CTkEntry(self.code_frame, width=100)
        self.code_entry.pack(side="left", padx=10)
        ctk.CTkButton(
            self.code_frame,
            text="OK",
            command=self.submit_code,
            width=60
        ).pack(side="left")

        # Control Card
        control_card = ctk.CTkFrame(panel)
        control_card.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            control_card,
            text="🤖 Управление ботом",
            font=("", 18, "bold")
        ).pack(pady=10)

        btn_frame = ctk.CTkFrame(control_card, fg_color="transparent")
        btn_frame.pack(pady=10)

        self.start_proxy_btn = ctk.CTkButton(
            btn_frame,
            text="🚀 Запустить AI Proxy",
            command=self.start_ai_proxy,
            width=200,
            height=45,
            fg_color="#1f6aa5",
            hover_color="#144870"
        )
        self.start_proxy_btn.pack(side="left", padx=10)

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="▶️ Запустить бота",
            command=self.start_bot,
            width=200,
            height=45,
            fg_color="#2ecc71",
            hover_color="#27ae60"
        )
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="⏹️ Остановить",
            command=self.stop_bot,
            width=200,
            height=45,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=10)

        # Quick Stats Cards
        stats_frame = ctk.CTkFrame(panel, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=20)

        # Messages stat
        msg_card = ctk.CTkFrame(stats_frame, width=150, height=100)
        msg_card.pack(side="left", padx=10, pady=5)
        msg_card.pack_propagate(False)

        ctk.CTkLabel(msg_card, text="💬", font=("", 30)).pack(pady=5)
        self.msg_count_label = ctk.CTkLabel(msg_card, text="0", font=("", 24, "bold"))
        self.msg_count_label.pack()
        ctk.CTkLabel(msg_card, text="Сообщений", font=("", 12)).pack()

        # Leads stat
        lead_card = ctk.CTkFrame(stats_frame, width=150, height=100)
        lead_card.pack(side="left", padx=10, pady=5)
        lead_card.pack_propagate(False)

        ctk.CTkLabel(lead_card, text="👥", font=("", 30)).pack(pady=5)
        self.lead_count_label = ctk.CTkLabel(lead_card, text="0", font=("", 24, "bold"))
        self.lead_count_label.pack()
        ctk.CTkLabel(lead_card, text="Лидов", font=("", 12)).pack()

        # Orders stat
        order_card = ctk.CTkFrame(stats_frame, width=150, height=100)
        order_card.pack(side="left", padx=10, pady=5)
        order_card.pack_propagate(False)

        ctk.CTkLabel(order_card, text="📦", font=("", 30)).pack(pady=5)
        self.order_count_label = ctk.CTkLabel(order_card, text="0", font=("", 24, "bold"))
        self.order_count_label.pack()
        ctk.CTkLabel(order_card, text="Заказов", font=("", 12)).pack()

        self.panels["main"] = panel

    def setup_messages_panel(self):
        """Messages panel with chat history"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=10)

        ctk.CTkLabel(
            header,
            text="💬 Сообщения",
            font=("", 24, "bold")
        ).pack(side="left", padx=20)

        ctk.CTkButton(
            header,
            text="🗑️ Очистить",
            command=self.clear_messages,
            width=100
        ).pack(side="right", padx=20)

        # Messages list
        self.messages_frame = ctk.CTkScrollableFrame(panel)
        self.messages_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.panels["messages"] = panel

    def setup_leads_panel(self):
        """Leads panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(
            panel,
            text="👥 Лиды",
            font=("", 24, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(
            panel,
            text="Здесь будут отображаться потенциальные клиенты",
            text_color="gray"
        ).pack()

        self.panels["leads"] = panel

    def setup_orders_panel(self):
        """Orders panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(
            panel,
            text="📦 Заказы",
            font=("", 24, "bold")
        ).pack(pady=20)

        ctk.CTkLabel(
            panel,
            text="Здесь будут отображаться заказы клиентов",
            text_color="gray"
        ).pack()

        self.panels["orders"] = panel

    def setup_settings_panel(self):
        """Settings panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        # Header
        ctk.CTkLabel(
            panel,
            text="⚙️ Настройки",
            font=("", 24, "bold")
        ).grid(row=0, column=0, pady=20, sticky="w", padx=20)

        # Settings content
        settings_frame = ctk.CTkScrollableFrame(panel)
        settings_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)

        # Model setting
        model_frame = ctk.CTkFrame(settings_frame)
        model_frame.pack(fill="x", pady=5)

        ctk.CTkLabel(
            model_frame,
            text="🤖 AI Модель:",
            font=("", 14)
        ).pack(side="left", padx=10)

        self.model_entry = ctk.CTkEntry(model_frame, width=200)
        self.model_entry.pack(side="left", padx=10)
        self.model_entry.insert(0, self.config.get("ai_model", "glm-4"))

        # System prompt
        prompt_frame = ctk.CTkFrame(settings_frame)
        prompt_frame.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(
            prompt_frame,
            text="📝 Системный промпт:",
            font=("", 14)
        ).pack(anchor="w", padx=10, pady=5)

        self.prompt_text = ctk.CTkTextbox(prompt_frame, height=300)
        self.prompt_text.pack(fill="both", expand=True, padx=10, pady=5)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        # Save button
        ctk.CTkButton(
            settings_frame,
            text="💾 Сохранить настройки",
            command=self.save_settings,
            width=200,
            height=40
        ).pack(pady=20)

        self.panels["settings"] = panel

    def show_panel(self, key: str):
        """Show a specific panel"""
        # Update nav buttons
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")

        # Show panel
        for k, panel in self.panels.items():
            if k == key:
                panel.grid(row=0, column=0, sticky="nsew")
            else:
                panel.grid_remove()

    # ========================================================================
    # Fallback Tkinter UI
    # ========================================================================
    def setup_tk_ui(self):
        """Fallback to standard Tkinter"""
        self.root = tk.Tk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("1000x700")

        # Notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Main tab
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Главная")
        self.setup_tk_main_tab(main_tab)

        # Messages tab
        messages_tab = ttk.Frame(notebook)
        notebook.add(messages_tab, text="Сообщения")
        self.setup_tk_messages_tab(messages_tab)

        # Settings tab
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="Настройки")
        self.setup_tk_settings_tab(settings_tab)

        # Status bar
        self.status_var = tk.StringVar(value="Готов")
        ttk.Label(self.root, textvariable=self.status_var).pack(fill="x", side="bottom")

    def setup_tk_main_tab(self, parent):
        # Auth
        auth_frame = ttk.LabelFrame(parent, text="Авторизация")
        auth_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(auth_frame, text="Телефон:").grid(row=0, column=0, padx=5, pady=5)
        self.phone_entry = ttk.Entry(auth_frame, width=20)
        self.phone_entry.grid(row=0, column=1, padx=5, pady=5)
        self.phone_entry.insert(0, self.config.get("phone", ""))
        self.auth_btn = ttk.Button(auth_frame, text="Войти", command=self.start_auth)
        self.auth_btn.grid(row=0, column=2, padx=5, pady=5)

        code_frame = ttk.Frame(auth_frame)
        code_frame.grid(row=1, column=0, columnspan=3, pady=5)
        ttk.Label(code_frame, text="Код:").pack(side="left")
        self.code_entry = ttk.Entry(code_frame, width=10)
        self.code_entry.pack(side="left", padx=5)
        ttk.Button(code_frame, text="OK", command=self.submit_code).pack(side="left")

        # Control
        control_frame = ttk.LabelFrame(parent, text="Управление")
        control_frame.pack(fill="x", padx=10, pady=10)

        self.start_btn = ttk.Button(control_frame, text="▶️ Запустить бота", command=self.start_bot)
        self.start_btn.pack(side="left", padx=10, pady=10)

        self.stop_btn = ttk.Button(control_frame, text="⏹️ Остановить", command=self.stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)

    def setup_tk_messages_tab(self, parent):
        self.messages_text = scrolledtext.ScrolledText(parent)
        self.messages_text.pack(fill="both", expand=True, padx=5, pady=5)

    def setup_tk_settings_tab(self, parent):
        ttk.Label(parent, text="AI Модель:").pack(anchor="w", padx=10, pady=5)
        self.model_entry = ttk.Entry(parent, width=30)
        self.model_entry.pack(anchor="w", padx=10, pady=5)
        self.model_entry.insert(0, self.config.get("ai_model", "glm-4"))

        ttk.Label(parent, text="Системный промпт:").pack(anchor="w", padx=10, pady=5)
        self.prompt_text = scrolledtext.ScrolledText(parent, height=20)
        self.prompt_text.pack(fill="both", expand=True, padx=10, pady=5)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        ttk.Button(parent, text="Сохранить", command=self.save_settings).pack(pady=10)

    # ========================================================================
    # Actions
    # ========================================================================
    def start_ai_proxy(self):
        """Start AI Proxy server"""
        threading.Thread(target=self.ai_proxy.start, daemon=True).start()

    def start_auth(self):
        """Start Telegram authentication"""
        phone = self.phone_entry.get().strip()
        if not phone:
            messagebox.showerror("Ошибка", "Введите номер телефона")
            return

        self.config["phone"] = phone
        self.save_config()

        def callback(status, data):
            self.message_queue.put(("auth", f"{status}:{data}"))

        self.bot.connect(phone, callback)

    def submit_code(self):
        """Submit verification code"""
        code = self.code_entry.get().strip()
        if not code:
            return

        phone = self.config.get("phone", "")

        def callback(status, data):
            self.message_queue.put(("auth", f"{status}:{data}"))

        self.bot.sign_in(phone, code, callback)

    def start_bot(self):
        """Start the bot"""
        def callback(status, data):
            self.message_queue.put(("bot", f"{status}:{data}"))

        self.bot.start_bot(callback)

        if CTK_AVAILABLE:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
        else:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")

        self.bot_status_var.set("✅ Бот: Работает")

    def stop_bot(self):
        """Stop the bot"""
        self.bot.stop_bot()

        if CTK_AVAILABLE:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        else:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

        self.bot_status_var.set("⏹️ Бот: Остановлен")

    def save_settings(self):
        self.config["ai_model"] = self.model_entry.get()

        if CTK_AVAILABLE:
            self.config["system_prompt"] = self.prompt_text.get("1.0", "end-1c")
        else:
            self.config["system_prompt"] = self.prompt_text.get("1.0", tk.END).strip()

        self.save_config()
        messagebox.showinfo("Сохранено", "Настройки успешно сохранены!")

    def clear_messages(self):
        self.messages.clear()
        self.save_data()
        if CTK_AVAILABLE:
            for widget in self.messages_frame.winfo_children():
                widget.destroy()

    def add_message_to_ui(self, msg_data: dict):
        """Add a message to the UI"""
        if not CTK_AVAILABLE:
            text = f"[{datetime.now().strftime('%H:%M:%S')}] {msg_data['sender']}: {msg_data['text'][:100]}\n"
            self.messages_text.insert(tk.END, text)
            self.messages_text.see(tk.END)
            return

        # Create message card
        card = ctk.CTkFrame(self.messages_frame)
        card.pack(fill="x", pady=2, padx=5)

        direction = msg_data.get("direction", "in")
        color = "#2ecc71" if direction == "out" else "#3498db"

        # Time
        time_label = ctk.CTkLabel(
            card,
            text=datetime.now().strftime("%H:%M:%S"),
            font=("", 10),
            text_color="gray"
        )
        time_label.pack(anchor="w", padx=10, pady=2)

        # Sender with color
        sender_label = ctk.CTkLabel(
            card,
            text=f"{'📤' if direction == 'out' else '📥'} {msg_data['sender']}",
            font=("", 12, "bold"),
            text_color=color
        )
        sender_label.pack(anchor="w", padx=10, pady=2)

        # Text
        text_label = ctk.CTkLabel(
            card,
            text=msg_data['text'][:200] + ("..." if len(msg_data['text']) > 200 else ""),
            font=("", 11),
            wraplength=600,
            justify="left"
        )
        text_label.pack(anchor="w", padx=10, pady=5)

    def update_stats(self):
        """Update statistics display"""
        self.stats_var.set(f"📊 {self.message_count} сообщений | {self.lead_count} лидов")

        if CTK_AVAILABLE:
            self.msg_count_label.configure(text=str(self.message_count))
            self.lead_count_label.configure(text=str(self.lead_count))

    def process_messages(self):
        """Process messages from background threads"""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()

                if msg_type == "proxy_status":
                    self.proxy_status_var.set(f"AI Proxy: {data}")

                elif msg_type == "auth":
                    status, info = data.split(":", 1) if ":" in data else (data, "")
                    if status == "authorized":
                        messagebox.showinfo("Успех", f"Уже авторизован как {info}!")
                        self.bot_status_var.set(f"✅ Авторизован: {info}")
                    elif status == "code_sent":
                        messagebox.showinfo("Код", "Введите код из Telegram")
                        if CTK_AVAILABLE:
                            self.code_frame.pack(pady=5)
                    elif status == "signed_in":
                        messagebox.showinfo("Успех", f"Авторизация успешна! {info}")
                        self.bot_status_var.set(f"✅ Авторизован: {info}")
                    elif status == "error":
                        messagebox.showerror("Ошибка", info)

                elif msg_type == "bot":
                    status, info = data.split(":", 1) if ":" in data else (data, "")
                    if status == "started":
                        self.bot_status_var.set("✅ Бот: Работает")
                    elif status == "error":
                        messagebox.showerror("Ошибка бота", info)

                elif msg_type == "message":
                    self.message_count += 1
                    self.add_message_to_ui(data)
                    self.update_stats()

                elif msg_type == "error":
                    print(f"Error: {data}")

        except queue.Empty:
            pass

        self.root.after(100, self.process_messages)

    def run(self):
        """Run the application"""
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main():
    app = NinjaApp()
    app.run()


if __name__ == "__main__":
    main()
