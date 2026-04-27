"""
Ninja Userbot - Telegram Auto-Reply with Mistral AI
Runs as YOUR Telegram account (Userbot, not Bot)
Supports images via Mistral Vision API
Lead tracking to Saved Messages
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
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User, Photo, Document
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
    "mistral_key": "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v",
    "mistral_model": "pixtral-12b-2409",  # Vision model for images
    "text_model": "mistral-medium-latest",  # Text-only model
    "system_prompt": "",
    "lead_prompt": "",
}

# Default system prompt - realistic employee from Tashkent
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

# Lead detection prompt
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

# Conversation history per chat (supports multimodal content)
HISTORY_LIMIT = 20
conversation_history: dict[int, list[dict]] = {}
message_logs: list = []
leads_log: list = []

# Bot state
bot_instance = None

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ConfigModel(BaseModel):
    api_id: str = ""
    api_hash: str = ""
    mistral_key: str = ""
    mistral_model: str = "pixtral-12b-2409"
    text_model: str = "mistral-medium-latest"
    system_prompt: str = ""
    lead_prompt: str = ""

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config.update(loaded)
        except:
            pass
    
    # Ensure prompts have defaults
    if not config.get("system_prompt"):
        config["system_prompt"] = DEFAULT_SYSTEM_PROMPT
    if not config.get("lead_prompt"):
        config["lead_prompt"] = DEFAULT_LEAD_PROMPT
    
    return config

def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

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
    """Add log entry"""
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
    """Add lead to log"""
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "client_name": client_name,
        "chat_id": chat_id,
        **lead_data
    }
    leads_log.append(entry)
    save_leads()

async def download_and_encode_image(client, message) -> Optional[str]:
    """Download image from message and return base64 encoded data URL"""
    try:
        if not message.media:
            return None
        
        # Handle photo
        if isinstance(message.media, MessageMediaPhoto):
            photo = message.media.photo
            if photo:
                # Download the photo
                file_path = await client.download_media(photo, IMAGES_DIR)
                
                # Read and encode
                with open(file_path, "rb") as f:
                    image_data = f.read()
                
                # Determine mime type
                ext = Path(file_path).suffix.lower()
                mime_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }
                mime_type = mime_types.get(ext, 'image/jpeg')
                
                # Create data URL
                base64_data = base64.b64encode(image_data).decode('utf-8')
                data_url = f"data:{mime_type};base64,{base64_data}"
                
                # Cleanup temp file
                try:
                    os.remove(file_path)
                except:
                    pass
                
                return data_url
        
        return None
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None

async def call_mistral_vision(messages: list[dict], api_key: str, model: str) -> str:
    """Call Mistral AI with vision support for multimodal messages"""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code != 200:
            error_detail = r.text
            raise Exception(f"API Error {r.status_code}: {error_detail}")
        return r.json()["choices"][0]["message"]["content"].strip()

async def analyze_lead(conversation: list[dict], api_key: str, model: str) -> dict:
    """Analyze conversation to detect if it's a successful lead"""
    try:
        messages = [
            {"role": "system", "content": DEFAULT_LEAD_PROMPT},
            {"role": "user", "content": f"Проанализируй переписку:\n\n{json.dumps(conversation, ensure_ascii=False, indent=2)}"}
        ]
        
        result = await call_mistral_vision(messages, api_key, model)
        
        # Parse JSON from response
        # Find JSON in response
        import re
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"is_lead": False}
    except Exception as e:
        print(f"Lead analysis error: {e}")
        return {"is_lead": False}

def add_to_history(chat_id: int, role: str, content: Union[str, list]) -> None:
    """Add message to conversation history (supports text or multimodal content)"""
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    
    conversation_history[chat_id].append({"role": role, "content": content})
    
    # Keep only last N messages
    if len(conversation_history[chat_id]) > HISTORY_LIMIT:
        conversation_history[chat_id] = conversation_history[chat_id][-HISTORY_LIMIT:]

