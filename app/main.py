"""
Ninja Userbot - Telegram Auto-Reply with Mistral AI
Runs as YOUR Telegram account (Userbot, not Bot)
Supports images via Mistral Vision API
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
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "api_id": "",
    "api_hash": "",
    "mistral_key": "",
    "mistral_model": "pixtral-12b-2409",  # Vision model for images
    "text_model": "mistral-medium-latest",  # Text-only model
    "system_prompt": "Ты личный AI-ассистент, который отвечает от имени владельца аккаунта в Telegram. Отвечай дружелюбно, кратко и естественно. Отвечай на том же языке, на котором написал собеседник. Учитывай контекст разговора. Если присылают изображение - опиши его и прокомментируй.",
}

# Conversation history per chat (supports multimodal content)
HISTORY_LIMIT = 20
conversation_history: dict[int, list[dict]] = {}
message_logs: list = []

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

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except:
            pass
    return config

def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

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
        json.dump(message_logs[-500:], f, indent=2)

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
    
    # Check if any message contains images
    has_images = False
    for msg in messages:
        if isinstance(msg.get("content"), list):
            for item in msg["content"]:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    has_images = True
                    break
    
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
                
                messages = get_conversation_messages(chat_id, self.config["system_prompt"])
                
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
            
            add_log("🚀 Юзербот работает! Жду новых сообщений (текст + изображения)...", "System", "success")
            
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
    global message_logs
    message_logs = load_logs()
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
        return {"running": False, "username": None, "message_count": 0}
    return {
        "running": bot_instance.running,
        "username": bot_instance.username,
        "message_count": bot_instance.message_count
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
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🥷 NINJA USERBOT (Vision Edition)")
    print("="*50)
    print("Telegram Auto-Reply with Mistral AI + Vision")
    print("Запускается как ВАШ аккаунт (не бот)")
    print("Поддержка текста и изображений")
    print("="*50 + "\n")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3030)
