"""
Ninja Userbot - Telegram Auto-Reply with AI
Runs as YOUR Telegram account (Userbot, not Bot)
Supports images via Mistral Vision API (Pixtral)
Universal OpenAI-compatible API for text generation
Lead tracking to Saved Messages
Web UI Authentication
"""

import asyncio
import json
import os
import sys
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User
from telethon.tl.types import MessageMediaPhoto

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", Path.home() / ".ninja-data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
LEADS_FILE = DATA_DIR / "leads.json"
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

КАЛОРИИ И ЦЕНЫ (с 1 мая 2026):
- 1000–1200 ккал — 94 000 сум
- 1400–1600 ккал — 112 000 сум
- 1800–2000 ккал — 126 000 сум
- 2200–2500 ккал — 140 000 сум
- 3000–3200 ккал — 170 000 сум

ДОСТАВКА:
- Время: 17:00–22:00 по маршруту
- 5 махаллинских овкат в порциях
- Курьер звонит по прибытии
- Яндекс такси - за счёт клиента

ЗАКАЗ:
- До 21:00 за день до доставки
- Отмена до 21:00 за день до доставки
- Минимум 3 дня для первого заказа
- Предоплата

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
""" + COMPANY_INFO

DEFAULT_LEAD_PROMPT = """Ты анализируешь переписку с клиентом и определяешь, является ли это успешным лидом.

УСПЕШНЫЙ ЛИД - клиент который:
✅ Готов сделать заказ (назначил калории, выбрал пакет)
✅ Запросил расчёт калорий и дал свои данные
✅ Дал адрес доставки и контакты
✅ Оплатил или готов оплатить
✅ Спросил про оплату/карты

НЕ ЛИД:
❌ Просто спрашивает цены "на будущее"
❌ Жалуется или возмущается
❌ Нужна просто консультация без намерения купить
❌ Спам или реклама

Проанализируй переписку и ответь ТОЛЬКО в формате JSON:
{
  "is_lead": true/false,
  "confidence": 0.0-1.0,
  "lead_type": "new_client/repeat_client/consultation/payment_confirmed",
  "client_name": "имя клиента",
  "summary": "краткое описание что нужно сделать",
  "urgency": "high/medium/low"
}

