"""
Ninja Userbot - Complete Native Windows Application
=====================================================
Telegram Auto-Reply with AI using z-ai-web-sdk
Full-featured: Images, Locations, Stickers, Orders, Leads
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
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Union
from dataclasses import dataclass, asdict, field

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
VERSION = "3.0"

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Ninja"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
LEADS_FILE = DATA_DIR / "leads.json"
ORDERS_FILE = DATA_DIR / "orders.json"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

AI_PROXY_PORT = 3000
AI_PROXY_URL = f"http://localhost:{AI_PROXY_PORT}/api/ai"
AI_VISION_URL = f"http://localhost:{AI_PROXY_PORT}/api/ai/vision"

# ===========================================================================
# COMPANY INFO
# ===========================================================================
COMPANY_INFO = """
КОМПАНИЯ: Sog'lom taom (Соғлом таом) - здоровое питание с доставкой
ЛОКАЦИЯ: Ташкент, Сергели район (ошхона)
ГРАФИК: 5-дневка (пн-пт), шанба - день уборки

ПАКЕТЫ:
- Классик: стандартное меню
- Индивидуал: можно исключить до 3 продуктов (аллергия/не нравится)
- Диабет: специальное меню для диабетиков

КАЛОРИИ И ЦЕНЫ:
- 1000–1200 ккал — 84 000 сум
- 1400–1600 ккал — 98 000 сум
- 1800–2000 ккал — 112 000 сум
- 2200–2500 ккал — 126 000 сум

ДОСТАВКА:
- Время: 17:00–22:00 по маршруту
- Дни: воскр, пн, вт, ср, чт, пт (2 пакета в пт для сб и вс)
- Заказ: До 21:00 за день до доставки

КАРТЫ:
- Humo: 9860010112421465
- Uzum: 4916990324223715
- Uzcard: 5614681209925290
- Получатель: Xodjimuratov Bahodir
"""

DEFAULT_SYSTEM_PROMPT = """Ты Бахром, 35-летний сотрудник компании Sog'lom taom из Ташкента.
Отвечаешь на сообщения клиентов в Telegram дружелюбно и профессионально.
Общаешься на узбекском и русском языках.
Используешь "Сиз" для новых клиентов, "Сен" для постоянных.

""" + COMPANY_INFO + """

ПОВЕДЕНИЕ ПРИ ПОЛУЧЕНИИ ЧЕКА:
1. Подтверди: "Хоп, чек келди. Текшириб чикишамиз..."
2. Спроси про дату доставки

ПОВЕДЕНИЕ ПРИ ПОЛУЧЕНИИ ЛОКАЦИИ:
1. Подтверди получение
2. Спроси точный адрес

ПОВЕДЕНИЕ ПРИ ОБСУЖДЕНИИ ДАТЫ ДОСТАВКИ:
1. Проверь что не суббота
2. Проверь что до 21:00
3. Подтверди дату
"""

DEFAULT_LEAD_PROMPT = """Анализируй переписку и определи, является ли это лидом.

УСПЕШНЫЙ ЛИД:
- Готов сделать заказ
- Прислал чек/локацию
- Спросил про оплату

