"""
Ninja Userbot - Telegram Auto-Reply with AI
Runs as YOUR Telegram account (Userbot, not Bot)
Supports images via Mistral Vision API (Pixtral)
Universal OpenAI-compatible API for text generation
Lead tracking to Saved Messages
Order Management with payment checks, locations, and date verification
"""

import asyncio
import json
import os
import sys
import base64
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union, Dict, List
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User, MessageMediaGeo, MessageMediaGeoLive, MessageMediaPhoto, DocumentAttributeSticker
from telethon.tl.types import MessageMediaDocument, InputMediaGeo, InputGeoPoint

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", Path.home() / ".ninja-data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
LEADS_FILE = DATA_DIR / "leads.json"
ORDERS_FILE = DATA_DIR / "orders.json"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Company Info for Context
COMPANY_INFO = """
КОМПАНИЯ: Sog'lom taom (Соғлом таом) - здоровое питание с доставкой
ЛОКАЦИЯ: Ташкент, Сергели район (ошхона)
ГРАФИК: 5-дневка (пн-пт), шанба - день уборки

ПАКЕТЫ:
- Классик: стандартное меню
- Индивидуал: можно исключить до 3 продуктов (аллергия/не нравится)
- Диабет: специальное меню для диабетиков

КАЛОРИИ И ЦЕНЫ (актуальные):
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

ПРАВИЛА:
- 15 дней на изменение списка исключений
- Шанба: 2 пакета в пятницу для непрерывного питания
- Результат: 5-7 кг в месяц при соблюдении графика

БЖУ: 30% белок, 20% жиры, 50% углеводы
Шакар: 10г на порцию (сахар безопаснее сахарозаменителей!)

КАРТЫ:
- Humo: 9860010112421465
- Uzum: 4916990324223715
- Uzcard: 5614681209925290
- Получатель: Xodjimuratov Bahodir

ИНСТАГРАМ: @soglom.taom
ТЕЛЕГРАМ КАНАЛ: @soglomtaom
"""

DEFAULT_CONFIG = {
    "api_id": "36244324",
    "api_hash": "15657d847ab4b8ae111ade8e2cbca51f",
    # Vision API (Pixtral/Mistral for image descriptions)
    "mistral_key": "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v",
    "mistral_model": "pixtral-12b-2409",
    # OpenAI-compatible API (for text generation)
    "api_base_url": "",
    "api_key": "",
    "model": "",
    "system_prompt": "",
    "lead_prompt": "",
    # Courier usernames (comma-separated)
    "couriers": "",
}

# Days mapping for Russian
DAYS_RU = {
    'monday': 'понедельник',
    'tuesday': 'вторник',
    'wednesday': 'среда',
    'thursday': 'четверг',
    'friday': 'пятница',
    'saturday': 'суббота',
    'sunday': 'воскресенье'
}

DAYS_UZ = {
    'monday': 'душанба',
    'tuesday': 'сешанба',
    'wednesday': 'чоршанба',
    'thursday': 'пайшанба',
    'friday': 'жума',
    'saturday': 'шанба',
    'sunday': 'якшанба'
}

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

ПОВЕДЕНИЕ ПРИ СТИКЕРАХ:
Когда клиент присылает стикер - ответь эмодзи или коротким сообщением, как бы ответил реальный человек.
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

# ---------------------------------------------------------------------------
# Data Classes for Order Management
# ---------------------------------------------------------------------------
@dataclass
class ClientOrder:
    chat_id: int
    client_name: str
    phone: str = ""
    address: str = ""
    location_url: str = ""
    location_lat: float = 0.0  # Широта для нативной геолокации
    location_lon: float = 0.0  # Долгота для нативной геолокации
    calories: str = ""
    package_type: str = "classic"  # classic, individual, diabetic
    days: int = 0
    delivery_date: str = ""
    price_per_day: int = 0
    total_price: int = 0
    payment_confirmed: bool = False
    check_image_path: str = ""
    check_image_file: str = ""  # Путь к файлу чека для отправки
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self):
        return asdict(self)

@dataclass
class MessageContext:
    has_image: bool = False
    has_location: bool = False
    has_sticker: bool = False
    location_lat: float = 0.0
    location_lon: float = 0.0
    image_description: str = ""
    sticker_emoji: str = ""
    is_check: bool = False
    is_courier: bool = False

# Global state
HISTORY_LIMIT = 20
conversation_history: dict[int, list[dict]] = {}
message_logs: list = []
leads_log: list = []
orders: Dict[int, ClientOrder] = {}  # chat_id -> ClientOrder

# Bot instance and state
client: Optional[TelegramClient] = None
bot_running = False
bot_username: Optional[str] = None
message_count = 0
lead_count = 0
config: dict = {}

auth_state = {
    "step": "idle",
    "phone": None,
    "phone_code_hash": None,
    "error": None
}

# Background task reference
bot_task: Optional[asyncio.Task] = None

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                cfg.update(loaded)
        except:
            pass
    if not cfg.get("system_prompt"):
        cfg["system_prompt"] = DEFAULT_SYSTEM_PROMPT
    if not cfg.get("lead_prompt"):
        cfg["lead_prompt"] = DEFAULT_LEAD_PROMPT
    return cfg

def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_logs() -> list:
    if LOGS_FILE.exists():
        try:
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_logs() -> None:
    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(message_logs[-500:], f, indent=2, ensure_ascii=False)

def load_leads() -> list:
    if LEADS_FILE.exists():
        try:
            with open(LEADS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_leads() -> None:
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads_log[-200:], f, indent=2, ensure_ascii=False)

def load_orders() -> Dict[int, ClientOrder]:
    if ORDERS_FILE.exists():
        try:
            with open(ORDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): ClientOrder(**v) for k, v in data.items()}
        except:
            pass
    return {}

def save_orders() -> None:
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v.to_dict() for k, v in orders.items()}, f, indent=2, ensure_ascii=False)

def add_log(message: str, sender: str = "System", direction: str = "system", has_image: bool = False, has_location: bool = False):
    display_msg = message[:200] if len(message) > 200 else message
    prefix = ""
    if has_image:
        prefix = "[IMAGE] "
    if has_location:
        prefix = "[LOCATION] "
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "sender": sender,
        "message": prefix + display_msg,
        "direction": direction,
        "has_image": has_image,
        "has_location": has_location
    }
    message_logs.append(entry)
    save_logs()
    print(f"[{direction}] {sender}: {prefix}{display_msg}")

def add_lead(lead_data: dict, client_name: str, chat_id: int):
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "client_name": client_name,
        "chat_id": chat_id,
        **lead_data
    }
    leads_log.append(entry)
    save_leads()

# Price mapping
PRICE_MAP = {
    "1000-1200": 84000,
    "1400-1600": 98000,
    "1800-2000": 112000,
    "2200-2500": 126000,
}

def get_price_for_calories(calories: str) -> int:
    """Get price based on calorie range"""
    calories = calories.replace(" ", "").replace("ккал", "").replace("kcal", "")
    for range_str, price in PRICE_MAP.items():
        if range_str in calories or calories in range_str:
            return price
    # Try to parse numeric value
    try:
        cal_val = int(calories.replace("-", "").replace("–", ""))
        if cal_val <= 1200:
            return 84000
        elif cal_val <= 1600:
            return 98000
        elif cal_val <= 2000:
            return 112000
        else:
            return 126000
    except:
        return 0

