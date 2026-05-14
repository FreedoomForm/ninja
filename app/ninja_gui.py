"""
Ninja Userbot - Complete Native Windows Application
=====================================================
Telegram Auto-Reply with AI using z-ai-web-sdk
Full-featured: Images, Locations, Stickers, Orders, Leads
100% matches Web UI functionality
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
VERSION = "3.5"

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
- 5 махаллинских овкат в порциях
- Курьер звонит по прибытии
- Яндекс такси - за счёт клиента
- Дни доставки: воскр, пн, вт, ср, чт, пт (2 пакета в пт для сб и вс)

ЗАКАЗ:
- До 21:00 за день до доставки
- Отмена до 21:00 за день до доставки
- Минимум 3 дня для первого заказа
- Предоплата обязательна

КАРТЫ:
- Humo: 9860010112421465
- Uzum: 4916990324223715
- Uzcard: 5614681209925290
- Получатель: Xodjimuratov Bahodir

ИНСТАГРАМ: @soglom.taom
ТЕЛЕГРАМ КАНАЛ: @soglomtaom
"""

DEFAULT_SYSTEM_PROMPT = """Ты Бахром, 35-летний сотрудник компании Sog'lom taom (Соғлом таом) из Ташкента, Узбекистан. Ты работаешь в отделе доставки здорового питания и отвечаешь на сообщения клиентов в Telegram.

О ТЕБЕ:
- Родился и вырос в Ташкенте, живёшь в Сергели районе
- Работаешь в Sog'lom taom уже 2 года
- Знаешь всё о правильном питании, БЖУ, калориях
- Общаешься на узбекском и русском языках
- Используешь смесь языков как все в Ташкенте (тебе понятно "калиш", "мойсалам", "хоп-хоп")
- Дружелюбный, но профессиональный
- Отвечаешь быстро и по делу

СТИЛЬ ОБЩЕНИЯ:
- Пиши естественно, как реальный человек из Ташкента
- Используй "Сиз" для новых клиентов, "Сен" для постоянных
- Можно использовать эмодзи, но умеренно
- Отвечай на том же языке, на котором написал клиент
- Не пиши слишком длинные сообщения
- Используй локальные выражения когда уместно

ВАЖНО:
- Ты НЕ бот, ты реальный человек
- Не говори "я AI" или "я ассистент"
- Если не знаешь ответа - скажи честно "сейчас уточню"
- Всегда будь вежлив даже с грубыми клиентами
- Цены и условия - только актуальные из контекста

ИНФОРМАЦИЯ О КОМПАНИИ (используй при ответах):
""" + COMPANY_INFO + """

ПОВЕДЕНИЕ ПРИ ПОЛУЧЕНИИ ЧЕКА ОПЛАТЫ:
Когда клиент присылает изображение чека:
1. Подтверди получение: "Хоп, чек келди. Текшириб чикишамиз..."
2. После обработки подтверди оплату
3. Спроси про дату первой доставки если ещё не обсуждали

ПОВЕДЕНИЕ ПРИ ПОЛУЧЕНИИ ЛОКАЦИИ:
Когда клиент присылает геолокацию:
1. Подтверди получение локации
2. Спроси точный адрес (район, массив, дом, квартира, код домофона)
3. Уточни куда оставить пакет если клиента нет дома

ПОВЕДЕНИЕ ПРИ ОБСУЖДЕНИИ ДАТЫ ДОСТАВКИ:
Когда клиент называет день доставки:
1. Проверь что сегодня до 21:00 - если после 21:00, доставка возможна только послезавтра
2. Проверь что день не суббота (в субботу доставки нет, кухня закрыта)
3. Если всё ОК - подтверди дату
4. Напомни про оплату до 21:00
"""

DEFAULT_LEAD_PROMPT = """Ты анализируешь переписку с клиентом и определяешь, является ли это успешным лидом.

УСПЕШНЫЙ ЛИД - клиент который:
✅ Готов сделать заказ (назначил калории, выбрал пакет)
✅ Запросил расчёт калорий и дал свои данные
✅ Дал адрес доставки и контакты
✅ Оплатил или готов оплатить
✅ Спросил про оплату/карты
✅ Прислал чек об оплате
✅ Прислал локацию

НЕ ЛИД:
❌ Просто спрашивает цены "на будущее"
❌ Жалуется или возмущается
❌ Нужна просто консультация без намерения купить
❌ Спам или реклама

Проанализируй переписку и ответь ТОЛЬКО в формате JSON:
{
  "is_lead": true/false,
  "confidence": 0.0-1.0,
  "lead_type": "new_client/repeat_client/consultation/payment_confirmed/location_received",
  "client_name": "имя клиента",
  "summary": "краткое описание что нужно сделать",
  "urgency": "high/medium/low",
  "order_details": {
    "calories": "калории если указаны",
    "days": "количество дней если указано",
    "address": "адрес если указан",
    "phone": "телефон если указан",
    "delivery_date": "дата доставки если указана",
    "payment_confirmed": true/false
  }
}

Если не лид - верни is_lead: false и остальные поля пустыми.
"""