def get_conversation_messages(chat_id: int, system_prompt: str) -> list[dict]:
    """Build messages list with full conversation context"""
    messages = [{"role": "system", "content": system_prompt}]
    
    if chat_id in conversation_history:
        messages.extend(conversation_history[chat_id])
    
    return messages

# ---------------------------------------------------------------------------
# Telegram Userbot
# ---------------------------------------------------------------------------
class TelegramUserbot:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.running = False
        self.config = load_config()
        self.username: Optional[str] = None
        self.message_count = 0
        self.lead_count = 0

    async def send_to_saved_messages(self, lead_data: dict, client_name: str, chat_id: int):
        """Send lead notification to Saved Messages"""
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
            
            # Send to Saved Messages (chat with self)
            me = await self.client.get_me()
            await self.client.send_message(me.id, message)
            add_log(f"Лид сохранён: {client_name}", "System", "lead")
            
        except Exception as e:
            add_log(f"Ошибка сохранения лида: {e}", "System", "error")

    async def handle_message(self, chat_id: int, sender: User, message) -> None:
        """Handle incoming message (text and/or images) and generate AI reply"""
        sender_name = sender.first_name or sender.last_name or str(sender.id)
        
        text = (message.text or "").strip()
        has_image = False
        image_url = None
        
        # Check for image
        if message.media:
            image_url = await download_and_encode_image(self.client, message)
            if image_url:
                has_image = True
        
        # Skip if no text and no image
        if not text and not has_image:
            return
        
        # Log incoming message
        add_log(text if text else "(изображение)", sender_name, "incoming", has_image)
        
        # Build content for history
        if has_image:
            # Multimodal content with image
            content = []
            if text:
                content.append({"type": "text", "text": text})
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
            add_to_history(chat_id, "user", content)
        else:
            # Text only
            add_to_history(chat_id, "user", text)
        
        try:
            # Show typing indicator
            async with self.client.action(chat_id, "typing"):
                add_log("Думаю...", "System", "system")
                
                messages = get_conversation_messages(chat_id, self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
                
                # Use vision model if images present
                model = self.config["mistral_model"] if has_image else self.config.get("text_model", self.config["mistral_model"])
                
                reply = await call_mistral_vision(
                    messages,
                    self.config["mistral_key"],
                    model
                )
        except Exception as e:
            add_log(f"AI Error: {e}", "System", "error")
            return
        
        try:
            # Add AI response to history
            add_to_history(chat_id, "assistant", reply)
            
            # Send the reply
            await self.client.send_message(chat_id, reply)
            self.message_count += 1
            
            # Log outgoing message
            add_log(reply, sender_name, "outgoing")
            
            # Analyze if this is a successful lead (every 3 messages to save API calls)
            msg_count = len(conversation_history.get(chat_id, []))
            if msg_count >= 3 and msg_count % 3 == 0:
                try:
                    # Prepare conversation for analysis (convert multimodal to text for analysis)
                    conv_for_analysis = []
                    for msg in conversation_history.get(chat_id, []):
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            # Extract text from multimodal
                            text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                            conv_for_analysis.append({
                                "role": msg["role"],
                                "content": " ".join(text_parts) + " [изображение]"
                            })
                        else:
                            conv_for_analysis.append(msg)
                    
                    lead_result = await analyze_lead(
                        conv_for_analysis,
                        self.config["mistral_key"],
                        self.config.get("text_model", self.config["mistral_model"])
                    )
                    
                    if lead_result.get("is_lead") and lead_result.get("confidence", 0) >= 0.6:
                        # Save lead
                        add_lead(lead_result, sender_name, chat_id)
                        self.lead_count += 1
                        
                        # Send to Saved Messages
                        await self.send_to_saved_messages(lead_result, sender_name, chat_id)
                        
                except Exception as e:
                    print(f"Lead analysis error: {e}")
                    
        except Exception as e:
            add_log(f"Send Error: {e}", "System", "error")

    async def fetch_chat_history(self, chat_id: int, limit: int = 20) -> list:
        """Fetch last N messages from chat including images"""
        messages = []
        try:
            async for msg in self.client.iter_messages(chat_id, limit=limit):
                msg_data = {
                    "id": msg.id,
                    "text": msg.text or "",
                    "date": msg.date.isoformat() if msg.date else None,
                    "out": msg.out,
                    "has_media": bool(msg.media),
                    "sender_id": msg.sender_id
                }
                messages.append(msg_data)
            return messages
        except Exception as e:
            add_log(f"Error fetching history: {e}", "System", "error")
            return []

    async def run(self):
        """Main userbot loop"""
        try:
            # Validate config
            if not self.config.get("api_id") or not self.config.get("api_hash"):
                add_log("ОШИБКА: Настройте API ID и API Hash в Settings", "System", "error")
                return
            
            if not self.config.get("mistral_key"):
                add_log("ОШИБКА: Настройте Mistral API Key в Settings", "System", "error")
                return
            
            # Create Telegram client
            self.client = TelegramClient(
                str(SESSION_PATH),
                int(self.config["api_id"]),
                self.config["api_hash"]
            )

            @self.client.on(events.NewMessage)
            async def handler(event):
                # Only handle private messages, not from self, not from bots
                if event.message.out or not event.is_private:
                    return
                
                sender = await event.get_sender()
                if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                    return
                
                # Handle message (text and/or images)
                await self.handle_message(event.chat_id, sender, event.message)

            # Start client
            add_log("Подключение к Telegram...", "System", "system")
            await self.client.start()
            
            # Get user info
            me = await self.client.get_me()
            self.username = f"@{me.username}" if me.username else me.first_name
            self.running = True
            add_log(f"✅ Вошел как {self.username}", "System", "success")
            
            # Process unread messages
            add_log("Проверка непрочитанных сообщений...", "System", "system")
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
                        add_log(f"{dialog.unread_count} сообщений от {sender_name}", "System", "system")
                        
                        async for message in self.client.iter_messages(
                            dialog.entity,
                            limit=dialog.unread_count,
                            reverse=True
                        ):
                            if not message.out:
                                # Handle message with possible images
                                await self.handle_message(dialog.id, entity, message)
                                unread_count += 1
                        
                        await self.client.send_read_acknowledge(dialog.entity)
                except Exception as e:
                    add_log(f"Ошибка: {e}", "System", "error")
            
            if unread_count > 0:
                add_log(f"Обработано {unread_count} сообщений", "System", "success")
            
            add_log("🚀 Юзербот работает! Отвечаю как сотрудник Sog'lom taom...", "System", "success")
            
            # Keep running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            add_log(f"Ошибка: {e}", "System", "error")
            self.running = False

    async def start(self):
        """Start the userbot"""
        if self.running:
            return
        add_log("Запуск юзербота...", "System", "system")
        await self.run()

    async def stop(self):
        """Stop the userbot"""
        if self.client:
            await self.client.disconnect()
        self.running = False
        add_log("Юзербот остановлен", "System", "info")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global message_logs, leads_log
    message_logs = load_logs()
    leads_log = load_leads()
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
    global bot_instance
    if bot_instance is None:
        return {"running": False, "username": None, "message_count": 0, "lead_count": 0}
    return {
        "running": bot_instance.running,
        "username": bot_instance.username,
        "message_count": bot_instance.message_count,
        "lead_count": bot_instance.lead_count
    }

@app.get("/api/config")
async def get_config():
    return load_config()

@app.post("/api/config")
async def update_config(config: ConfigModel):
    global bot_instance
    save_config(config.model_dump())
    if bot_instance:
        bot_instance.config = load_config()
    add_log("Настройки сохранены", "System", "system")
    return {"success": True}

@app.post("/api/start")
async def start_bot():
    global bot_instance
    import threading
    
    if bot_instance is None:
        bot_instance = TelegramUserbot()
    
    if bot_instance.running:
        return {"success": True, "message": "Already running"}
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bot_instance.start())
        finally:
            loop.close()
    
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    
    return {"success": True, "message": "Starting..."}