def check_delivery_date_possible(requested_date: datetime) -> dict:
    """
    Check if delivery is possible on the requested date.
    Returns dict with 'possible', 'reason', 'next_available'
    """
    now = datetime.now()
    today_deadline = now.replace(hour=21, minute=0, second=0, microsecond=0)
    
    # Check if it's Saturday (kitchen closed)
    if requested_date.weekday() == 5:  # Saturday
        next_day = requested_date + timedelta(days=1)  # Sunday
        return {
            "possible": False,
            "reason": "В субботу кухня закрыта (день уборки)",
            "next_available": next_day.strftime("%d.%m.%Y")
        }
    
    # Check deadline
    if requested_date.date() == now.date():
        # Delivery today - check if before 21:00
        if now.hour >= 21:
            tomorrow = now + timedelta(days=1)
            if tomorrow.weekday() == 5:  # Skip Saturday
                tomorrow += timedelta(days=1)
            return {
                "possible": False,
                "reason": "Уже после 21:00, заказы принимаются до 21:00 за день до доставки",
                "next_available": tomorrow.strftime("%d.%m.%Y")
            }
    elif requested_date.date() == (now + timedelta(days=1)).date():
        # Delivery tomorrow - check if before 21:00 today
        if now.hour >= 21:
            day_after = now + timedelta(days=2)
            if day_after.weekday() == 5:  # Skip Saturday
                day_after += timedelta(days=1)
            return {
                "possible": False,
                "reason": "Уже после 21:00, завтра доставка невозможна",
                "next_available": day_after.strftime("%d.%m.%Y")
            }
    
    return {
        "possible": True,
        "reason": "OK",
        "next_available": requested_date.strftime("%d.%m.%Y")
    }

def parse_delivery_date(text: str) -> Optional[datetime]:
    """Parse delivery date from text"""
    text = text.lower()
    now = datetime.now()
    
    # Check for "today"/"сегодня"/"бугун"
    if any(word in text for word in ['сегодня', 'бугун', 'today', 'сёгун', 'bugun']):
        return now
    
    # Check for "tomorrow"/"завтра"/"эртага"
    if any(word in text for word in ['завтра', 'эртага', 'tomorrow', 'ertaga']):
        return now + timedelta(days=1)
    
    # Check for day of week
    day_mapping = {
        'понедельник': 0, 'душанба': 0, 'monday': 0, 'пн': 0,
        'вторник': 1, 'сешанба': 1, 'tuesday': 1, 'вт': 1,
        'среда': 2, 'чоршанба': 2, 'wednesday': 2, 'ср': 2,
        'четверг': 3, 'пайшанба': 3, 'thursday': 3, 'чт': 3,
        'пятница': 4, 'жума': 4, 'friday': 4, 'пт': 4,
        'суббота': 5, 'шанба': 5, 'saturday': 5, 'сб': 5,
        'воскресенье': 6, 'якшанба': 6, 'sunday': 6, 'вс': 6,
    }
    
    for day_name, day_num in day_mapping.items():
        if day_name in text:
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return now + timedelta(days=days_ahead)
    
    # Check for date patterns like "15.05", "15 мая", "15-may"
    date_pattern = r'(\d{1,2})[.\s/-](\d{1,2})'
    match = re.search(date_pattern, text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        try:
            date = now.replace(day=day, month=month)
            if date < now:
                date = date.replace(year=date.year + 1)
            return date
        except:
            pass
    
    return None

async def download_and_encode_image(msg) -> Optional[str]:
    global client
    try:
        if not msg.media:
            return None
        if isinstance(msg.media, MessageMediaPhoto):
            photo = msg.media.photo
            if photo:
                file_path = await client.download_media(photo, IMAGES_DIR)
                with open(file_path, "rb") as f:
                    image_data = f.read()
                ext = Path(file_path).suffix.lower()
                mime_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
                mime_type = mime_types.get(ext, 'image/jpeg')
                base64_data = base64.b64encode(image_data).decode('utf-8')
                data_url = f"data:{mime_type};base64,{base64_data}"
                # Keep file for order records
                return data_url
        return None
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

async def save_image_for_order(msg, chat_id: int) -> Optional[str]:
    """Save image and return file path"""
    global client
    try:
        if not msg.media:
            return None
        if isinstance(msg.media, MessageMediaPhoto):
            photo = msg.media.photo
            if photo:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = IMAGES_DIR / f"check_{chat_id}_{timestamp}.jpg"
                await client.download_media(photo, file_path)
                return str(file_path)
        return None
    except Exception as e:
        print(f"Error saving image: {e}")
        return None

# ---------------------------------------------------------------------------
# AI API Functions
# ---------------------------------------------------------------------------
async def describe_image_with_pixtral(image_url: str, mistral_key: str, model: str = "pixtral-12b-2409") -> str:
    """Describe image using Pixtral vision model (Mistral)"""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"}
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": """Проанализируй это изображение. Это может быть:
1. Чек об оплате (перевод денег)
2. Скриншот приложения банка
3. Фото продукта
4. Другое

Если это чек/перевод, укажи:
- Сумму перевода
- Дату и время если видны
- Номер карты получателя если виден
- Имя получателя если видно

Отвечай на русском языке кратко и по делу."""},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }
    ]
    
    payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 500}
    
    async with httpx.AsyncClient(timeout=120) as http_client:
        r = await http_client.post(url, headers=headers, json=payload)
        if r.status_code != 200:
            raise Exception(f"Pixtral API Error {r.status_code}: {r.text}")
        return r.json()["choices"][0]["message"]["content"].strip()

async def call_openai_compatible(messages: list[dict], base_url: str, api_key: str, model: str) -> str:
    """Call any OpenAI-compatible API"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # Convert messages to text-only format
    clean_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text parts
            text_parts = []
            for item in content:
                if item.get("type") == "text":
                    text_parts.append(item["text"])
            content = "\n".join(text_parts)
        clean_messages.append({
            "role": msg["role"],
            "content": str(content)
        })
    
    payload = {
        "model": model,
        "messages": clean_messages,
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": False
    }
    
    async with httpx.AsyncClient(timeout=120) as http_client:
        r = await http_client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            raise Exception(f"API Error {r.status_code}: {r.text}")
        return r.json()["choices"][0]["message"]["content"].strip()

async def call_ai(messages: list[dict], cfg: dict) -> str:
    """Main AI function - handles images with Pixtral, text with OpenAI-compatible API"""
    base_url = cfg.get("api_base_url", "")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "")
    
    if not base_url or not model:
        raise Exception("Настройте API Base URL и Model в настройках")
    
    # Add current date/time context
    now = datetime.now()
    time_context = f"\n\n[ТЕКУЩЕЕ ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')} ({DAYS_RU.get(now.strftime('%A').lower(), now.strftime('%A'))})]"
    time_context += f"\n[СЕЙЧАС {now.strftime('%H:%M')}, ДЕДЛАЙН ЗАКАЗА НА ЗАВТРА: 21:00]"
    if now.hour >= 21:
        time_context += "\n[ВНИМАНИЕ: Уже после 21:00, заказы на завтра не принимаются!]"
    
    # Add time context to system message
    messages_with_time = messages.copy()
    if messages_with_time and messages_with_time[0]["role"] == "system":
        messages_with_time[0] = {
            "role": "system",
            "content": messages_with_time[0]["content"] + time_context
        }
    
    # Check if there are images in messages
    has_image = False
    image_url = None
    for msg in messages_with_time:
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "image_url":
                    has_image = True
                    image_url = item.get("image_url", {}).get("url", "")
                    break
        if has_image:
            break
    
    # If image exists, describe it with Pixtral first
    if has_image and image_url:
        mistral_key = cfg.get("mistral_key", "")
        mistral_model = cfg.get("mistral_model", "pixtral-12b-2409")
        
        if not mistral_key:
            raise Exception("Для обработки изображений нужен Mistral API ключ (Pixtral)")
        
        # Describe image with Pixtral
        image_description = await describe_image_with_pixtral(image_url, mistral_key, mistral_model)
        
        # Replace image with description in messages
        for msg in messages_with_time:
            content = msg.get("content", "")
            if isinstance(content, list):
                new_content = []
                for item in content:
                    if item.get("type") == "text":
                        new_content.append(item)
                    elif item.get("type") == "image_url":
                        new_content.append({
                            "type": "text",
                            "text": f"\n[ИЗОБРАЖЕНИЕ: {image_description}]\n"
                        })
                msg["content"] = new_content
    
    # Call the OpenAI-compatible API
    return await call_openai_compatible(messages_with_time, base_url, api_key, model)