DEFAULT_CONFIG = {
    "api_id": "",
    "api_hash": "",
    "phone": "",
    "mistral_key": "",
    "mistral_model": "pixtral-12b-2409",
    "text_model": "mistral-medium-latest",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "lead_prompt": DEFAULT_LEAD_PROMPT,
    "ai_model": "glm-4",
    "couriers": "",
}

# Vision and Text Models
VISION_MODELS = [
    ("pixtral-12b-2409", "Pixtral 12B (рекомендуется)"),
    ("pixtral-large-latest", "Pixtral Large"),
    ("mistral-large-latest", "Mistral Large"),
]

TEXT_MODELS = [
    ("mistral-medium-latest", "Mistral Medium"),
    ("mistral-small-latest", "Mistral Small"),
    ("mistral-large-latest", "Mistral Large"),
    ("open-mistral-nemo", "Mistral Nemo"),
]

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
    status: str = "pending"


@dataclass
class Lead:
    id: str
    timestamp: str
    chat_id: int
    client_name: str
    summary: str
    confidence: float = 0.5
    lead_type: str = "new_client"
    urgency: str = "medium"


@dataclass
class MessageLog:
    id: str
    timestamp: str
    chat_id: int
    sender: str
    text: str
    direction: str  # "in", "out", "system", "error", "lead"
    media_type: str = "text"
    has_image: bool = False
    has_location: bool = False


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================
def get_price_for_calories(calories: str) -> int:
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
    """Client for AI API calls - supports both z-ai-web-sdk and Mistral"""

    def __init__(self, config: dict):
        self.config = config
        self.proxy_url = AI_PROXY_URL
        self.vision_url = AI_VISION_URL

    async def chat(self, messages: list, model: str = "glm-4") -> str:
        """Send chat completion request via z-ai-web-sdk proxy"""
        now = datetime.now()
        time_context = f"\n\n[ТЕКУЩЕЕ ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')} ({DAYS_RU.get(now.strftime('%A').lower(), '')})]"
        time_context += f"\n[СЕЙЧАС {now.strftime('%H:%M')}, ДЕДЛАЙН ЗАКАЗА НА ЗАВТРА: 21:00]"
        if now.hour >= 21:
            time_context += "\n[ВНИМАНИЕ: Уже после 21:00, заказы на завтра не принимаются!]"

        messages_with_time = messages.copy()
        if messages_with_time and messages_with_time[0]["role"] == "system":
            messages_with_time[0] = {"role": "system", "content": messages_with_time[0]["content"] + time_context}

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.proxy_url,
                json={"messages": messages_with_time, "model": model, "temperature": 0.7, "max_tokens": 1000}
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            raise Exception(f"AI API Error: {response.status_code}")

    async def vision_mistral(self, image_base64: str, mistral_key: str, model: str) -> str:
        """Analyze image with Mistral Vision API (Pixtral)"""
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"}

        prompt = """Проанализируй это изображение. Это может быть:

1. Стикер из Telegram (мультяшное изображение, эмодзи-персонаж)
2. Чек об оплате (перевод денег)
3. Скриншот приложения банка
4. Фото продукта или еды
5. Другое

ЕСЛИ ЭТО СТИКЕР:
- Опиши какой эмоционал/настроение передаёт стикер
- Опиши персонажа если есть (кот, медведь, человек и т.д.)
- Какую реакцию ожидают от этого стикера (согласие, смех, грусть, благодарность)

ЕСЛИ ЭТО ЧЕК/ПЕРЕВОД:
- Сумму перевода
- Дату и время если видны
- Номер карты получателя если виден
- Имя получателя если видно

Отвечай на русском языке кратко и по делу (2-3 предложения)."""

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_base64}}
            ]
        }]

        payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 500}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Mistral Vision error: {e}")
        return "изображение"

    async def vision_proxy(self, image_base64: str) -> str:
        """Analyze image with z-ai-web-sdk Vision API"""
        prompt = """Проанализируй это изображение.
Если это СТИКЕР - опиши эмоцию и настроение.
Если это ЧЕК - укажи сумму перевода.
Если это ЛОКАЦИЯ/КАРТА - опиши место.
Отвечай кратко (2-3 предложения)."""

        try:
            async with httpx.AsyncClient(timeout=120) as client:
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
        api_id = self.config.get("api_id", "")
        api_hash = self.config.get("api_hash", "")
        if not api_id or not api_hash:
            raise Exception("Настройте API ID и API Hash в настройках")
        self.client = TelegramClient(str(SESSION_PATH), int(api_id), api_hash)
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

        image_base64 = None
        media_type = "text"
        media_description = ""
        has_image = False
        has_location = False

        # Handle location
        if isinstance(event.media, (MessageMediaGeo, MessageMediaGeoLive)):
            media_type = "location"
            has_location = True
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
            has_image = True
            image_base64 = await self._download_image(event)
            if image_base64:
                # Try Mistral Vision first, then proxy
                mistral_key = self.config.get("mistral_key", "")
                mistral_model = self.config.get("mistral_model", "pixtral-12b-2409")
                
                if mistral_key:
                    media_description = await self.ai_client.vision_mistral(image_base64, mistral_key, mistral_model)
                else:
                    media_description = await self.ai_client.vision_proxy(image_base64)
                    
                self.message_callback("image", {
                    "chat_id": chat_id, "sender": sender_name,
                    "description": media_description
                })

        # Handle sticker
        elif event.media and hasattr(event.media, 'document'):
            sticker_base64 = await self._download_sticker(event)
            if sticker_base64:
                media_type = "sticker"
                has_image = True
                mistral_key = self.config.get("mistral_key", "")
                mistral_model = self.config.get("mistral_model", "pixtral-12b-2409")
                
                if mistral_key:
                    media_description = await self.ai_client.vision_mistral(
                        sticker_base64, mistral_key, mistral_model
                    )
                else:
                    media_description = await self.ai_client.vision_proxy(sticker_base64)
                    
                self.message_callback("sticker", {
                    "chat_id": chat_id, "sender": sender_name,
                    "description": media_description
                })

        # Build message for AI
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
            "chat_id": chat_id, "sender": sender_name,
            "text": enriched_text[:200], "direction": "in",
            "media_type": media_type, "has_image": has_image, "has_location": has_location
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
    """Main Application - 100% matches Web UI"""

    def __init__(self):
        self.config = self.load_config()
        self.message_queue = queue.Queue()

        # Data
        self.messages: List[MessageLog] = []
        self.leads: List[Lead] = []
        self.orders: Dict[int, ClientOrder] = {}
        self.load_data()

        # AI
        self.ai_client = AIClient(self.config)

        # AI Proxy
        if getattr(sys, 'frozen', False):
            proxy_dir = Path(sys.executable).parent / "ai-proxy"
        else:
            proxy_dir = Path(__file__).parent.parent / "ai-proxy"
        self.ai_proxy = AIProxyManager(proxy_dir, self._on_proxy_status)

        # Bot
        self.bot = BotManager(self.config, self._on_bot_message, self.ai_client)

        # Stats
        self.message_count = len(self.messages)
        self.lead_count = len(self.leads)
        self.order_count = len(self.orders)
        self.bot_username = ""

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
        if not cfg.get("system_prompt"):
            cfg["system_prompt"] = DEFAULT_SYSTEM_PROMPT
        if not cfg.get("lead_prompt"):
            cfg["lead_prompt"] = DEFAULT_LEAD_PROMPT
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

        if LEADS_FILE.exists():
            try:
                with open(LEADS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.leads = [Lead(**l) for l in data[-200:]]
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

        with open(LEADS_FILE, "w", encoding="utf-8") as f:
            json.dump([asdict(l) for l in self.leads[-200:]], f, indent=2, ensure_ascii=False)

        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): asdict(v) for k, v in self.orders.items()}, f, indent=2, ensure_ascii=False)

    # =======================================================================
    # UI SETUP
    # =======================================================================
    def setup_ui(self):
        if CTK_AVAILABLE:
            self.setup_ctk_ui()
        else:
            self.setup_tk_ui()

    def setup_ctk_ui(self):
        """Professional CustomTkinter UI - matches Web UI exactly"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(f"🥷 Ninja Userbot - Sog'lom taom")
        self.root.geometry("1000x750")
        self.root.minsize(900, 650)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        # ===== HEADER =====
        header = ctk.CTkFrame(self.root, height=60, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # Title
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=10)
        ctk.CTkLabel(title_frame, text="🥷 Ninja Userbot", font=("", 20, "bold")).pack(side="left")
        ctk.CTkLabel(title_frame, text="Sog'lom taom", font=("", 12), text_color="#10b981").pack(side="left", padx=10)

        # Status Badge
        self.status_badge = ctk.CTkLabel(
            header, text="Offline", font=("", 13, "bold"),
            fg_color="#6b7280", corner_radius=16, width=80, height=28
        )
        self.status_badge.grid(row=0, column=2, padx=20, pady=10)

        # ===== MAIN CONTENT =====
        main = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # Info Box
        info_box = ctk.CTkFrame(main, fg_color="#1e3a5f", corner_radius=8)
        info_box.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(
            info_box,
            text="📱 Telegram Userbot для Sog'lom taom — автоответчик для клиентов здорового питания.\nОтвечает как реальный сотрудник + определяет успешные лиды → Saved Messages",
            font=("", 12), text_color="#93c5fd", justify="left"
        ).pack(padx=15, pady=10, anchor="w")

        # Stats Row
        stats_row = ctk.CTkFrame(main, fg_color="transparent")
        stats_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        self.stat_labels = {}
        for i, (label, color) in enumerate([
            ("Статус", "#10b981"),
            ("Сообщений", "#10b981"),
            ("Лидов", "#34d399"),
            ("Аккаунт", "#10b981")
        ]):
            card = ctk.CTkFrame(stats_row, width=150, height=70, corner_radius=10)
            card.grid(row=0, column=i, padx=5, sticky="ew")
            card.grid_propagate(False)
            
            value_lbl = ctk.CTkLabel(card, text="0" if label != "Статус" else "Stopped", font=("", 18, "bold"), text_color=color)
            value_lbl.pack(pady=(12, 0))
            ctk.CTkLabel(card, text=label, font=("", 11), text_color="#9ca3af").pack()
            self.stat_labels[label] = value_lbl

        # Tabs
        tabs_frame = ctk.CTkFrame(main, fg_color="transparent")
        tabs_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        self.tab_buttons = {}
        for i, (text, key) in enumerate([
            ("🎮 Управление", "control"),
            ("🎯 Лиды", "leads"),
            ("⚙️ Настройки", "settings"),
            ("📋 Логи", "logs")
        ]):
            btn = ctk.CTkButton(
                tabs_frame, text=text, width=140, height=36,
                fg_color="#10b981" if i == 0 else "transparent",
                text_color="white" if i == 0 else "#9ca3af",
                hover_color="#059669" if i == 0 else "#374151",
                corner_radius=8, command=lambda k=key: self.show_panel(k)
            )
            btn.grid(row=0, column=i, padx=3)
            self.tab_buttons[key] = btn

        # Panels Container
        self.panels_frame = ctk.CTkFrame(main, corner_radius=12, fg_color="#1a1a2e")
        self.panels_frame.grid(row=3, column=0, sticky="nsew")
        self.panels_frame.grid_columnconfigure(0, weight=1)
        self.panels_frame.grid_rowconfigure(0, weight=1)

        self.panels = {}
        self.setup_control_panel()
        self.setup_leads_panel()
        self.setup_settings_panel()
        self.setup_logs_panel()

        self.show_panel("control")

    def setup_control_panel(self):
        """Control panel with Start/Stop and live logs"""
        panel = ctk.CTkFrame(self.panels_frame, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        # Buttons
        btn_frame = ctk.CTkFrame(panel, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="w", pady=(0, 15))

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶ Запустить", width=150, height=40,
            fg_color="#10b981", hover_color="#059669",
            command=self.start_bot
        )
        self.start_btn.pack(side="left", padx=(0, 10))

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="⏹ Остановить", width=150, height=40,
            fg_color="#ef4444", hover_color="#dc2626",
            command=self.stop_bot, state="disabled"
        )
        self.stop_btn.pack(side="left")

        # Auth section
        auth_frame = ctk.CTkFrame(panel, fg_color="transparent")
        auth_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(auth_frame, text="📱 Телефон:", font=("", 12)).pack(side="left")
        self.phone_entry = ctk.CTkEntry(auth_frame, width=180, placeholder_text="+998...")
        self.phone_entry.pack(side="left", padx=10)
        self.phone_entry.insert(0, self.config.get("phone", ""))

        self.auth_btn = ctk.CTkButton(auth_frame, text="🔑 Войти", width=100, command=self.start_auth)
        self.auth_btn.pack(side="left", padx=10)

        self.code_entry = ctk.CTkEntry(auth_frame, width=100, placeholder_text="Код")
        self.code_entry.pack(side="left", padx=10)

        ctk.CTkButton(auth_frame, text="OK", width=50, command=self.submit_code).pack(side="left")

        # Logs display
        self.control_logs = ctk.CTkScrollableFrame(panel, fg_color="#0d0d1a", corner_radius=8)
        self.control_logs.grid(row=1, column=0, sticky="nsew")

        self.panels["control"] = panel

    def setup_leads_panel(self):
        """Leads panel with cards"""
        panel = ctk.CTkFrame(self.panels_frame, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        btn_frame = ctk.CTkFrame(panel, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="w", pady=(0, 10))
        ctk.CTkButton(btn_frame, text="🗑 Очистить лиды", fg_color="#374151", width=150, command=self.clear_leads).pack()

        self.leads_list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.leads_list.grid(row=1, column=0, sticky="nsew")

        self.panels["leads"] = panel

    def setup_settings_panel(self):
        """Settings panel - matches Web UI exactly"""
        panel = ctk.CTkFrame(self.panels_frame, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")

        # Telegram Section
        ctk.CTkLabel(scroll, text="📱 Telegram", font=("", 16, "bold"), text_color="#10b981").pack(anchor="w", pady=(0, 10))

        tg_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        tg_frame.pack(fill="x", pady=(0, 20))

        # API ID
        id_frame = ctk.CTkFrame(tg_frame, fg_color="transparent")
        id_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(id_frame, text="API ID", width=120, anchor="w").pack(side="left")
        self.api_id_entry = ctk.CTkEntry(id_frame, width=300, placeholder_text="12345678")
        self.api_id_entry.pack(side="left", padx=10)
        self.api_id_entry.insert(0, self.config.get("api_id", ""))
        ctk.CTkLabel(id_frame, text="Получить на my.telegram.org", text_color="#6b7280", font=("", 10)).pack(side="left")

        # API Hash
        hash_frame = ctk.CTkFrame(tg_frame, fg_color="transparent")
        hash_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(hash_frame, text="API Hash", width=120, anchor="w").pack(side="left")
        self.api_hash_entry = ctk.CTkEntry(hash_frame, width=300, placeholder_text="a1b2c3d4e5f6...", show="*")
        self.api_hash_entry.pack(side="left", padx=10)
        self.api_hash_entry.insert(0, self.config.get("api_hash", ""))

        # Mistral AI Section
        ctk.CTkLabel(scroll, text="🤖 Mistral AI", font=("", 16, "bold"), text_color="#10b981").pack(anchor="w", pady=(0, 10))

        mistral_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        mistral_frame.pack(fill="x", pady=(0, 20))

        # Mistral Key
        key_frame = ctk.CTkFrame(mistral_frame, fg_color="transparent")
        key_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(key_frame, text="Mistral API Key", width=120, anchor="w").pack(side="left")
        self.mistral_key_entry = ctk.CTkEntry(key_frame, width=300, placeholder_text="your-api-key", show="*")
        self.mistral_key_entry.pack(side="left", padx=10)
        self.mistral_key_entry.insert(0, self.config.get("mistral_key", ""))
        ctk.CTkLabel(key_frame, text="console.mistral.ai", text_color="#6b7280", font=("", 10)).pack(side="left")

        # Vision Model
        vision_frame = ctk.CTkFrame(mistral_frame, fg_color="transparent")
        vision_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(vision_frame, text="Vision Model", width=120, anchor="w").pack(side="left")
        self.vision_model_cb = ctk.CTkComboBox(vision_frame, values=[m[1] for m in VISION_MODELS], width=300)
        self.vision_model_cb.pack(side="left", padx=10)
        current_vision = self.config.get("mistral_model", "pixtral-12b-2409")
        for val, name in VISION_MODELS:
            if val == current_vision:
                self.vision_model_cb.set(name)
                break

        # Text Model
        text_frame = ctk.CTkFrame(mistral_frame, fg_color="transparent")
        text_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(text_frame, text="Text Model", width=120, anchor="w").pack(side="left")
        self.text_model_cb = ctk.CTkComboBox(text_frame, values=[m[1] for m in TEXT_MODELS], width=300)
        self.text_model_cb.pack(side="left", padx=10)
        current_text = self.config.get("text_model", "mistral-medium-latest")
        for val, name in TEXT_MODELS:
            if val == current_text:
                self.text_model_cb.set(name)
                break

        # System Prompt Section
        ctk.CTkLabel(scroll, text="💬 Промпт сотрудника", font=("", 16, "bold"), text_color="#10b981").pack(anchor="w", pady=(0, 10))

        prompt_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        prompt_frame.pack(fill="both", expand=True, pady=(0, 20))

        ctk.CTkLabel(prompt_frame, text="Системный промпт (инструкции для AI)", text_color="#9ca3af", font=("", 11)).pack(anchor="w")
        ctk.CTkLabel(prompt_frame, text="Оставьте пустым для использования дефолтного промпта (сотрудник Sog'lom taom)", text_color="#6b7280", font=("", 10)).pack(anchor="w", pady=(0, 5))

        self.prompt_text = ctk.CTkTextbox(prompt_frame, height=250, font=("", 11))
        self.prompt_text.pack(fill="both", expand=True)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        # Save Button
        ctk.CTkButton(scroll, text="💾 Сохранить", width=150, height=40, command=self.save_settings).pack(pady=10)

        self.panels["settings"] = panel

    def setup_logs_panel(self):
        """Full logs panel"""
        panel = ctk.CTkFrame(self.panels_frame, fg_color="transparent")
        panel.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        btn_frame = ctk.CTkFrame(panel, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="w", pady=(0, 10))
        ctk.CTkButton(btn_frame, text="🗑 Очистить логи", fg_color="#374151", width=150, command=self.clear_messages).pack()

        self.full_logs = ctk.CTkScrollableFrame(panel, fg_color="#0d0d1a", corner_radius=8)
        self.full_logs.grid(row=1, column=0, sticky="nsew")

        self.panels["logs"] = panel

    def show_panel(self, key: str):
        for k, btn in self.tab_buttons.items():
            if k == key:
                btn.configure(fg_color="#10b981", text_color="white", hover_color="#059669")
            else:
                btn.configure(fg_color="transparent", text_color="#9ca3af", hover_color="#374151")

        for k, panel in self.panels.items():
            if k == key:
                panel.grid(row=0, column=0, sticky="nsew")
            else:
                panel.grid_remove()

    # =======================================================================
    # ACTIONS
    # =======================================================================
    def start_auth(self):
        phone = self.phone_entry.get().strip()
        if not phone:
            messagebox.showerror("Ошибка", "Введите номер телефона")
            return
        self.config["phone"] = phone
        self.save_config()
        self.bot.config = self.config
        self.bot.connect(phone, self._on_auth_result)

    def _on_auth_result(self, status, data):
        self.message_queue.put(("auth", (status, data)))

    def submit_code(self):
        code = self.code_entry.get().strip()
        phone = self.phone_entry.get().strip()
        if not code:
            messagebox.showerror("Ошибка", "Введите код")
            return
        self.bot.sign_in(phone, code, self._on_auth_result)

    def start_ai_proxy(self):
        threading.Thread(target=self.ai_proxy.start, daemon=True).start()

    def start_bot(self):
        api_id = self.config.get("api_id", "")
        api_hash = self.config.get("api_hash", "")
        if not api_id or not api_hash:
            messagebox.showerror("Ошибка", "Настройте API ID и API Hash в настройках")
            return
        self.bot.config = self.config
        self.bot.start_bot(self._on_bot_start_result)

    def _on_bot_start_result(self, status, data):
        self.message_queue.put(("bot_start", (status, data)))

    def stop_bot(self):
        self.bot.stop_bot()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.update_status_badge(False)
        self.stat_labels["Статус"].configure(text="Stopped")
        self.add_log("System", "Бот остановлен", "system")

    def save_settings(self):
        self.config["api_id"] = self.api_id_entry.get().strip()
        self.config["api_hash"] = self.api_hash_entry.get().strip()
        self.config["mistral_key"] = self.mistral_key_entry.get().strip()
        
        vision_name = self.vision_model_cb.get()
        for val, name in VISION_MODELS:
            if name == vision_name:
                self.config["mistral_model"] = val
                break
        
        text_name = self.text_model_cb.get()
        for val, name in TEXT_MODELS:
            if name == text_name:
                self.config["text_model"] = val
                break
        
        self.config["system_prompt"] = self.prompt_text.get("1.0", "end").strip()
        
        self.save_config()
        self.bot.config = self.config
        self.ai_client.config = self.config
        messagebox.showinfo("Сохранено", "✅ Настройки сохранены!")
        self.add_log("System", "Настройки сохранены", "system")

    def clear_messages(self):
        self.messages.clear()
        self.save_data()
        self.update_logs_display()
        self.message_count = 0
        self.stat_labels["Сообщений"].configure(text="0")

    def clear_leads(self):
        self.leads.clear()
        self.save_data()
        self.update_leads_display()
        self.lead_count = 0
        self.stat_labels["Лидов"].configure(text="0")

    def update_status_badge(self, online: bool):
        if online:
            self.status_badge.configure(text="Online", fg_color="#10b981")
        else:
            self.status_badge.configure(text="Offline", fg_color="#6b7280")

    def add_log(self, sender: str, text: str, direction: str, has_image: bool = False, has_location: bool = False):
        log = MessageLog(
            id=datetime.now().strftime("%Y%m%d%H%M%S%f"),
            timestamp=datetime.now().strftime("%H:%M:%S"),
            chat_id=0,
            sender=sender,
            text=text,
            direction=direction,
            has_image=has_image,
            has_location=has_location
        )
        self.messages.append(log)
        self.save_data()
        self.message_count = len(self.messages)
        self.root.after(10, self.update_logs_display)

    def update_logs_display(self):
        # Clear existing
        for widget in self.control_logs.winfo_children():
            widget.destroy()
        for widget in self.full_logs.winfo_children():
            widget.destroy()

        # Render last 50 logs
        for log in self.messages[-50:][::-1]:
            self._create_log_entry(self.control_logs, log)
            self._create_log_entry(self.full_logs, log)

        self.stat_labels["Сообщений"].configure(text=str(self.message_count))

    def _create_log_entry(self, parent, log: MessageLog):
        colors = {
            "in": "#3b82f6",
            "out": "#10b981",
            "system": "#6b7280",
            "error": "#ef4444",
            "lead": "#f59e0b"
        }
        bg_colors = {
            "in": "transparent",
            "out": "transparent",
            "system": "transparent",
            "error": "transparent",
            "lead": "#2d1f0d"
        }

        frame = ctk.CTkFrame(parent, fg_color=bg_colors.get(log.direction, "transparent"), corner_radius=0)
        frame.pack(fill="x", pady=2)

        # Left border color indicator
        indicator = ctk.CTkFrame(frame, width=3, fg_color=colors.get(log.direction, "#6b7280"), corner_radius=0)
        indicator.pack(side="left", fill="y")

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        # Time
        ctk.CTkLabel(content, text=log.timestamp, text_color="#6b7280", font=("", 11), width=60, anchor="w").pack(side="left")

        # Sender
        ctk.CTkLabel(content, text=log.sender, text_color="#10b981", font=("", 11, "bold"), width=80, anchor="w").pack(side="left")

        # Message
        icon = ""
        if log.has_image:
            icon = "🖼️ "
        elif log.has_location:
            icon = "📍 "

        ctk.CTkLabel(content, text=f"{icon}{log.text}", text_color="#e5e7eb", font=("", 11), anchor="w").pack(side="left", fill="x", expand=True)

    def update_leads_display(self):
        for widget in self.leads_list.winfo_children():
            widget.destroy()

        if not self.leads:
            ctk.CTkLabel(self.leads_list, text="Нет лидов", text_color="#6b7280", font=("", 14)).pack(pady=50)
            return

        for lead in self.leads[-20:][::-1]:
            self._create_lead_card(lead)

        self.stat_labels["Лидов"].configure(text=str(len(self.leads)))

    def _create_lead_card(self, lead: Lead):
        urgency_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#10b981"}

        card = ctk.CTkFrame(self.leads_list, fg_color="#1a1a2e", corner_radius=8)
        card.pack(fill="x", pady=5, padx=5)

        # Left border
        border = ctk.CTkFrame(card, width=4, fg_color="#f59e0b", corner_radius=0)
        border.pack(side="left", fill="y")

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="x", expand=True, padx=15, pady=12)

        # Header row
        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(header, text=f"👤 {lead.client_name}", font=("", 13, "bold"), text_color="#f59e0b").pack(side="left")
        
        type_badge = ctk.CTkLabel(header, text=lead.lead_type, font=("", 10), fg_color="#3d2f0d", corner_radius=4, padx=8)
        type_badge.pack(side="left", padx=10)

        # Summary
        ctk.CTkLabel(content, text=lead.summary, font=("", 11), text_color="#9ca3af", wraplength=600, justify="left").pack(fill="x", pady=(5, 0))

        # Meta row
        meta = ctk.CTkFrame(content, fg_color="transparent")
        meta.pack(fill="x", pady=(5, 0))

        confidence = int((lead.confidence or 0.5) * 100)
        ctk.CTkLabel(meta, text=f"📊 {confidence}%", font=("", 10), text_color="#6b7280").pack(side="left")
        
        urgency_color = urgency_colors.get(lead.urgency, "#f59e0b")
        ctk.CTkLabel(meta, text=f"⚡ {lead.urgency}", font=("", 10), text_color=urgency_color).pack(side="left", padx=15)
        
        ctk.CTkLabel(meta, text=f"🕐 {lead.timestamp}", font=("", 10), text_color="#6b7280").pack(side="left")

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
                        self.stat_labels["Аккаунт"].configure(text=info[:15] if len(info) > 15 else info)
                        self.add_log("System", f"Авторизован как {info}", "system")
                    elif status == "code_sent":
                        self.add_log("System", "Код отправлен в Telegram", "system")
                        messagebox.showinfo("Код", "Код отправлен в Telegram. Введите код.")
                    elif status == "signed_in":
                        self.bot_username = info
                        self.stat_labels["Аккаунт"].configure(text=info[:15] if len(info) > 15 else info)
                        self.add_log("System", f"Вход выполнен: {info}", "system")
                    elif status == "error":
                        self.add_log("Error", info, "error")
                        messagebox.showerror("Ошибка", info)
                        
                elif msg_type == "bot_start":
                    status, info = data
                    if status == "started":
                        self.start_btn.configure(state="disabled")
                        self.stop_btn.configure(state="normal")
                        self.update_status_badge(True)
                        self.stat_labels["Статус"].configure(text="Running")
                        self.add_log("System", "Бот запущен и слушает сообщения", "system")
                    elif status == "error":
                        self.add_log("Error", info, "error")
                        messagebox.showerror("Ошибка", info)
                        
                elif msg_type == "message":
                    self.add_log(
                        data["sender"], data["text"], data["direction"],
                        data.get("has_image", False), data.get("has_location", False)
                    )
                    
                elif msg_type == "location":
                    self.add_log(data["sender"], f"📍 Локация: {data['url']}", "in", has_location=True)
                    
                elif msg_type == "image":
                    self.add_log(data["sender"], f"🖼️ {data['description']}", "in", has_image=True)
                    
                elif msg_type == "sticker":
                    self.add_log(data["sender"], f"🎭 Стикер: {data['description']}", "in", has_image=True)
                    
                elif msg_type == "error":
                    self.add_log("Error", str(data), "error")
                    
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_messages)

    def run(self):
        self.root.mainloop()

    # =======================================================================
    # FALLBACK TKINTER UI
    # =======================================================================
    def setup_tk_ui(self):
        self.root = tk.Tk()
        self.root.title(f"🥷 Ninja Userbot - Sog'lom taom")
        self.root.geometry("900x700")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Control Tab
        control_tab = ttk.Frame(notebook)
        notebook.add(control_tab, text="🎮 Управление")
        self.setup_tk_control_tab(control_tab)

        # Leads Tab
        leads_tab = ttk.Frame(notebook)
        notebook.add(leads_tab, text="🎯 Лиды")
        self.leads_text = scrolledtext.ScrolledText(leads_tab)
        self.leads_text.pack(fill="both", expand=True, padx=5, pady=5)

        # Settings Tab
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="⚙️ Настройки")
        self.setup_tk_settings_tab(settings_tab)

        # Logs Tab
        logs_tab = ttk.Frame(notebook)
        notebook.add(logs_tab, text="📋 Логи")
        self.logs_text = scrolledtext.ScrolledText(logs_tab)
        self.logs_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.status_var = tk.StringVar(value="Готов")
        ttk.Label(self.root, textvariable=self.status_var).pack(fill="x", side="bottom")

    def setup_tk_control_tab(self, parent):
        # Auth
        auth_frame = ttk.LabelFrame(parent, text="📱 Авторизация")
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
        control_frame = ttk.LabelFrame(parent, text="🤖 Управление")
        control_frame.pack(fill="x", padx=10, pady=10)

        self.start_btn = ttk.Button(control_frame, text="▶ Запустить", command=self.start_bot)
        self.start_btn.pack(side="left", padx=10, pady=10)
        self.stop_btn = ttk.Button(control_frame, text="⏹ Остановить", command=self.stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)

        # Logs
        ttk.Label(parent, text="📋 Логи:").pack(anchor="w", padx=10)
        self.control_logs = scrolledtext.ScrolledText(parent, height=15)
        self.control_logs.pack(fill="both", expand=True, padx=10, pady=5)

    def setup_tk_settings_tab(self, parent):
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)

        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Telegram
        ttk.Label(scrollable, text="📱 Telegram", font=("", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        ttk.Label(scrollable, text="API ID:").pack(anchor="w", padx=10)
        self.api_id_entry = ttk.Entry(scrollable, width=40)
        self.api_id_entry.pack(anchor="w", padx=10, pady=(0, 5))
        self.api_id_entry.insert(0, self.config.get("api_id", ""))
        
        ttk.Label(scrollable, text="API Hash:").pack(anchor="w", padx=10)
        self.api_hash_entry = ttk.Entry(scrollable, width=40, show="*")
        self.api_hash_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.api_hash_entry.insert(0, self.config.get("api_hash", ""))

        # Mistral
        ttk.Label(scrollable, text="🤖 Mistral AI", font=("", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        ttk.Label(scrollable, text="API Key:").pack(anchor="w", padx=10)
        self.mistral_key_entry = ttk.Entry(scrollable, width=40, show="*")
        self.mistral_key_entry.pack(anchor="w", padx=10, pady=(0, 10))
        self.mistral_key_entry.insert(0, self.config.get("mistral_key", ""))

        # Prompt
        ttk.Label(scrollable, text="💬 Системный промпт:").pack(anchor="w", padx=10, pady=(10, 5))
        self.prompt_text = scrolledtext.ScrolledText(scrollable, height=15, width=60)
        self.prompt_text.pack(anchor="w", padx=10, pady=(0, 10))
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        ttk.Button(scrollable, text="💾 Сохранить", command=self.save_settings).pack(pady=10)


# ===========================================================================
# MAIN
# ===========================================================================
if __name__ == "__main__":
    app = NinjaApp()
    app.run()