Ответь в JSON:
{
  "is_lead": true/false,
  "client_name": "имя",
  "summary": "что нужно сделать"
}
"""

DEFAULT_CONFIG = {
    "api_id": "36244324",
    "api_hash": "15657d847ab4b8ae111ade8e2cbca51f",
    "phone": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "lead_prompt": DEFAULT_LEAD_PROMPT,
    "ai_model": "glm-4",
    "mistral_key": "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v",
    "couriers": "",
}

# Days mapping
DAYS_RU = {
    'monday': 'понедельник', 'tuesday': 'вторник', 'wednesday': 'среда',
    'thursday': 'четверг', 'friday': 'пятница', 'saturday': 'суббота', 'sunday': 'воскресенье'
}

# Price mapping
PRICE_MAP = {
    "1000-1200": 84000, "1400-1600": 98000,
    "1800-2000": 112000, "2200-2500": 126000,
}

# ===========================================================================
# DATA CLASSES
# ===========================================================================
@dataclass
class ClientOrder:
    chat_id: int
    client_name: str = ""
    phone: str = ""
    address: str = ""
    location_url: str = ""
    location_lat: float = 0.0
    location_lon: float = 0.0
    calories: str = ""
    package_type: str = "classic"
    days: int = 0
    delivery_date: str = ""
    price_per_day: int = 0
    total_price: int = 0
    payment_confirmed: bool = False
    check_image_path: str = ""
    notes: str = ""
    created_at: str = ""
    status: str = "pending"  # pending, confirmed, delivered

    def to_dict(self):
        return asdict(self)


@dataclass
class Lead:
    id: str
    timestamp: str
    chat_id: int
    client_name: str
    summary: str
    lead_type: str = "new"
    urgency: str = "medium"
    status: str = "new"


@dataclass  
class MessageLog:
    id: str
    timestamp: str
    chat_id: int
    sender: str
    text: str
    direction: str
    media_type: str = "text"
    media_description: str = ""


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================
def get_price_for_calories(calories: str) -> int:
    """Get price based on calorie range"""
    calories = calories.replace(" ", "").replace("ккал", "").replace("kcal", "")
    for range_str, price in PRICE_MAP.items():
        if range_str in calories or calories in range_str:
            return price
    try:
        cal_val = int(calories.replace("-", "").replace("–", ""))
        if cal_val <= 1200: return 84000
        elif cal_val <= 1600: return 98000
        elif cal_val <= 2000: return 112000
        else: return 126000
    except:
        return 0


def check_delivery_date_possible(requested_date: datetime) -> dict:
    """Check if delivery is possible on the requested date"""
    now = datetime.now()
    
    # Saturday - kitchen closed
    if requested_date.weekday() == 5:
        next_day = requested_date + timedelta(days=1)
        return {"possible": False, "reason": "В субботу кухня закрыта", "next_available": next_day.strftime("%d.%m.%Y")}
    
    # Check 21:00 deadline
    if requested_date.date() == (now + timedelta(days=1)).date():
        if now.hour >= 21:
            day_after = now + timedelta(days=2)
            if day_after.weekday() == 5:
                day_after += timedelta(days=1)
            return {"possible": False, "reason": "После 21:00 заказ на завтра невозможен", "next_available": day_after.strftime("%d.%m.%Y")}
    
    return {"possible": True, "reason": "OK", "next_available": requested_date.strftime("%d.%m.%Y")}


def parse_delivery_date(text: str) -> Optional[datetime]:
    """Parse delivery date from text"""
    text = text.lower()
    now = datetime.now()
    
    if any(w in text for w in ['сегодня', 'бугун', 'today', 'bugun']):
        return now
    if any(w in text for w in ['завтра', 'эртага', 'tomorrow', 'ertaga']):
        return now + timedelta(days=1)
    
    day_mapping = {
        'понедельник': 0, 'душанба': 0, 'пн': 0,
        'вторник': 1, 'сешанба': 1, 'вт': 1,
        'среда': 2, 'чоршанба': 2, 'ср': 2,
        'четверг': 3, 'пайшанба': 3, 'чт': 3,
        'пятница': 4, 'жума': 4, 'пт': 4,
        'суббота': 5, 'шанба': 5, 'сб': 5,
        'воскресенье': 6, 'якшанба': 6, 'вс': 6,
    }
    
    for day_name, day_num in day_mapping.items():
        if day_name in text:
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return now + timedelta(days=days_ahead)
    
    return None


# ===========================================================================
# AI PROXY MANAGER
# ===========================================================================
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
        try:
            r = httpx.get(f"http://localhost:{AI_PROXY_PORT}/api/ai", timeout=2)
            return r.status_code == 200
        except:
            return False

    def start(self) -> bool:
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
            server_js = self.proxy_dir / "server.js"
            cmd = ["node", "server.js"] if server_js.exists() else ["npm", "run", "start"]

            self.process = subprocess.Popen(
                cmd, cwd=str(self.proxy_dir),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

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
    """Client for AI API calls"""

    def __init__(self, base_url: str = AI_PROXY_URL, vision_url: str = AI_VISION_URL):
        self.base_url = base_url
        self.vision_url = vision_url

    async def chat(self, messages: list, model: str = "glm-4") -> str:
        """Send chat completion request"""
        # Add time context
        now = datetime.now()
        time_context = f"\n[ТЕКУЩЕЕ ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')} ({DAYS_RU.get(now.strftime('%A').lower(), '')})]"
        time_context += f"\n[ДЕДЛАЙН ЗАКАЗА: 21:00]"
        
        messages_with_time = messages.copy()
        if messages_with_time and messages_with_time[0]["role"] == "system":
            messages_with_time[0] = {"role": "system", "content": messages_with_time[0]["content"] + time_context}

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.base_url,
                json={"messages": messages_with_time, "model": model, "temperature": 0.7, "max_tokens": 1000}
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            raise Exception(f"AI API Error: {response.status_code}")

    async def vision(self, image_base64: str, prompt: str = None) -> str:
        """Analyze image with Vision API"""
        if prompt is None:
            prompt = """Проанализируй это изображение.