async def analyze_lead(conversation: list[dict], cfg: dict) -> dict:
    try:
        messages = [
            {"role": "system", "content": DEFAULT_LEAD_PROMPT},
            {"role": "user", "content": f"Проанализируй переписку:\n\n{json.dumps(conversation, ensure_ascii=False, indent=2)}"}
        ]
        result = await call_ai(messages, cfg)
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"is_lead": False}
    except Exception as e:
        print(f"Lead analysis error: {e}")
        return {"is_lead": False}

def add_to_history(chat_id: int, role: str, content: Union[str, list], context: MessageContext = None) -> None:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    
    # Add context info to content
    if context:
        if isinstance(content, str):
            if context.has_location:
                content = f"[ЛОКАЦИЯ: {context.location_lat}, {context.location_lon}]\n{content}"
            if context.has_sticker:
                content = f"[СТИКЕР: {context.sticker_emoji}]\n{content}"
    
    conversation_history[chat_id].append({"role": role, "content": content})
    if len(conversation_history[chat_id]) > HISTORY_LIMIT:
        conversation_history[chat_id] = conversation_history[chat_id][-HISTORY_LIMIT:]

def get_conversation_messages(chat_id: int, system_prompt: str) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    if chat_id in conversation_history:
        messages.extend(conversation_history[chat_id])
    return messages

# ---------------------------------------------------------------------------
# Courier Detection
# ---------------------------------------------------------------------------
def is_courier(sender: User, cfg: dict) -> bool:
    """Check if sender is a courier based on config"""
    couriers = cfg.get("couriers", "")
    if not couriers:
        return False
    courier_list = [c.strip().lower().replace("@", "") for c in couriers.split(",")]
    sender_username = (sender.username or "").lower()
    sender_name = (sender.first_name or "").lower()
    return any(c in sender_username or c in sender_name for c in courier_list)