Если не лид - верни is_lead: false и остальные поля пустыми.
"""

# Global state
HISTORY_LIMIT = 20
conversation_history: dict[int, list[dict]] = {}
message_logs: list = []
leads_log: list = []

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

def add_log(message: str, sender: str = "System", direction: str = "system", has_image: bool = False):
    display_msg = message[:200] if len(message) > 200 else message
    if has_image:
        display_msg = "[IMAGE] " + display_msg
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "sender": sender,
        "message": display_msg,
        "direction": direction,
        "has_image": has_image
    }
    message_logs.append(entry)
    save_logs()
    print(f"[{direction}] {sender}: {display_msg}")

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
                try:
                    os.remove(file_path)
                except:
                    pass
                return data_url
        return None
    except Exception as e:
        print(f"Error downloading image: {e}")
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
                {"type": "text", "text": "Опиши это изображение подробно на русском языке. Что на нём видно?"},
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
    time_context = f"\n\n[ТЕКУЩЕЕ ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')} ({now.strftime('%A')})]"
    
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
        import re
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"is_lead": False}
    except Exception as e:
        print(f"Lead analysis error: {e}")
        return {"is_lead": False}

def add_to_history(chat_id: int, role: str, content: Union[str, list]) -> None:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    conversation_history[chat_id].append({"role": role, "content": content})
    if len(conversation_history[chat_id]) > HISTORY_LIMIT:
        conversation_history[chat_id] = conversation_history[chat_id][-HISTORY_LIMIT:]

def get_conversation_messages(chat_id: int, system_prompt: str) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    if chat_id in conversation_history:
        messages.extend(conversation_history[chat_id])
    return messages

# ---------------------------------------------------------------------------
# Telegram Bot Logic
# ---------------------------------------------------------------------------
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
    global client, config, message_count, lead_count
    sender_name = sender.first_name or sender.last_name or str(sender.id)
    text = (message.text or "").strip()
    has_image = False
    image_url = None

    if message.media:
        image_url = await download_and_encode_image(message)
        if image_url:
            has_image = True

    if not text and not has_image:
        return

    add_log(text if text else "(изображение)", sender_name, "incoming", has_image)

    if has_image:
        content = []
        if text:
            content.append({"type": "text", "text": text})
        content.append({"type": "image_url", "image_url": {"url": image_url}})
        add_to_history(chat_id, "user", content)
    else:
        add_to_history(chat_id, "user", text)

    try:
        async with client.action(chat_id, "typing"):
            add_log("Думаю...", "System", "system")
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

class PhoneModel(BaseModel):
    phone: str

class CodeModel(BaseModel):
    code: str

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global message_logs, leads_log, config
    message_logs = load_logs()
    leads_log = load_leads()
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
        "lead_count": lead_count
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
        .container { max-width: 900px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; padding: 15px 20px; background: rgba(255,255,255,0.05); border-radius: 12px; margin-bottom: 20px; }
        .header h1 { display: flex; align-items: center; gap: 10px; font-size: 22px; }
        .status-badge { padding: 6px 14px; border-radius: 16px; font-weight: 600; font-size: 13px; }
        .status-online { background: #10b981; }
        .status-offline { background: #6b7280; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
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
        .urgency-high { color: #ef4444; }
        .urgency-medium { color: #f59e0b; }
        .urgency-low { color: #10b981; }
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
                    <small>Например: llama3.2, gpt-4o-mini</small>
                </div>
            </div>
            <div class="form-group">
                <label>API Key</label>
                <input type="password" id="quickApiKey" placeholder="sk-...">
            </div>
            <button class="btn btn-primary" onclick="saveQuickConfig()">💾 Сохранить</button>
        </div>

        <!-- Config Panel -->
        <div id="panel-config" class="panel">
            <div class="warning-box">
                ⚠️ <strong>Pixtral (Mistral)</strong> используется для описания изображений. Без него картинки не будут анализироваться.
            </div>

            <div class="section-title">🖼️ Vision API (для изображений)</div>
            <div class="form-row">
                <div class="form-group">
                    <label>Mistral API Key (Pixtral)</label>
                    <input type="password" id="mistralKey" placeholder="Для обработки изображений">
                </div>
                <div class="form-group">
                    <label>Pixtral Model</label>
                    <input type="text" id="mistralModel" value="pixtral-12b-2409">
                </div>
            </div>

            <div class="divider"></div>

            <div class="section-title">🤖 Text API (OpenAI-compatible)</div>
            <div class="form-group">
                <label>API Base URL</label>
                <input type="text" id="apiBaseUrl" placeholder="https://api.openai.com/v1">
                <small>Любой OpenAI-совместимый endpoint</small>
            </div>
            <div class="form-group">
                <label>API Key</label>
                <input type="password" id="apiKey" placeholder="Ваш API ключ">
            </div>
            <div class="form-group">
                <label>Model Name</label>
                <input type="text" id="modelName" placeholder="gpt-4o-mini, llama3.2, mistral-large-latest...">
            </div>

            <div class="divider"></div>

            <div class="section-title">📱 Telegram API</div>
            <div class="form-row">
                <div class="form-group">
                    <label>API ID</label>
                    <input type="text" id="apiId">
                </div>
                <div class="form-group">
                    <label>API Hash</label>
                    <input type="text" id="apiHash">
                </div>
            </div>

            <div class="divider"></div>

            <div class="section-title">🎭 System Prompt</div>
            <div class="form-group">
                <label>Промпт для AI (персонаж и стиль)</label>
                <textarea id="systemPrompt" rows="10" style="font-family: monospace; font-size: 12px;"></textarea>
            </div>

            <div style="margin-top: 20px;">
                <button class="btn btn-primary" onclick="saveConfig()">💾 Сохранить настройки</button>
            </div>
        </div>

        <!-- Logs Panel -->
        <div id="panel-logs" class="panel">
            <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
                <h3>📋 Логи сообщений</h3>
                <div>
                    <button class="btn btn-secondary" onclick="refreshLogs()">🔄 Обновить</button>
                    <button class="btn btn-danger" onclick="clearLogs()">🗑️ Очистить</button>
                </div>
            </div>
            <div id="logsContainer" class="logs"></div>
        </div>

        <!-- Leads Panel -->
        <div id="panel-leads" class="panel">
            <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
                <h3>🎯 Найденные лиды</h3>
                <div>
                    <button class="btn btn-secondary" onclick="refreshLeads()">🔄 Обновить</button>
                    <button class="btn btn-danger" onclick="clearLeads()">🗑️ Очистить</button>
                </div>
            </div>
            <div id="leadsContainer"></div>
        </div>
    </div>

    <script>
        let authStep = 'idle';

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadConfig();
            refreshStatus();
        });

        function showPanel(name) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById('panel-' + name).classList.add('active');
            event.target.classList.add('active');
            
            if (name === 'logs') refreshLogs();
            if (name === 'leads') refreshLeads();
        }

        async function loadConfig() {
            try {
                const r = await fetch('/api/config');
                const data = await r.json();
                
                // Vision API
                document.getElementById('mistralKey').value = data.mistral_key || '';
                document.getElementById('mistralModel').value = data.mistral_model || 'pixtral-12b-2409';
                
                // Text API
                document.getElementById('apiBaseUrl').value = data.api_base_url || '';
                document.getElementById('apiKey').value = data.api_key || '';
                document.getElementById('modelName').value = data.model || '';
                
                // Quick settings
                document.getElementById('quickBaseUrl').value = data.api_base_url || '';
                document.getElementById('quickApiKey').value = data.api_key || '';
                document.getElementById('quickModel').value = data.model || '';
                
                // Telegram
                document.getElementById('apiId').value = data.api_id || '';
                document.getElementById('apiHash').value = data.api_hash || '';
                
                // Prompts
                document.getElementById('systemPrompt').value = data.system_prompt || '';
            } catch (e) {
                console.error('Load config error:', e);
            }
        }

        async function saveConfig() {
            const config = {
                mistral_key: document.getElementById('mistralKey').value,
                mistral_model: document.getElementById('mistralModel').value,
                api_base_url: document.getElementById('apiBaseUrl').value,
                api_key: document.getElementById('apiKey').value,
                model: document.getElementById('modelName').value,
                api_id: document.getElementById('apiId').value,
                api_hash: document.getElementById('apiHash').value,
                system_prompt: document.getElementById('systemPrompt').value
            };
            
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                alert('✅ Настройки сохранены!');
            } catch (e) {
                alert('❌ Ошибка сохранения: ' + e.message);
            }
        }

        async function saveQuickConfig() {
            const config = {
                api_base_url: document.getElementById('quickBaseUrl').value,
                api_key: document.getElementById('quickApiKey').value,
                model: document.getElementById('quickModel').value
            };
            
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                
                // Sync with main config fields
                document.getElementById('apiBaseUrl').value = config.api_base_url;
                document.getElementById('apiKey').value = config.api_key;
                document.getElementById('modelName').value = config.model;
                
                alert('✅ Быстрые настройки сохранены!');
                refreshStatus();
            } catch (e) {
                alert('❌ Ошибка: ' + e.message);
            }
        }

        async function refreshStatus() {
            try {
                const r = await fetch('/api/status');
                const data = await r.json();
                
                const badge = document.getElementById('statusBadge');
                badge.textContent = data.running ? 'Онлайн' : 'Оффлайн';
                badge.className = 'status-badge ' + (data.running ? 'status-online' : 'status-offline');
                
                document.getElementById('statMessages').textContent = data.message_count;
                document.getElementById('statLeads').textContent = data.lead_count;
                document.getElementById('statUsername').textContent = data.username || '-';
                
                document.getElementById('btnStart').disabled = data.running;
                document.getElementById('btnStop').disabled = !data.running;
                
                // Check auth status
                const ar = await fetch('/api/auth/status');
                const auth = await ar.json();
                authStep = auth.step;
                
                if (auth.step === 'phone' || auth.step === 'code') {
                    showAuthModal();
                }
            } catch (e) {
                console.error('Status error:', e);
            }
            
            // Load model name for stats
            try {
                const cr = await fetch('/api/config');
                const cfg = await cr.json();
                document.getElementById('statModel').textContent = cfg.model ? cfg.model.substring(0, 12) : '-';
            } catch (e) {}
        }

        async function startBot() {
            try {
                await fetch('/api/start', { method: 'POST' });
                setTimeout(refreshStatus, 1000);
            } catch (e) {
                alert('Ошибка запуска: ' + e.message);
            }
        }

        async function stopBot() {
            try {
                await fetch('/api/stop', { method: 'POST' });
                setTimeout(refreshStatus, 500);
            } catch (e) {
                alert('Ошибка остановки: ' + e.message);
            }
        }

        async function refreshLogs() {
            try {
                const r = await fetch('/api/logs');
                const logs = await r.json();
                const container = document.getElementById('logsContainer');
                
                if (logs.length === 0) {
                    container.innerHTML = '<p style="color: #6b7280; text-align: center; padding: 20px;">Нет логов</p>';
                    return;
                }
                
                container.innerHTML = logs.reverse().map(log => {
                    let dirClass = 'log-system';
                    if (log.direction === 'incoming') dirClass = 'log-incoming';
                    else if (log.direction === 'outgoing') dirClass = 'log-outgoing';
                    else if (log.direction === 'error') dirClass = 'log-error';
                    else if (log.direction === 'success') dirClass = 'log-success';
                    else if (log.direction === 'lead') dirClass = 'log-lead';
                    
                    const imageBadge = log.has_image ? '<span class="log-image">📷</span> ' : '';
                    
                    return `<div class="log-entry ${dirClass}">
                        <span class="log-time">${log.timestamp}</span>
                        <span class="log-sender">${log.sender}</span>
                        <span class="log-message">${imageBadge}${escapeHtml(log.message)}</span>
                    </div>`;
                }).join('');
            } catch (e) {
                console.error('Logs error:', e);
            }
        }

        async function clearLogs() {
            if (!confirm('Очистить все логи?')) return;
            await fetch('/api/logs', { method: 'DELETE' });
            refreshLogs();
        }

        async function refreshLeads() {
            try {
                const r = await fetch('/api/leads');
                const leads = await r.json();
                const container = document.getElementById('leadsContainer');
                
                if (leads.length === 0) {
                    container.innerHTML = '<p style="color: #6b7280; text-align: center; padding: 20px;">Нет лидов</p>';
                    return;
                }
                
                container.innerHTML = leads.reverse().map(lead => {
                    const urgencyClass = 'urgency-' + (lead.urgency || 'medium');
                    return `<div class="lead-card">
                        <div class="lead-header">
                            <span class="lead-client">${escapeHtml(lead.client_name || 'Неизвестно')}</span>
                            <span class="lead-type">${lead.lead_type || 'new_client'}</span>
                        </div>
                        <div class="lead-summary">${escapeHtml(lead.summary || '')}</div>
                        <div class="lead-meta">
                            <span class="${urgencyClass}">⚡ ${lead.urgency || 'medium'}</span>
                            <span>📊 ${(lead.confidence || 0) * 100}%</span>
                            <span>🕐 ${lead.timestamp || ''}</span>
                        </div>
                    </div>`;
                }).join('');
            } catch (e) {
                console.error('Leads error:', e);
            }
        }

        async function clearLeads() {
            if (!confirm('Очистить все лиды?')) return;
            await fetch('/api/leads', { method: 'DELETE' });
            refreshLeads();
        }

        function showAuthModal() {
            const modal = document.getElementById('authModal');
            const title = document.getElementById('authTitle');
            const input = document.getElementById('authInput');
            const error = document.getElementById('authError');
            
            modal.classList.add('show');
            error.textContent = '';
            
            if (authStep === 'phone') {
                title.textContent = '📱 Введите номер телефона';
                input.placeholder = '+998901234567';
                input.type = 'tel';
            } else if (authStep === 'code') {
                title.textContent = '🔑 Введите код из Telegram';
                input.placeholder = '12345';
                input.type = 'text';
            }
            input.value = '';
            input.focus();
        }

        async function submitAuth() {
            const input = document.getElementById('authInput');
            const error = document.getElementById('authError');
            const value = input.value.trim();
            
            if (!value) {
                error.textContent = 'Введите значение';
                return;
            }
            
            try {
                if (authStep === 'phone') {
                    const r = await fetch('/api/auth/phone', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ phone: value })
                    });
                    const data = await r.json();
                    
                    if (data.success) {
                        authStep = 'code';
                        showAuthModal();
                    } else {
                        error.textContent = data.error || 'Ошибка';
                    }
                } else if (authStep === 'code') {
                    const r = await fetch('/api/auth/code', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ code: value })
                    });
                    const data = await r.json();
                    
                    if (data.success) {
                        document.getElementById('authModal').classList.remove('show');
                        authStep = 'done';
                        refreshStatus();
                    } else {
                        error.textContent = data.error || 'Неверный код';
                    }
                }
            } catch (e) {
                error.textContent = 'Ошибка: ' + e.message;
            }
        }

        // Handle Enter key in auth modal
        document.getElementById('authInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') submitAuth();
        });

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
'''

@app.get("/", response_class=HTMLResponse)
async def root():
    return WEB_UI_HTML

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3030)