@app.post("/api/stop")
async def stop_bot():
    global bot_instance
    if bot_instance:
        await bot_instance.stop()
    return {"success": True}

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
    """Get all leads"""
    return leads_log[-50:]

@app.delete("/api/leads")
async def clear_leads():
    global leads_log
    leads_log = []
    save_leads()
    return {"success": True}

@app.get("/api/history/{chat_id}")
async def get_chat_history(chat_id: int, limit: int = 20):
    """Get last N messages from a specific chat"""
    global bot_instance
    if bot_instance is None or not bot_instance.running:
        return {"error": "Bot not running"}
    
    history = await bot_instance.fetch_chat_history(chat_id, limit)
    return {"chat_id": chat_id, "messages": history}

@app.get("/api/conversation/{chat_id}")
async def get_conversation_history(chat_id: int):
    """Get conversation history stored in memory"""
    if chat_id in conversation_history:
        return {"chat_id": chat_id, "history": conversation_history[chat_id]}
    return {"chat_id": chat_id, "history": []}

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
        .stat-card.highlight .value { color: #34d399; }
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
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; margin-bottom: 6px; color: #9ca3af; font-size: 13px; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 10px 12px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; color: #fff; font-size: 14px; }
        .form-group select { background: rgba(0,0,0,0.5); cursor: pointer; }
        .form-group select option { background: #1a1a2e; color: #fff; }
        .form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: #10b981; }
        .form-group small { color: #6b7280; font-size: 11px; }
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
        .log-image { color: #f59e0b; }
        .info-box { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); border-radius: 8px; padding: 12px 16px; margin-bottom: 20px; font-size: 13px; color: #93c5fd; }
        .feature-badge { display: inline-block; padding: 3px 8px; background: rgba(16, 185, 129, 0.2); border-radius: 4px; font-size: 11px; color: #10b981; margin-left: 8px; }
        .lead-card { background: rgba(0,0,0,0.2); border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 4px solid #f59e0b; }
        .lead-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
        .lead-client { font-weight: 600; color: #f59e0b; }
        .lead-type { font-size: 11px; padding: 2px 8px; background: rgba(245,158,11,0.2); border-radius: 4px; }
        .lead-summary { color: #9ca3af; font-size: 12px; margin-bottom: 6px; }
        .lead-meta { display: flex; gap: 15px; font-size: 11px; color: #6b7280; }
        .urgency-high { color: #ef4444; }
        .urgency-medium { color: #f59e0b; }
        .urgency-low { color: #10b981; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); border-radius: 3px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><span>🥷</span> Ninja Userbot <span class="feature-badge">Sog'lom taom</span></h1>
            <div id="statusBadge" class="status-badge status-offline">Offline</div>
        </div>
        <div class="info-box">
            <strong>Telegram Userbot для Sog'lom taom</strong> — автоответчик для клиентов здорового питания.
            Отвечает как реальный сотрудник + определяет успешные лиды → Saved Messages.
        </div>
        <div class="stats">
            <div class="stat-card"><div id="statStatus" class="value">Stopped</div><div class="label">Статус</div></div>
            <div class="stat-card"><div id="statMessages" class="value">0</div><div class="label">Сообщений</div></div>
            <div class="stat-card highlight"><div id="statLeads" class="value">0</div><div class="label">Лидов</div></div>
            <div class="stat-card"><div id="statUser" class="value">-</div><div class="label">Аккаунт</div></div>
        </div>
        <div class="tabs">
            <button class="tab active" onclick="showTab('control')">🎮 Управление</button>
            <button class="tab" onclick="showTab('leads')">🎯 Лиды</button>
            <button class="tab" onclick="showTab('settings')">⚙️ Настройки</button>
            <button class="tab" onclick="showTab('logs')">📋 Логи</button>
        </div>
        <div id="tab-control" class="panel active">
            <div style="margin-bottom: 20px;">
                <button id="startBtn" class="btn btn-primary" onclick="startBot()">▶ Запустить</button>
                <button id="stopBtn" class="btn btn-danger" onclick="stopBot()" disabled>⏹ Остановить</button>
            </div>
            <div class="logs" id="controlLogs"></div>
        </div>
        <div id="tab-leads" class="panel">
            <button class="btn" onclick="clearLeads()" style="background:#374151;margin-bottom:15px;">🗑 Очистить лиды</button>
            <div id="leadsList"></div>
        </div>
        <div id="tab-settings" class="panel">
            <h3 style="margin-bottom:16px;color:#10b981;">📱 Telegram</h3>
            <div class="form-row">
                <div class="form-group"><label>API ID</label><input type="text" id="apiId" placeholder="12345678"><small>Получить на my.telegram.org</small></div>
                <div class="form-group"><label>API Hash</label><input type="password" id="apiHash" placeholder="a1b2c3d4e5f6..."></div>
            </div>
            <h3 style="margin:20px 0 16px;color:#10b981;">🤖 Mistral AI</h3>
            <div class="form-group"><label>Mistral API Key</label><input type="password" id="mistralKey" placeholder="your-api-key"><small>Получить на console.mistral.ai</small></div>
            <div class="form-row">
                <div class="form-group"><label>Vision Model</label><select id="mistralModel"><option value="pixtral-12b-2409">Pixtral 12B</option><option value="pixtral-large-latest">Pixtral Large</option></select></div>
                <div class="form-group"><label>Text Model</label><select id="textModel"><option value="mistral-medium-latest">Mistral Medium</option><option value="mistral-small-latest">Mistral Small</option></select></div>
            </div>
            <button class="btn btn-primary" onclick="saveConfig()">💾 Сохранить</button>
        </div>
        <div id="tab-logs" class="panel">
            <button class="btn" onclick="clearLogs()" style="background:#374151;margin-bottom:15px;">🗑 Очистить логи</button>
            <div class="logs" id="logsList"></div>
        </div>
        <p style="text-align:center;color:#6b7280;margin-top:30px;font-size:12px;">🥷 Ninja Userbot • Sog'lom taom Edition</p>
    </div>
    <script>
        const API = window.location.origin + '/api';
        function showTab(name) { document.querySelectorAll('.tab').forEach(t => t.classList.remove('active')); document.querySelectorAll('.panel').forEach(t => t.classList.remove('active')); event.target.classList.add('active'); document.getElementById('tab-' + name).classList.add('active'); }
        async function updateStatus() { try { const res = await fetch(`${API}/status`); const data = await res.json(); document.getElementById('statusBadge').textContent = data.running ? 'Online' : 'Offline'; document.getElementById('statusBadge').className = 'status-badge ' + (data.running ? 'status-online' : 'status-offline'); document.getElementById('statStatus').textContent = data.running ? 'Running' : 'Stopped'; document.getElementById('statMessages').textContent = data.message_count; document.getElementById('statLeads').textContent = data.lead_count || 0; document.getElementById('statUser').textContent = data.username || '-'; document.getElementById('startBtn').disabled = data.running; document.getElementById('stopBtn').disabled = !data.running; } catch(e) { document.getElementById('statusBadge').textContent = 'No Connection'; } }
        async function loadConfig() { try { const res = await fetch(`${API}/config`); const data = await res.json(); document.getElementById('apiId').value = data.api_id || ''; document.getElementById('apiHash').value = data.api_hash || ''; document.getElementById('mistralKey').value = data.mistral_key || ''; document.getElementById('mistralModel').value = data.mistral_model || 'pixtral-12b-2409'; document.getElementById('textModel').value = data.text_model || 'mistral-medium-latest'; } catch(e) {} }
        async function saveConfig() { const config = { api_id: document.getElementById('apiId').value, api_hash: document.getElementById('apiHash').value, mistral_key: document.getElementById('mistralKey').value, mistral_model: document.getElementById('mistralModel').value, text_model: document.getElementById('textModel').value }; try { await fetch(`${API}/config`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config) }); alert('✅ Сохранено!'); loadLogs(); } catch(e) { alert('❌ Ошибка: ' + e); } }
        async function startBot() { try { await fetch(`${API}/start`, {method: 'POST'}); updateStatus(); loadLogs(); } catch(e) {} }
        async function stopBot() { try { await fetch(`${API}/stop`, {method: 'POST'}); updateStatus(); } catch(e) {} }
        async function loadLogs() { try { const res = await fetch(`${API}/logs`); const logs = await res.json(); const html = renderLogs(logs); document.getElementById('logsList').innerHTML = html; document.getElementById('controlLogs').innerHTML = html; } catch(e) {} }
        async function clearLogs() { try { await fetch(`${API}/logs`, {method: 'DELETE'}); loadLogs(); } catch(e) {} }
        async function loadLeads() { try { const res = await fetch(`${API}/leads`); const leads = await res.json(); document.getElementById('leadsList').innerHTML = renderLeads(leads); } catch(e) {} }
        async function clearLeads() { try { await fetch(`${API}/leads`, {method: 'DELETE'}); loadLeads(); updateStatus(); } catch(e) {} }
        function renderLogs(logs) { if (!logs || logs.length === 0) return '<p style="color:#6b7280;text-align:center;padding:20px;">Нет записей</p>'; return logs.slice().reverse().map(log => { const imageIcon = log.has_image ? '<span class="log-image">🖼️</span> ' : ''; return `<div class="log-entry log-${log.direction}"><span class="log-time">${log.timestamp}</span><span class="log-sender">${log.sender}</span><span class="log-message">${imageIcon}${escapeHtml(log.message)}</span></div>`; }).join(''); }
        function renderLeads(leads) { if (!leads || leads.length === 0) return '<p style="color:#6b7280;text-align:center;padding:20px;">Нет лидов</p>'; return leads.slice().reverse().map(lead => { const urgencyClass = `urgency-${lead.urgency || 'medium'}`; return `<div class="lead-card"><div class="lead-header"><span class="lead-client">👤 ${lead.client_name || 'Клиент'}</span><span class="lead-type">${lead.lead_type || 'new_client'}</span></div><div class="lead-summary">${lead.summary || ''}</div><div class="lead-meta"><span>📊 ${((lead.confidence || 0.5) * 100).toFixed(0)}%</span><span class="${urgencyClass}">⚡ ${lead.urgency || 'medium'}</span><span>🕐 ${lead.timestamp || ''}</span></div></div>`; }).join(''); }
        function escapeHtml(text) { const div = document.createElement('div'); div.textContent = text; return div.innerHTML; }
        loadConfig(); updateStatus(); loadLogs(); loadLeads(); setInterval(updateStatus, 3000); setInterval(loadLogs, 3000); setInterval(loadLeads, 5000);
    </script>
</body>
</html>'''

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve embedded web UI"""
    return HTMLResponse(content=WEB_UI_HTML)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def open_browser():
    """Open browser after server starts"""
    import time
    import webbrowser
    time.sleep(1.5)
    webbrowser.open("http://localhost:3030")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🥷 NINJA USERBOT (Sog'lom taom Edition)")
    print("="*50)
    print("Telegram Auto-Reply with Mistral AI + Vision")
    print("Отвечает как сотрудник компании здорового питания")
    print("Автоматическое определение лидов → Saved Messages")
    print("="*50 + "\n")
    
    # Open browser automatically
    import threading
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3030)