Если это СТИКЕР - опиши эмоцию и настроение.
Если это ЧЕК - укажи сумму перевода.
Если это ЛОКАЦИЯ/КАРТА - опиши место.
Отвечай кратко (2-3 предложения)."""

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                response = await client.post(
                    self.vision_url,
                    json={"image_base64": image_base64, "prompt": prompt}
                )
                if response.status_code == 200:
                    return response.json().get("description", "изображение")
            except:
                pass
        return "изображение"


# ===========================================================================
# BOT MANAGER
# ===========================================================================
class BotManager:
    """Manages Telegram client with full features"""

    def __init__(self, config: dict, message_callback, ai_client: AIClient):
        self.config = config
        self.message_callback = message_callback
        self.ai_client = ai_client
        self.client: Optional[TelegramClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = False
        self.conversation_history: Dict[int, list] = {}
        self.orders: Dict[int, ClientOrder] = {}
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

    async def _download_image(self, event) -> Optional[str]:
        """Download image and return base64"""
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
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                    return f"data:{mime_type};base64,{base64_data}"
            return None
        except Exception as e:
            print(f"Error downloading image: {e}")
            return None

    async def _download_sticker(self, event) -> Optional[str]:
        """Download sticker and convert to JPEG"""
        try:
            if not event.media or not hasattr(event.media, 'document'):
                return None

            doc = event.media.document
            if not doc:
                return None

            is_sticker = False
            sticker_emoji = ""
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeSticker):
                    is_sticker = True
                    sticker_emoji = attr.alt or ""
                    break

            if not is_sticker:
                return None

            file_path = await self.client.download_media(doc, IMAGES_DIR)

            try:
                from PIL import Image
                img = Image.open(file_path)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                jpeg_path = str(file_path).replace('.webp', '.jpg')
                img.save(jpeg_path, 'JPEG', quality=85)
                with open(jpeg_path, "rb") as f:
                    image_data = f.read()
                try:
                    os.remove(file_path)
                    os.remove(jpeg_path)
                except:
                    pass
                base64_data = base64.b64encode(image_data).decode('utf-8')
                return f"data:image/jpeg;base64,{base64_data}"
            except ImportError:
                with open(file_path, "rb") as f:
                    image_data = f.read()
                try:
                    os.remove(file_path)
                except:
                    pass
                base64_data = base64.b64encode(image_data).decode('utf-8')
                return f"data:image/jpeg;base64,{base64_data}"

        except Exception as e:
            print(f"Error downloading sticker: {e}")
            return None

    async def _process_message(self, event, sender: User):
        """Process incoming message with all features"""
        chat_id = event.chat_id
        text = event.text or ""
        sender_name = sender.first_name or "Unknown"

        # Check for media
        image_base64 = None
        media_type = "text"
        media_description = ""
        location_lat = 0.0
        location_lon = 0.0

        # Handle location
        if isinstance(event.media, (MessageMediaGeo, MessageMediaGeoLive)):
            media_type = "location"
            location_lat = event.media.geo.lat
            location_lon = event.media.geo.long
            media_description = f"Координаты: {location_lat:.4f}, {location_lon:.4f}"
            location_url = f"https://maps.google.com/maps?q={location_lat},{location_lon}"
            self.message_callback("location", {
                "chat_id": chat_id, "sender": sender_name,
                "lat": location_lat, "lon": location_lon, "url": location_url
            })

        # Handle image
        elif isinstance(event.media, MessageMediaPhoto):
            media_type = "image"
            image_base64 = await self._download_image(event)
            if image_base64:
                # Use Vision API
                media_description = await self.ai_client.vision(image_base64)
                self.message_callback("image", {
                    "chat_id": chat_id, "sender": sender_name,
                    "description": media_description
                })

        # Handle sticker
        elif event.media and hasattr(event.media, 'document'):
            sticker_base64 = await self._download_sticker(event)
            if sticker_base64:
                media_type = "sticker"
                media_description = await self.ai_client.vision(sticker_base64, 
                    "Опиши этот стикер: какой персонаж, какую эмоцию выражает.")
                self.message_callback("sticker", {
                    "chat_id": chat_id, "sender": sender_name,
                    "description": media_description
                })

        # Build message for AI
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        # Add context to message
        enriched_text = text
        if media_description:
            enriched_text = f"[{media_type.upper()}: {media_description}]\n{text}"

        self.conversation_history[chat_id].append({"role": "user", "content": enriched_text})

        # Keep last 15 messages
        if len(self.conversation_history[chat_id]) > 15:
            self.conversation_history[chat_id] = self.conversation_history[chat_id][-15:]

        # Build messages for AI
        messages = [{"role": "system", "content": self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT)}]
        messages.extend(self.conversation_history[chat_id])

        # Notify UI
        self.message_callback("message", {
            "chat_id": chat_id, "sender": sender_name,
            "text": enriched_text[:200], "direction": "in", "media_type": media_type
        })

        try:
            response = await self.ai_client.chat(messages, self.config.get("ai_model", "glm-4"))
            await event.reply(response)
            self.conversation_history[chat_id].append({"role": "assistant", "content": response})

            self.message_callback("message", {
                "chat_id": chat_id, "sender": "AI",
                "text": response[:200], "direction": "out"
            })

        except Exception as e:
            self.message_callback("error", f"AI Error: {e}")


# ===========================================================================
# MAIN APPLICATION
# ===========================================================================
class NinjaApp:
    """Main Application with Professional Windows UI"""

    def __init__(self):
        self.config = self.load_config()
        self.message_queue = queue.Queue()

        # Data
        self.messages: List[MessageLog] = []
        self.leads: List[Lead] = []
        self.orders: Dict[int, ClientOrder] = {}
        self.load_data()

        # AI
        self.ai_client = AIClient()

        # AI Proxy
        if getattr(sys, 'frozen', False):
            proxy_dir = Path(sys.executable).parent / "ai-proxy"
        else:
            proxy_dir = Path(__file__).parent.parent / "ai-proxy"
        self.ai_proxy = AIProxyManager(proxy_dir, self._on_proxy_status)

        # Bot
        self.bot = BotManager(self.config, self._on_bot_message, self.ai_client)

        # Stats
        self.message_count = 0
        self.lead_count = 0

        # UI
        self.setup_ui()
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
                    self.messages = [MessageLog(**m) for m in data[-500:]]
            except:
                pass

        if ORDERS_FILE.exists():
            try:
                with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.orders[int(k)] = ClientOrder(**v)
            except:
                pass

    def save_data(self):
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in self.messages[-500:]], f, indent=2, ensure_ascii=False)

        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v.to_dict() for k, v in self.orders.items()}, f, indent=2, ensure_ascii=False)

    # =======================================================================
    # UI SETUP
    # =======================================================================
    def setup_ui(self):
        if CTK_AVAILABLE:
            self.setup_ctk_ui()
        else:
            self.setup_tk_ui()

    def setup_ctk_ui(self):
        """Professional CustomTkinter UI"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("1300x850")
        self.root.minsize(1100, 750)

        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # ===== SIDEBAR =====
        self.sidebar = ctk.CTkFrame(self.root, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Logo
        ctk.CTkLabel(self.sidebar, text="🥷 NINJA", font=("", 28, "bold")).pack(pady=20)
        ctk.CTkLabel(self.sidebar, text=f"v{VERSION}", text_color="gray").pack()

        # Navigation
        self.nav_buttons = {}
        nav_items = [
            ("🏠 Главная", "main"),
            ("💬 Сообщения", "messages"),
            ("📦 Заказы", "orders"),
            ("👥 Лиды", "leads"),
            ("⚙️ Настройки", "settings"),
        ]

        for text, key in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=text, command=lambda k=key: self.show_panel(k),
                height=50, anchor="w", fg_color="transparent",
                text_color=("gray10", "#DCE4EE"), hover_color=("gray70", "gray30"), corner_radius=10
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = btn

        # Status
        status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        status_frame.pack(side="bottom", fill="x", padx=10, pady=15)

        self.proxy_status_var = ctk.StringVar(value="⏹️ AI Proxy: Остановлен")
        ctk.CTkLabel(status_frame, textvariable=self.proxy_status_var, font=("", 11)).pack(anchor="w")

        self.bot_status_var = ctk.StringVar(value="⏹️ Бот: Остановлен")
        ctk.CTkLabel(status_frame, textvariable=self.bot_status_var, font=("", 11)).pack(anchor="w", pady=5)

        self.stats_var = ctk.StringVar(value="📊 0 сообщений | 0 лидов | 0 заказов")
        ctk.CTkLabel(status_frame, textvariable=self.stats_var, font=("", 11)).pack(anchor="w")

        # ===== CONTENT =====
        self.content = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.panels = {}
        self.setup_main_panel()
        self.setup_messages_panel()
        self.setup_orders_panel()
        self.setup_leads_panel()
        self.setup_settings_panel()

        self.show_panel("main")

    def setup_main_panel(self):
        """Main dashboard"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")

        # Title
        ctk.CTkLabel(panel, text="🏠 Главная панель", font=("", 26, "bold")).pack(pady=15)

        # Auth Card
        auth_card = ctk.CTkFrame(panel)
        auth_card.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(auth_card, text="📱 Авторизация Telegram", font=("", 16, "bold")).pack(pady=10)

        phone_frame = ctk.CTkFrame(auth_card, fg_color="transparent")
        phone_frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(phone_frame, text="Телефон:", width=120).pack(side="left")
        self.phone_entry = ctk.CTkEntry(phone_frame, width=250, placeholder_text="+998...")
        self.phone_entry.pack(side="left", padx=10)
        self.phone_entry.insert(0, self.config.get("phone", ""))

        self.auth_btn = ctk.CTkButton(auth_card, text="🔑 Войти в Telegram", command=self.start_auth, width=200, height=40)
        self.auth_btn.pack(pady=10)

        self.code_frame = ctk.CTkFrame(auth_card, fg_color="transparent")
        ctk.CTkLabel(self.code_frame, text="Код:").pack(side="left")
        self.code_entry = ctk.CTkEntry(self.code_frame, width=100)
        self.code_entry.pack(side="left", padx=10)
        ctk.CTkButton(self.code_frame, text="OK", command=self.submit_code, width=60).pack(side="left")

        # Control Card
        control_card = ctk.CTkFrame(panel)
        control_card.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(control_card, text="🤖 Управление ботом", font=("", 16, "bold")).pack(pady=10)

        btn_frame = ctk.CTkFrame(control_card, fg_color="transparent")
        btn_frame.pack(pady=10)

        self.start_proxy_btn = ctk.CTkButton(
            btn_frame, text="🚀 Запустить AI Proxy", command=self.start_ai_proxy,
            width=200, height=45, fg_color="#1f6aa5", hover_color="#144870"
        )
        self.start_proxy_btn.pack(side="left", padx=10)

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶️ Запустить бота", command=self.start_bot,
            width=200, height=45, fg_color="#2ecc71", hover_color="#27ae60"
        )
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="⏹️ Остановить", command=self.stop_bot,
            width=200, height=45, fg_color="#e74c3c", hover_color="#c0392b", state="disabled"
        )
        self.stop_btn.pack(side="left", padx=10)

        # Stats Cards
        stats_frame = ctk.CTkFrame(panel, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=20)

        for icon, label, attr in [("💬", "Сообщений", "msg"), ("👥", "Лидов", "lead"), ("📦", "Заказов", "order")]:
            card = ctk.CTkFrame(stats_frame, width=150, height=100)
            card.pack(side="left", padx=10, pady=5)
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=icon, font=("", 28)).pack(pady=5)
            lbl = ctk.CTkLabel(card, text="0", font=("", 22, "bold"))
            lbl.pack()
            setattr(self, f"{attr}_count_label", lbl)
            ctk.CTkLabel(card, text=label, font=("", 11)).pack()

        self.panels["main"] = panel

    def setup_messages_panel(self):
        """Messages panel with chat history"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=10)

        ctk.CTkLabel(header, text="💬 Сообщения", font=("", 22, "bold")).pack(side="left", padx=20)
        ctk.CTkButton(header, text="🗑️ Очистить", command=self.clear_messages, width=100).pack(side="right", padx=20)

        self.messages_frame = ctk.CTkScrollableFrame(panel)
        self.messages_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.panels["messages"] = panel

    def setup_orders_panel(self):
        """Orders management panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(panel, text="📦 Заказы", font=("", 22, "bold")).pack(pady=20)

        # Orders list placeholder
        self.orders_frame = ctk.CTkScrollableFrame(panel)
        self.orders_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.panels["orders"] = panel

    def setup_leads_panel(self):
        """Leads panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(panel, text="👥 Лиды", font=("", 22, "bold")).pack(pady=20)

        self.leads_frame = ctk.CTkScrollableFrame(panel)
        self.leads_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.panels["leads"] = panel

    def setup_settings_panel(self):
        """Settings panel"""
        panel = ctk.CTkFrame(self.content, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(panel, text="⚙️ Настройки", font=("", 22, "bold")).grid(row=0, column=0, pady=15, sticky="w", padx=20)

        settings_frame = ctk.CTkScrollableFrame(panel)
        settings_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)

        # Model
        model_frame = ctk.CTkFrame(settings_frame)
        model_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(model_frame, text="🤖 AI Модель:", font=("", 13)).pack(side="left", padx=10)
        self.model_entry = ctk.CTkEntry(model_frame, width=200)
        self.model_entry.pack(side="left", padx=10)
        self.model_entry.insert(0, self.config.get("ai_model", "glm-4"))

        # System prompt
        prompt_frame = ctk.CTkFrame(settings_frame)
        prompt_frame.pack(fill="both", expand=True, pady=10)
        ctk.CTkLabel(prompt_frame, text="📝 Системный промпт:", font=("", 13)).pack(anchor="w", padx=10, pady=5)

        self.prompt_text = ctk.CTkTextbox(prompt_frame, height=300)
        self.prompt_text.pack(fill="both", expand=True, padx=10, pady=5)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        ctk.CTkButton(settings_frame, text="💾 Сохранить настройки", command=self.save_settings, width=200, height=40).pack(pady=15)

        self.panels["settings"] = panel

    def show_panel(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.configure(fg_color=("gray75", "gray25") if k == key else "transparent")
        for k, panel in self.panels.items():
            panel.grid(row=0, column=0, sticky="nsew") if k == key else panel.grid_remove()

    # =======================================================================
    # FALLBACK TKINTER UI
    # =======================================================================
    def setup_tk_ui(self):
        self.root = tk.Tk()
        self.root.title(f"🥷 Ninja Userbot v{VERSION}")
        self.root.geometry("1000x700")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Главная")
        self.setup_tk_main_tab(main_tab)

        messages_tab = ttk.Frame(notebook)
        notebook.add(messages_tab, text="Сообщения")
        self.messages_text = scrolledtext.ScrolledText(messages_tab)
        self.messages_text.pack(fill="both", expand=True, padx=5, pady=5)

        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="Настройки")
        self.setup_tk_settings_tab(settings_tab)

        self.status_var = tk.StringVar(value="Готов")
        ttk.Label(self.root, textvariable=self.status_var).pack(fill="x", side="bottom")

    def setup_tk_main_tab(self, parent):
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

        control_frame = ttk.LabelFrame(parent, text="Управление")
        control_frame.pack(fill="x", padx=10, pady=10)

        self.start_btn = ttk.Button(control_frame, text="▶️ Запустить бота", command=self.start_bot)
        self.start_btn.pack(side="left", padx=10, pady=10)
        self.stop_btn = ttk.Button(control_frame, text="⏹️ Остановить", command=self.stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)

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

    # =======================================================================
    # ACTIONS
    # =======================================================================
    def start_ai_proxy(self):
        threading.Thread(target=self.ai_proxy.start, daemon=True).start()

    def start_auth(self):
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
        code = self.code_entry.get().strip()
        if not code:
            return

        def callback(status, data):
            self.message_queue.put(("auth", f"{status}:{data}"))

        self.bot.sign_in(self.config.get("phone", ""), code, callback)

    def start_bot(self):
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
        """Add message to UI"""
        if not CTK_AVAILABLE:
            text = f"[{datetime.now().strftime('%H:%M:%S')}] {msg_data['sender']}: {msg_data['text']}\n"
            self.messages_text.insert(tk.END, text)
            self.messages_text.see(tk.END)
            return

        card = ctk.CTkFrame(self.messages_frame)
        card.pack(fill="x", pady=2, padx=5)

        direction = msg_data.get("direction", "in")
        color = "#2ecc71" if direction == "out" else "#3498db"

        ctk.CTkLabel(card, text=datetime.now().strftime("%H:%M:%S"), font=("", 10), text_color="gray").pack(anchor="w", padx=10, pady=2)

        icon = "📤" if direction == "out" else "📥"
        media_type = msg_data.get("media_type", "text")
        if media_type == "image":
            icon = "🖼️"
        elif media_type == "location":
            icon = "📍"
        elif media_type == "sticker":
            icon = "😀"

        ctk.CTkLabel(card, text=f"{icon} {msg_data['sender']}", font=("", 12, "bold"), text_color=color).pack(anchor="w", padx=10, pady=2)

        ctk.CTkLabel(card, text=msg_data['text'][:300], font=("", 11), wraplength=600, justify="left").pack(anchor="w", padx=10, pady=5)

    def update_stats(self):
        self.stats_var.set(f"📊 {self.message_count} сообщений | {self.lead_count} лидов | {len(self.orders)} заказов")

        if CTK_AVAILABLE:
            self.msg_count_label.configure(text=str(self.message_count))
            self.lead_count_label.configure(text=str(self.lead_count))
            self.order_count_label.configure(text=str(len(self.orders)))

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

                elif msg_type == "image":
                    self.message_callback("message", {
                        "chat_id": data["chat_id"], "sender": data["sender"],
                        "text": f"[IMAGE: {data['description']}]",
                        "direction": "in", "media_type": "image"
                    })

                elif msg_type == "location":
                    self.add_message_to_ui({
                        "chat_id": data["chat_id"], "sender": data["sender"],
                        "text": f"[LOCATION: {data['url']}]",
                        "direction": "in", "media_type": "location"
                    })
                    self.message_count += 1
                    self.update_stats()

                elif msg_type == "sticker":
                    self.add_message_to_ui({
                        "chat_id": data["chat_id"], "sender": data["sender"],
                        "text": f"[STICKER: {data['description']}]",
                        "direction": "in", "media_type": "sticker"
                    })
                    self.message_count += 1
                    self.update_stats()

                elif msg_type == "error":
                    print(f"Error: {data}")

        except queue.Empty:
            pass

        self.root.after(100, self.process_messages)

    def run(self):
        self.root.mainloop()


# ===========================================================================
# ENTRY POINT
# ===========================================================================
def main():
    app = NinjaApp()
    app.run()


if __name__ == "__main__":
    main()