async def handle_courier_message(chat_id: int, sender: User, message):
    """Handle messages from couriers differently"""
    global client, config
    
    sender_name = sender.first_name or sender.last_name or str(sender.id)
    text = (message.text or "").strip()
    
    add_log(f"[КУРЬЕР] {text}", sender_name, "courier")
    
    # Simple acknowledgment for couriers
    try:
        # Check for delivery confirmation patterns
        if any(word in text.lower() for word in ['доставил', 'отдал', ' delivered', 'етказдим']):
            await client.send_message(chat_id, "Хоп, отмечаем! Рахмат 👍")
            # Also send to saved messages
            me = await client.get_me()
            await client.send_message(me.id, f"📦 КУРЬЕР ДОСТАВИЛ\n\n👤 {sender_name}\n📱 @{sender.username or 'нет username'}\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n💬 {text}")
        elif any(word in text.lower() for word in ['не нашел', 'не открыл', 'не ответил', 'no answer']):
            await client.send_message(chat_id, "Понял, щас позвоню клиенту")
            # Notify in saved messages
            me = await client.get_me()
            await client.send_message(me.id, f"⚠️ ПРОБЛЕМА С ДОСТАВКОЙ\n\n👤 {sender_name}\n💬 {text}\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        else:
            await client.send_message(chat_id, "Принял, спасибо")
    except Exception as e:
        add_log(f"Ошибка ответа курьеру: {e}", "System", "error")

# ---------------------------------------------------------------------------
# Telegram Bot Logic
# ---------------------------------------------------------------------------
async def send_order_to_saved_messages(order: ClientOrder, check_image_path: str = None):
    """Send complete order info to Saved Messages with native location"""
    global client
    try:
        me = await client.get_me()
        
        # Send check image first if available
        if check_image_path and Path(check_image_path).exists():
            try:
                await client.send_file(me.id, check_image_path, caption="💳 Чек об оплате")
                add_log("Чек отправлен в Saved Messages", "System", "order")
            except Exception as e:
                add_log(f"Ошибка отправки чека: {e}", "System", "error")
        
        # Send native location if coordinates available
        if order.location_lat != 0.0 and order.location_lon != 0.0:
            try:
                geo_point = InputGeoPoint(lat=order.location_lat, long=order.location_lon)
                geo_media = InputMediaGeo(geo_point=geo_point)
                await client.send_message(me.id, file=geo_media)
                add_log(f"Локация отправлена: {order.location_lat}, {order.location_lon}", "System", "order")
            except Exception as e:
                add_log(f"Ошибка отправки локации: {e}", "System", "error")
        
        # Build order message
        location_info = ""
        if order.location_lat != 0.0 and order.location_lon != 0.0:
            location_info = f"🗺 Локация: {order.location_lat:.6f}, {order.location_lon:.6f}"
        elif order.location_url:
            location_info = f"🗺 Ссылка: {order.location_url}"
        else:
            location_info = "🗺 Локация: не указана"
        
        message = f"""✅ ЗАКАЗ ОФОРМЛЕН

👤 Клиент: {order.client_name}
📱 Телефон: {order.phone or 'не указан'}
📍 Адрес: {order.address or 'не указан'}
{location_info}

📦 Пакет: {order.package_type}
🔥 Калории: {order.calories or 'не указаны'}
📅 Дней: {order.days or 'не указано'}
🚚 Доставка: {order.delivery_date or 'не указана'}

💰 Цена за день: {order.price_per_day:,} сум
💰 Итого: {order.total_price:,} сум

💳 Оплата: {'✅ Подтверждена' if order.payment_confirmed else '⏳ Ожидает'}

📝 Заметки: {order.notes or 'нет'}

🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
        
        # Send text message
        await client.send_message(me.id, message)
        
        add_log(f"Заказ сохранён: {order.client_name}", "System", "order")
    except Exception as e:
        add_log(f"Ошибка сохранения заказа: {e}", "System", "error")

async def send_to_saved_messages(lead_data: dict, client_name: str, chat_id: int):
    global client
    try:
        urgency_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        emoji = urgency_emoji.get(lead_data.get("urgency", "medium"), "🟡")
        message = f"""{emoji} НОВЫЙ ЛИД!

👤 Клиент: {client_name}
📱 Chat ID: {chat_id}
📋 Тип: {lead_data.get('lead_type', 'new_client')}
⏰ Срочность: {lead_data.get('urgency', 'medium')}

📝 Что нужно:
{lead_data.get('summary', 'Связаться с клиентом')}

📊 Уверенность: {lead_data.get('confidence', 0.5) * 100:.0f}%

🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
        me = await client.get_me()
        await client.send_message(me.id, message)
        add_log(f"Лид сохранён: {client_name}", "System", "lead")
    except Exception as e:
        add_log(f"Ошибка сохранения лида: {e}", "System", "error")

async def handle_message(chat_id: int, sender: User, message):
    global client, config, message_count, lead_count, orders
    
    sender_name = sender.first_name or sender.last_name or str(sender.id)
    text = (message.text or "").strip()
    
    # Create message context
    context = MessageContext()
    
    # Check for location
    if message.media:
        if isinstance(message.media, (MessageMediaGeo, MessageMediaGeoLive)):
            context.has_location = True
            geo = message.media.geo
            context.location_lat = geo.lat
            context.location_lon = geo.long
            add_log(f"Геолокация: {geo.lat}, {geo.long}", sender_name, "incoming", has_location=True)
        elif isinstance(message.media, MessageMediaPhoto):
            # Handle image
            image_url = await download_and_encode_image(message)
            if image_url:
                context.has_image = True
                context.image_url = image_url
                # Save image for order
                check_path = await save_image_for_order(message, chat_id)
                if check_path:
                    if chat_id not in orders:
                        orders[chat_id] = ClientOrder(
                            chat_id=chat_id,
                            client_name=sender_name,
                            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                    orders[chat_id].check_image_path = check_path
                    save_orders()
        elif hasattr(message.media, 'document'):
            # Check for sticker
            doc = message.media.document
            if doc and hasattr(doc, 'attributes'):
                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeSticker):
                        context.has_sticker = True
                        context.sticker_emoji = attr.alt or "👍"
                        add_log(f"Стикер: {context.sticker_emoji}", sender_name, "incoming")
                        break
    
    if not text and not context.has_image and not context.has_location and not context.has_sticker:
        return
    
    if not context.has_location and not context.has_sticker:
        add_log(text if text else "(изображение)", sender_name, "incoming", has_image=context.has_image)
    
    # Update or create order
    if chat_id not in orders:
        orders[chat_id] = ClientOrder(
            chat_id=chat_id,
            client_name=sender_name,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    
    order = orders[chat_id]
    order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Update order details from message
    if context.has_location:
        order.location_url = f"https://maps.google.com/maps?q={context.location_lat},{context.location_lon}"
        order.location_lat = context.location_lat
        order.location_lon = context.location_lon
    
    # Parse delivery date from message
    delivery_date = parse_delivery_date(text)
    if delivery_date:
        date_check = check_delivery_date_possible(delivery_date)
        if date_check["possible"]:
            order.delivery_date = delivery_date.strftime("%d.%m.%Y")
        else:
            # Add date issue to context for AI
            text += f"\n[СИСТЕМА: {date_check['reason']}. Ближайшая дата: {date_check['next_available']}]"
    
    # Parse calories from message
    cal_match = re.search(r'(\d{4}[\s-]?\d{3,4})\s*(ккал|kcal)?', text, re.IGNORECASE)
    if cal_match:
        order.calories = cal_match.group(1).replace(" ", "")
        order.price_per_day = get_price_for_calories(order.calories)
    
    # Parse days count
    days_match = re.search(r'(\d+)\s*(день|дней|кунь|кун)', text, re.IGNORECASE)
    if days_match:
        order.days = int(days_match.group(1))
        order.total_price = order.price_per_day * order.days
    
    # Parse phone number
    phone_match = re.search(r'(\+?998\d{9})', text)
    if phone_match:
        order.phone = phone_match.group(1)
    
    # Parse address (simple pattern for Uzbek addresses)
    if not order.address:
        # Look for district + address pattern
        addr_patterns = [
            r'(район|массив|туман).*?(дом|уй|кв|квартира).*?\d+',
            r'(Чилонзор|Сергели|Юнусабад|Мирабад|Яккасарай|Шайхантаур|Учтепа|Алмазар|Яшнобод|Бектемир).*?\d+',
        ]
        for pattern in addr_patterns:
            addr_match = re.search(pattern, text, re.IGNORECASE)
            if addr_match:
                order.address = addr_match.group(0)
                break
    
    save_orders()
    
    # Build message for AI
    if context.has_image:
        content = []
        if text:
            content.append({"type": "text", "text": text})
        content.append({"type": "image_url", "image_url": {"url": context.image_url}})
        add_to_history(chat_id, "user", content, context)
    elif context.has_sticker:
        add_to_history(chat_id, "user", f"[СТИКЕР: {context.sticker_emoji}] {text}", context)
    else:
        add_to_history(chat_id, "user", text, context)
    
    try:
        async with client.action(chat_id, "typing"):
            messages = get_conversation_messages(chat_id, config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
            reply = await call_ai(messages, config)
    except Exception as e:
        add_log(f"AI Error: {e}", "System", "error")
        return
    
    try:
        add_to_history(chat_id, "assistant", reply)
        await client.send_message(chat_id, reply)
        message_count += 1
        add_log(reply, sender_name, "outgoing")
        
        # Check for payment confirmation in reply
        if any(word in reply.lower() for word in ['отметили', 'приняли', 'подтвержд', 'хоп', 'рахмат', 'спасибо']):
            if any(word in reply.lower() for word in ['чек', 'оплата', 'оплат', 'перевод']):
                order.payment_confirmed = True
                save_orders()
                
                # If we have all order details, send to saved messages
                if order.payment_confirmed and order.phone and order.calories:
                    await send_order_to_saved_messages(order, order.check_image_path)
        
        # Analyze for leads every 3 messages
        msg_count = len(conversation_history.get(chat_id, []))
        if msg_count >= 3 and msg_count % 3 == 0:
            try:
                conv_for_analysis = []
                for msg in conversation_history.get(chat_id, []):
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                        conv_for_analysis.append({"role": msg["role"], "content": " ".join(text_parts) + " [изображение]"})
                    else:
                        conv_for_analysis.append(msg)
                
                lead_result = await analyze_lead(conv_for_analysis, config)
                if lead_result.get("is_lead") and lead_result.get("confidence", 0) >= 0.6:
                    add_lead(lead_result, sender_name, chat_id)
                    lead_count += 1
                    
                    # Update order from lead analysis
                    order_details = lead_result.get("order_details", {})
                    if order_details:
                        if order_details.get("calories"):
                            order.calories = order_details["calories"]
                        if order_details.get("days"):
                            order.days = int(order_details["days"])
                        if order_details.get("address"):
                            order.address = order_details["address"]
                        if order_details.get("phone"):
                            order.phone = order_details["phone"]
                        if order_details.get("delivery_date"):
                            order.delivery_date = order_details["delivery_date"]
                        if order_details.get("payment_confirmed"):
                            order.payment_confirmed = True
                        save_orders()
                    
                    await send_to_saved_messages(lead_result, sender_name, chat_id)
            except Exception as e:
                print(f"Lead analysis error: {e}")
    except Exception as e:
        add_log(f"Send Error: {e}", "System", "error")

async def run_bot():
    global client, bot_running, bot_username, message_count, lead_count, config, auth_state, bot_task
    
    try:
        if not config.get("api_id") or not config.get("api_hash"):
            add_log("ОШИБКА: Настройте API ID и API Hash", "System", "error")
            return

        client = TelegramClient(str(SESSION_PATH), int(config["api_id"]), config["api_hash"])

        @client.on(events.NewMessage)
        async def handler(event):
            global bot_running
            if not bot_running:
                return
            if event.message.out or not event.is_private:
                return
            sender = await event.get_sender()
            if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                return
            
            # Check if sender is courier
            if is_courier(sender, config):
                await handle_courier_message(event.chat_id, sender, event.message)
                return
            
            await handle_message(event.chat_id, sender, event.message)

        add_log("Подключение к Telegram...", "System", "system")
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            bot_username = f"@{me.username}" if me.username else me.first_name
            bot_running = True
            auth_state["step"] = "done"
            add_log(f"✅ Вошел как {bot_username}", "System", "success")

            # Process unread messages
            add_log("Проверка непрочитанных сообщений...", "System", "system")
            unread_count = 0
            async for dialog in client.iter_dialogs(limit=100):
                try:
                    entity = dialog.entity
                    if not isinstance(entity, User):
                        continue
                    if entity.is_self or getattr(entity, 'bot', False):
                        continue
                    sender_name = entity.first_name or entity.last_name or str(entity.id)
                    if dialog.unread_count > 0:
                        add_log(f"{dialog.unread_count} сообщений от {sender_name}", "System", "system")
                        async for message in client.iter_messages(dialog.entity, limit=dialog.unread_count, reverse=True):
                            if not message.out:
                                # Check if courier
                                if is_courier(entity, config):
                                    await handle_courier_message(dialog.id, entity, message)
                                else:
                                    await handle_message(dialog.id, entity, message)
                                unread_count += 1
                        await client.send_read_acknowledge(dialog.entity)
                except Exception as e:
                    add_log(f"Ошибка: {e}", "System", "error")

            if unread_count > 0:
                add_log(f"Обработано {unread_count} сообщений", "System", "success")
            add_log("🚀 Юзербот работает! Отвечаю как сотрудник Sog'lom taom...", "System", "success")

            # Keep running until disconnected
            await client.run_until_disconnected()
        else:
            auth_state["step"] = "phone"
            auth_state["error"] = None
            add_log("📱 Требуется авторизация. Введите номер телефона в Web UI", "System", "system")

    except Exception as e:
        add_log(f"Ошибка: {e}", "System", "error")
        bot_running = False

async def start_bot():
    global bot_running, bot_task, config
    if bot_running:
        return
    config = load_config()
    bot_task = asyncio.create_task(run_bot())

async def stop_bot():
    global client, bot_running
    bot_running = False
    if client:
        await client.disconnect()
    add_log("Юзербот остановлен", "System", "info")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ConfigModel(BaseModel):
    api_id: str = ""
    api_hash: str = ""
    mistral_key: str = ""
    mistral_model: str = "pixtral-12b-2409"
    api_base_url: str = ""
    api_key: str = ""
    model: str = ""
    system_prompt: str = ""
    lead_prompt: str = ""
    couriers: str = ""

class PhoneModel(BaseModel):
    phone: str

class CodeModel(BaseModel):
    code: str

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global message_logs, leads_log, orders, config
    message_logs = load_logs()
    leads_log = load_leads()
    orders = load_orders()
    config = load_config()
    yield

app = FastAPI(title="Ninja Userbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    return {
        "running": bot_running,
        "username": bot_username,
        "message_count": message_count,
        "lead_count": lead_count,
        "active_orders": len([o for o in orders.values() if not o.payment_confirmed or o.delivery_date])
    }

@app.get("/api/config")
async def get_config():
    return config

@app.post("/api/config")
async def update_config(cfg: ConfigModel):
    global config
    save_config(cfg.model_dump())
    config = load_config()
    add_log("Настройки сохранены", "System", "system")
    return {"success": True}

@app.post("/api/start")
async def api_start_bot():
    await start_bot()
    return {"success": True, "message": "Starting..."}

@app.post("/api/stop")
async def api_stop_bot():
    await stop_bot()
    return {"success": True}

@app.get("/api/auth/status")
async def get_auth_status():
    return {
        "step": auth_state["step"],
        "error": auth_state.get("error"),
        "running": bot_running
    }

@app.post("/api/auth/phone")
async def send_phone(data: PhoneModel):
    global client, auth_state
    
    if client is None:
        if not config.get("api_id") or not config.get("api_hash"):
            return {"success": False, "error": "Настройте API ID и API Hash"}
        client = TelegramClient(str(SESSION_PATH), int(config["api_id"]), config["api_hash"])
        await client.connect()

    try:
        result = await client.send_code_request(data.phone)
        auth_state["phone"] = data.phone
        auth_state["phone_code_hash"] = result.phone_code_hash
        auth_state["step"] = "code"
        auth_state["error"] = None
        add_log(f"📱 Код отправлен на {data.phone}", "System", "system")
        return {"success": True, "message": "Code sent"}
    except Exception as e:
        auth_state["error"] = str(e)
        add_log(f"Ошибка отправки кода: {e}", "System", "error")
        return {"success": False, "error": str(e)}

@app.post("/api/auth/code")
async def send_code(data: CodeModel):
    global client, auth_state, bot_running, bot_username
    
    if client is None:
        return {"success": False, "error": "Client not initialized"}

    try:
        await client.sign_in(
            auth_state["phone"],
            data.code,
            phone_code_hash=auth_state["phone_code_hash"]
        )

        me = await client.get_me()
        bot_username = f"@{me.username}" if me.username else me.first_name
        bot_running = True
        auth_state["step"] = "done"
        auth_state["error"] = None

        add_log(f"✅ Вошел как {bot_username}", "System", "success")

        @client.on(events.NewMessage)
        async def handler(event):
            global bot_running
            if not bot_running:
                return
            if event.message.out or not event.is_private:
                return
            sender = await event.get_sender()
            if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                return
            
            # Check if courier
            if is_courier(sender, config):
                await handle_courier_message(event.chat_id, sender, event.message)
                return
            
            await handle_message(event.chat_id, sender, event.message)

        add_log("🚀 Юзербот работает!", "System", "success")
        asyncio.create_task(process_unread_messages())

        return {"success": True, "username": bot_username}
    except Exception as e:
        auth_state["error"] = str(e)
        add_log(f"Ошибка входа: {e}", "System", "error")
        return {"success": False, "error": str(e)}

async def process_unread_messages():
    global client, bot_running
    if not client or not bot_running:
        return
    
    add_log("Проверка непрочитанных сообщений...", "System", "system")
    unread_count = 0
    try:
        async for dialog in client.iter_dialogs(limit=100):
            try:
                entity = dialog.entity
                if not isinstance(entity, User):
                    continue
                if entity.is_self or getattr(entity, 'bot', False):
                    continue
                sender_name = entity.first_name or entity.last_name or str(entity.id)
                if dialog.unread_count > 0:
                    add_log(f"{dialog.unread_count} сообщений от {sender_name}", "System", "system")
                    async for message in client.iter_messages(dialog.entity, limit=dialog.unread_count, reverse=True):
                        if not message.out:
                            # Check if courier
                            if is_courier(entity, config):
                                await handle_courier_message(dialog.id, entity, message)
                            else:
                                await handle_message(dialog.id, entity, message)
                            unread_count += 1
                    await client.send_read_acknowledge(dialog.entity)
            except Exception as e:
                add_log(f"Ошибка: {e}", "System", "error")

        if unread_count > 0:
            add_log(f"Обработано {unread_count} сообщений", "System", "success")
    except Exception as e:
        add_log(f"Ошибка обработки: {e}", "System", "error")

@app.get("/api/logs")
async def get_logs():
    return message_logs[-100:]

@app.delete("/api/logs")
async def clear_logs():
    global message_logs
    message_logs = []
    save_logs()
    return {"success": True}

@app.get("/api/leads")
async def get_leads():
    return leads_log[-50:]

@app.delete("/api/leads")
async def clear_leads():
    global leads_log
    leads_log = []
    save_leads()
    return {"success": True}

@app.get("/api/orders")
async def get_orders():
    return {str(k): v.to_dict() for k, v in orders.items()}

@app.get("/api/orders/{chat_id}")
async def get_order(chat_id: int):
    if chat_id in orders:
        return orders[chat_id].to_dict()
    return {"error": "Order not found"}

@app.delete("/api/orders")
async def clear_orders():
    global orders
    orders = {}
    save_orders()
    return {"success": True}

@app.post("/api/orders/{chat_id}/confirm")
async def confirm_order_payment(chat_id: int):
    if chat_id in orders:
        orders[chat_id].payment_confirmed = True
        orders[chat_id].updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_orders()
        
        # Send to saved messages with check image
        await send_order_to_saved_messages(orders[chat_id], orders[chat_id].check_image_path)
        return {"success": True}
    return {"error": "Order not found"}

# ---------------------------------------------------------------------------
# Web UI (embedded)
# ---------------------------------------------------------------------------
WEB_UI_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🥷 Ninja Userbot - Sog'lom taom</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); min-height: 100vh; color: #fff; padding: 20px; }
        .container { max-width: 1100px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; padding: 15px 20px; background: rgba(255,255,255,0.05); border-radius: 12px; margin-bottom: 20px; }
        .header h1 { display: flex; align-items: center; gap: 10px; font-size: 22px; }
        .status-badge { padding: 6px 14px; border-radius: 16px; font-weight: 600; font-size: 13px; }
        .status-online { background: #10b981; }
        .status-offline { background: #6b7280; }
        .stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 20px; }
        .stat-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 15px; text-align: center; }
        .stat-card .value { font-size: 20px; font-weight: bold; color: #10b981; }
        .stat-card .label { color: #9ca3af; font-size: 12px; margin-top: 4px; }
        .stat-card.highlight { background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); }
        .tabs { display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab { padding: 10px 20px; background: rgba(255,255,255,0.05); border: none; color: #9ca3af; cursor: pointer; border-radius: 8px; font-size: 14px; transition: all 0.2s; }
        .tab.active { background: #10b981; color: #fff; }
        .tab:hover { background: rgba(255,255,255,0.1); }
        .panel { background: rgba(255,255,255,0.05); border-radius: 12px; padding: 20px; display: none; }
        .panel.active { display: block; }
        .btn { padding: 12px 24px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; margin-right: 10px; }
        .btn-primary { background: #10b981; color: #fff; }
        .btn-primary:hover { background: #059669; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-danger:hover { background: #dc2626; }
        .btn-secondary { background: #6b7280; color: #fff; }
        .btn-secondary:hover { background: #4b5563; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; margin-bottom: 6px; color: #9ca3af; font-size: 13px; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px 12px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; color: #fff; font-size: 14px; }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: #10b981; }
        .form-group small { color: #6b7280; font-size: 11px; margin-top: 4px; display: block; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .logs { max-height: 350px; overflow-y: auto; background: rgba(0,0,0,0.2); border-radius: 8px; padding: 10px; }
        .log-entry { padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; gap: 10px; font-size: 12px; }
        .log-entry:last-child { border-bottom: none; }
        .log-time { color: #6b7280; min-width: 55px; }
        .log-sender { color: #10b981; min-width: 80px; font-weight: 500; }
        .log-message { color: #e5e7eb; flex: 1; word-break: break-word; }
        .log-incoming { border-left: 3px solid #3b82f6; }
        .log-outgoing { border-left: 3px solid #10b981; }
        .log-system { border-left: 3px solid #6b7280; }
        .log-error { border-left: 3px solid #ef4444; }
        .log-success { border-left: 3px solid #10b981; }
        .log-lead { border-left: 3px solid #f59e0b; background: rgba(245, 158, 11, 0.05); }
        .log-order { border-left: 3px solid #8b5cf6; background: rgba(139, 92, 246, 0.05); }
        .log-courier { border-left: 3px solid #06b6d4; background: rgba(6, 182, 212, 0.05); }
        .info-box { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #93c5fd; }
        .warning-box { background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #fcd34d; }
        .auth-modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center; }
        .auth-modal.show { display: flex; }
        .auth-box { background: #1a1a2e; border-radius: 16px; padding: 30px; max-width: 400px; width: 90%; text-align: center; }
        .auth-box h2 { color: #10b981; margin-bottom: 20px; }
        .auth-box input { width: 100%; padding: 14px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; color: #fff; font-size: 16px; margin-bottom: 15px; text-align: center; }
        .auth-box input:focus { outline: none; border-color: #10b981; }
        .auth-box .btn { width: 100%; margin: 0; }
        .lead-card { background: rgba(0,0,0,0.2); border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 4px solid #f59e0b; }
        .lead-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .lead-client { font-weight: 600; color: #f59e0b; }
        .lead-type { font-size: 11px; padding: 2px 8px; background: rgba(245,158,11,0.2); border-radius: 4px; }
        .lead-summary { color: #9ca3af; font-size: 12px; margin-bottom: 6px; }
        .lead-meta { display: flex; gap: 15px; font-size: 11px; color: #6b7280; }
        .order-card { background: rgba(0,0,0,0.2); border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 4px solid #8b5cf6; }
        .order-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .order-client { font-weight: 600; color: #8b5cf6; }
        .order-status { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
        .order-status.paid { background: rgba(16, 185, 129, 0.2); color: #10b981; }
        .order-status.pending { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .order-details { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 12px; color: #9ca3af; }
        .order-detail { display: flex; gap: 4px; }
        .order-detail span:first-child { color: #6b7280; }
        .section-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #10b981; display: flex; align-items: center; gap: 8px; }
        .divider { height: 1px; background: rgba(255,255,255,0.1); margin: 20px 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); border-radius: 3px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 3px; }
    </style>
</head>
<body>
    <!-- Auth Modal -->
    <div id="authModal" class="auth-modal">
        <div class="auth-box">
            <h2 id="authTitle">📱 Введите номер телефона</h2>
            <input type="text" id="authInput" placeholder="+998901234567">
            <button class="btn btn-primary" onclick="submitAuth()">Продолжить</button>
            <p id="authError" style="color:#ef4444;margin-top:15px;font-size:12px;"></p>
        </div>
    </div>

    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🥷 Ninja Userbot</h1>
            <span id="statusBadge" class="status-badge status-offline">Оффлайн</span>
        </div>

        <!-- Stats -->
        <div class="stats">
            <div class="stat-card">
                <div class="value" id="statMessages">0</div>
                <div class="label">Сообщений</div>
            </div>
            <div class="stat-card highlight">
                <div class="value" id="statLeads">0</div>
                <div class="label">Лидов</div>
            </div>
            <div class="stat-card">
                <div class="value" id="statOrders">0</div>
                <div class="label">Заказов</div>
            </div>
            <div class="stat-card">
                <div class="value" id="statUsername">-</div>
                <div class="label">Аккаунт</div>
            </div>
            <div class="stat-card">
                <div class="value" id="statModel">-</div>
                <div class="label">Модель</div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="tabs">
            <button class="tab active" onclick="showPanel('control')">🎮 Управление</button>
            <button class="tab" onclick="showPanel('config')">⚙️ Настройки</button>
            <button class="tab" onclick="showPanel('logs')">📋 Логи</button>
            <button class="tab" onclick="showPanel('leads')">🎯 Лиды</button>
            <button class="tab" onclick="showPanel('orders')">📦 Заказы</button>
        </div>

        <!-- Control Panel -->
        <div id="panel-control" class="panel active">
            <div class="info-box">
                💡 <strong>OpenAI-compatible API</strong> - работает с любым провайдером: Ollama Cloud, Together AI, Groq, Mistral, OpenAI и др.
            </div>
            
            <div style="margin-bottom: 20px;">
                <button id="btnStart" class="btn btn-primary" onclick="startBot()">▶️ Запустить</button>
                <button id="btnStop" class="btn btn-danger" onclick="stopBot()" disabled>⏹️ Остановить</button>
                <button class="btn btn-secondary" onclick="refreshStatus()">🔄 Обновить</button>
            </div>

            <div class="divider"></div>

            <div class="section-title">📝 Быстрые настройки API</div>
            <div class="form-row">
                <div class="form-group">
                    <label>API Base URL</label>
                    <input type="text" id="quickBaseUrl" placeholder="https://api.openai.com/v1">
                    <small>Например: https://api.ollama.ai/v1</small>
                </div>
                <div class="form-group">
                    <label>Model</label>
                    <input type="text" id="quickModel" placeholder="gpt-4o-mini">
                </div>
            </div>
            <div class="form-group">
                <label>API Key (опционально)</label>
                <input type="password" id="quickApiKey" placeholder="sk-...">
            </div>
            <button class="btn btn-primary" onclick="saveQuickConfig()">💾 Сохранить</button>

            <div class="divider"></div>

            <div class="section-title">🚚 Курьеры</div>
            <div class="form-group">
                <label>Юзернеймы курьеров (через запятую)</label>
                <input type="text" id="couriersInput" placeholder="@courier1, @courier2">
                <small>Сообщения от курьеров обрабатываются отдельно</small>
            </div>
            <button class="btn btn-primary" onclick="saveCouriers()">💾 Сохранить</button>
        </div>

        <!-- Config Panel -->
        <div id="panel-config" class="panel">
            <div class="section-title">🔑 Telegram API</div>
            <div class="form-row">
                <div class="form-group">
                    <label>API ID</label>
                    <input type="text" id="apiId" placeholder="12345678">
                    <small>Получите на my.telegram.org</small>
                </div>
                <div class="form-group">
                    <label>API Hash</label>
                    <input type="password" id="apiHash" placeholder="abc123...">
                </div>
            </div>

            <div class="divider"></div>

            <div class="section-title">🤖 AI Model</div>
            <div class="form-group">
                <label>API Base URL</label>
                <input type="text" id="apiBaseUrl" placeholder="https://api.openai.com/v1">
            </div>
            <div class="form-group">
                <label>API Key</label>
                <input type="password" id="apiKey" placeholder="sk-...">
            </div>
            <div class="form-group">
                <label>Model</label>
                <input type="text" id="modelName" placeholder="gpt-4o-mini">
            </div>

            <div class="divider"></div>

            <div class="section-title">🖼 Vision API (Mistral/Pixtral)</div>
            <div class="form-row">
                <div class="form-group">
                    <label>Mistral API Key</label>
                    <input type="password" id="mistralKey" placeholder="...">
                    <small>Для обработки изображений</small>
                </div>
                <div class="form-group">
                    <label>Vision Model</label>
                    <input type="text" id="mistralModel" value="pixtral-12b-2409">
                </div>
            </div>

            <div class="divider"></div>

            <div class="section-title">🎭 System Prompt</div>
            <div class="form-group">
                <label>Промпт для AI</label>
                <textarea id="systemPrompt" rows="10" style="font-family: monospace; font-size: 12px;"></textarea>
            </div>

            <button class="btn btn-primary" onclick="saveFullConfig()">💾 Сохранить настройки</button>
        </div>

        <!-- Logs Panel -->
        <div id="panel-logs" class="panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div class="section-title" style="margin: 0;">📋 Логи сообщений</div>
                <button class="btn btn-secondary" onclick="clearLogs()">🗑 Очистить</button>
            </div>
            <div class="logs" id="logsContainer">
                <div style="text-align: center; color: #6b7280; padding: 20px;">Загрузка...</div>
            </div>
        </div>

        <!-- Leads Panel -->
        <div id="panel-leads" class="panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div class="section-title" style="margin: 0;">🎯 Лиды</div>
                <button class="btn btn-secondary" onclick="clearLeads()">🗑 Очистить</button>
            </div>
            <div id="leadsContainer">
                <div style="text-align: center; color: #6b7280; padding: 20px;">Загрузка...</div>
            </div>
        </div>

        <!-- Orders Panel -->
        <div id="panel-orders" class="panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div class="section-title" style="margin: 0;">📦 Активные заказы</div>
                <button class="btn btn-secondary" onclick="refreshOrders()">🔄 Обновить</button>
            </div>
            <div id="ordersContainer">
                <div style="text-align: center; color: #6b7280; padding: 20px;">Загрузка...</div>
            </div>
        </div>
    </div>

    <script>
        let authStep = 'phone';
        let refreshInterval;

        async function refreshStatus() {
            try {
                const r = await fetch('/api/status');
                const d = await r.json();
                
                document.getElementById('statMessages').textContent = d.message_count;
                document.getElementById('statLeads').textContent = d.lead_count;
                document.getElementById('statOrders').textContent = d.active_orders || 0;
                
                const badge = document.getElementById('statusBadge');
                if (d.running) {
                    badge.textContent = '🟢 ' + (d.username || 'Онлайн');
                    badge.className = 'status-badge status-online';
                    document.getElementById('btnStart').disabled = true;
                    document.getElementById('btnStop').disabled = false;
                    document.getElementById('statUsername').textContent = d.username || '-';
                } else {
                    badge.textContent = '🔴 Оффлайн';
                    badge.className = 'status-badge status-offline';
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStop').disabled = true;
                }
            } catch (e) {
                console.error('Status error:', e);
            }
        }

        async function loadConfig() {
            try {
                const r = await fetch('/api/config');
                const d = await r.json();
                
                document.getElementById('apiId').value = d.api_id || '';
                document.getElementById('apiHash').value = d.api_hash || '';
                document.getElementById('apiBaseUrl').value = d.api_base_url || '';
                document.getElementById('apiKey').value = d.api_key || '';
                document.getElementById('modelName').value = d.model || '';
                document.getElementById('mistralKey').value = d.mistral_key || '';
                document.getElementById('mistralModel').value = d.mistral_model || 'pixtral-12b-2409';
                document.getElementById('systemPrompt').value = d.system_prompt || '';
                document.getElementById('couriersInput').value = d.couriers || '';
                
                document.getElementById('quickBaseUrl').value = d.api_base_url || '';
                document.getElementById('quickModel').value = d.model || '';
                document.getElementById('quickApiKey').value = d.api_key || '';
                
                document.getElementById('statModel').textContent = d.model ? d.model.substring(0, 10) : '-';
            } catch (e) {
                console.error('Config error:', e);
            }
        }

        async function startBot() {
            const btn = document.getElementById('btnStart');
            btn.disabled = true;
            btn.textContent = '⏳ Запуск...';
            
            try {
                await fetch('/api/start', { method: 'POST' });
                setTimeout(checkAuth, 1000);
            } catch (e) {
                console.error('Start error:', e);
                btn.disabled = false;
                btn.textContent = '▶️ Запустить';
            }
        }

        async function stopBot() {
            try {
                await fetch('/api/stop', { method: 'POST' });
                refreshStatus();
            } catch (e) {
                console.error('Stop error:', e);
            }
        }

        async function checkAuth() {
            try {
                const r = await fetch('/api/auth/status');
                const d = await r.json();
                
                if (d.step === 'phone' || d.step === 'code') {
                    showAuthModal(d.step, d.error);
                } else if (d.step === 'done') {
                    hideAuthModal();
                    refreshStatus();
                } else {
                    setTimeout(checkAuth, 2000);
                }
            } catch (e) {
                setTimeout(checkAuth, 2000);
            }
        }

        function showAuthModal(step, error) {
            authStep = step;
            const modal = document.getElementById('authModal');
            const title = document.getElementById('authTitle');
            const input = document.getElementById('authInput');
            const errorEl = document.getElementById('authError');
            
            modal.classList.add('show');
            errorEl.textContent = error || '';
            
            if (step === 'phone') {
                title.textContent = '📱 Введите номер телефона';
                input.placeholder = '+998901234567';
                input.type = 'text';
            } else {
                title.textContent = '🔑 Введите код из Telegram';
                input.placeholder = '12345';
                input.type = 'text';
            }
            input.value = '';
        }

        function hideAuthModal() {
            document.getElementById('authModal').classList.remove('show');
        }

        async function submitAuth() {
            const input = document.getElementById('authInput').value.trim();
            const errorEl = document.getElementById('authError');
            
            if (!input) {
                errorEl.textContent = 'Введите значение';
                return;
            }
            
            try {
                const endpoint = authStep === 'phone' ? '/api/auth/phone' : '/api/auth/code';
                const body = authStep === 'phone' ? { phone: input } : { code: input };
                
                const r = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                
                const d = await r.json();
                
                if (d.success) {
                    if (authStep === 'phone') {
                        showAuthModal('code', '');
                    } else {
                        hideAuthModal();
                        refreshStatus();
                    }
                } else {
                    errorEl.textContent = d.error || 'Ошибка';
                }
            } catch (e) {
                errorEl.textContent = 'Ошибка соединения';
            }
        }

        async function saveQuickConfig() {
            const config = {
                api_base_url: document.getElementById('quickBaseUrl').value,
                model: document.getElementById('quickModel').value,
                api_key: document.getElementById('quickApiKey').value
            };
            
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                alert('✅ Сохранено!');
                loadConfig();
            } catch (e) {
                alert('❌ Ошибка');
            }
        }

        async function saveCouriers() {
            const config = {
                couriers: document.getElementById('couriersInput').value
            };
            
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                alert('✅ Курьеры сохранены!');
            } catch (e) {
                alert('❌ Ошибка');
            }
        }

        async function saveFullConfig() {
            const config = {
                api_id: document.getElementById('apiId').value,
                api_hash: document.getElementById('apiHash').value,
                api_base_url: document.getElementById('apiBaseUrl').value,
                api_key: document.getElementById('apiKey').value,
                model: document.getElementById('modelName').value,
                mistral_key: document.getElementById('mistralKey').value,
                mistral_model: document.getElementById('mistralModel').value,
                system_prompt: document.getElementById('systemPrompt').value,
                couriers: document.getElementById('couriersInput').value
            };
            
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                alert('✅ Настройки сохранены!');
                loadConfig();
            } catch (e) {
                alert('❌ Ошибка');
            }
        }

        async function loadLogs() {
            try {
                const r = await fetch('/api/logs');
                const logs = await r.json();
                
                const container = document.getElementById('logsContainer');
                if (logs.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 20px;">Нет логов</div>';
                    return;
                }
                
                container.innerHTML = logs.reverse().map(log => {
                    let dirClass = 'log-system';
                    if (log.direction === 'incoming') dirClass = 'log-incoming';
                    else if (log.direction === 'outgoing') dirClass = 'log-outgoing';
                    else if (log.direction === 'error') dirClass = 'log-error';
                    else if (log.direction === 'success') dirClass = 'log-success';
                    else if (log.direction === 'lead') dirClass = 'log-lead';
                    else if (log.direction === 'order') dirClass = 'log-order';
                    else if (log.direction === 'courier') dirClass = 'log-courier';
                    
                    return `<div class="log-entry ${dirClass}">
                        <span class="log-time">${log.timestamp}</span>
                        <span class="log-sender">${log.sender}</span>
                        <span class="log-message">${log.message}</span>
                    </div>`;
                }).join('');
            } catch (e) {
                console.error('Logs error:', e);
            }
        }

        async function clearLogs() {
            await fetch('/api/logs', { method: 'DELETE' });
            loadLogs();
        }

        async function loadLeads() {
            try {
                const r = await fetch('/api/leads');
                const leads = await r.json();
                
                const container = document.getElementById('leadsContainer');
                if (leads.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 20px;">Нет лидов</div>';
                    return;
                }
                
                container.innerHTML = leads.reverse().map(lead => {
                    return `<div class="lead-card">
                        <div class="lead-header">
                            <span class="lead-client">👤 ${lead.client_name}</span>
                            <span class="lead-type">${lead.lead_type}</span>
                        </div>
                        <div class="lead-summary">${lead.summary}</div>
                        <div class="lead-meta">
                            <span class="urgency-${lead.urgency}">⚡ ${lead.urgency}</span>
                            <span>📊 ${Math.round(lead.confidence * 100)}%</span>
                            <span>🕐 ${lead.timestamp}</span>
                            <span>📱 ${lead.chat_id}</span>
                        </div>
                    </div>`;
                }).join('');
            } catch (e) {
                console.error('Leads error:', e);
            }
        }

        async function clearLeads() {
            await fetch('/api/leads', { method: 'DELETE' });
            loadLeads();
        }

        async function loadOrders() {
            try {
                const r = await fetch('/api/orders');
                const orders = await r.json();
                
                const container = document.getElementById('ordersContainer');
                const orderList = Object.entries(orders);
                
                if (orderList.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: #6b7280; padding: 20px;">Нет активных заказов</div>';
                    return;
                }
                
                container.innerHTML = orderList.map(([chatId, order]) => {
                    const statusClass = order.payment_confirmed ? 'paid' : 'pending';
                    const statusText = order.payment_confirmed ? '✅ Оплачен' : '⏳ Ожидает';
                    
                    return `<div class="order-card">
                        <div class="order-header">
                            <span class="order-client">👤 ${order.client_name}</span>
                            <span class="order-status ${statusClass}">${statusText}</span>
                        </div>
                        <div class="order-details">
                            <div class="order-detail"><span>📱</span> <span>${order.phone || '-'}</span></div>
                            <div class="order-detail"><span>🔥</span> <span>${order.calories || '-'}</span></div>
                            <div class="order-detail"><span>📅</span> <span>${order.days || '-'} дней</span></div>
                            <div class="order-detail"><span>🚚</span> <span>${order.delivery_date || '-'}</span></div>
                            <div class="order-detail"><span>📍</span> <span>${(order.address || '-').substring(0, 30)}</span></div>
                            <div class="order-detail"><span>💰</span> <span>${order.total_price ? order.total_price.toLocaleString() + ' сум' : '-'}</span></div>
                        </div>
                        ${!order.payment_confirmed ? `<button class="btn btn-primary" style="margin-top:10px;padding:8px 16px;font-size:12px;" onclick="confirmOrder(${chatId})">✅ Подтвердить оплату</button>` : ''}
                    </div>`;
                }).join('');
            } catch (e) {
                console.error('Orders error:', e);
            }
        }

        async function refreshOrders() {
            loadOrders();
        }

        async function confirmOrder(chatId) {
            try {
                await fetch(`/api/orders/${chatId}/confirm`, { method: 'POST' });
                loadOrders();
                alert('✅ Оплата подтверждена! Заказ отправлен в Saved Messages');
            } catch (e) {
                alert('❌ Ошибка');
            }
        }

        function showPanel(name) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('panel-' + name).classList.add('active');
            event.target.classList.add('active');
            
            if (name === 'logs') loadLogs();
            if (name === 'leads') loadLeads();
            if (name === 'orders') loadOrders();
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadConfig();
            refreshStatus();
            refreshInterval = setInterval(refreshStatus, 5000);
        });

        // Handle Enter in auth modal
        document.getElementById('authInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') submitAuth();
        });
    </script>
</body>
</html>
'''

@app.get("/", response_class=HTMLResponse)
async def get_web_ui():
    return WEB_UI_HTML

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3030)
