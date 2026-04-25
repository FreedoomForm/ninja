"""
Ninja Auto-Reply
----------------
Logs into your Telegram account with Telethon, listens for incoming
private messages, and auto-replies using Mistral AI.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
API_ID = int(os.environ.get("TELEGRAM_API_ID", "36244324"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "15657d847ab4b8ae111ade8e2cbca51f")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

# Session and data
DATA_DIR = Path(os.environ.get("NINJA_DATA_DIR", Path.home() / ".ninja"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"

# Conversation memory
HISTORY_LIMIT = 12
_history: dict[int, list[dict]] = {}

SYSTEM_PROMPT = (
    "You are the personal AI assistant replying on behalf of the account owner "
    "in Telegram private chats. Be friendly, concise, and natural. Reply in the "
    "same language the user wrote in. Never reveal that you are an AI unless "
    "the user explicitly asks. Keep answers short (1-3 sentences)."
)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("ninja")
log.setLevel(logging.DEBUG)
logging.getLogger("telethon").setLevel(logging.WARNING)


async def mistral_chat(messages: list[dict]) -> str:
    """Call Mistral chat-completions."""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MISTRAL_MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 400}
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def push_history(chat_id: int, role: str, content: str) -> None:
    buf = _history.setdefault(chat_id, [])
    buf.append({"role": role, "content": content})
    if len(buf) > HISTORY_LIMIT:
        del buf[0 : len(buf) - HISTORY_LIMIT]


def build_messages(chat_id: int) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}] + _history.get(chat_id, [])


async def reply_to_message(client: TelegramClient, chat_id: int, sender: User, text: str) -> None:
    """Send auto-reply to a message."""
    sender_name = sender.first_name or sender.last_name or str(sender.id)
    log.info("← [%s] %s", sender_name, text[:120])
    
    push_history(chat_id, "user", text)
    
    try:
        async with client.action(chat_id, "typing"):
            reply = await mistral_chat(build_messages(chat_id))
    except Exception as e:
        log.exception("Mistral error: %s", e)
        return
    
    push_history(chat_id, "assistant", reply)
    await client.send_message(chat_id, reply)
    log.info("→ [%s] %s", sender_name, reply[:120])


async def main() -> None:
    log.info("Starting Ninja auto-reply…")
    log.info("Session file: %s.session", SESSION_PATH)

    client = TelegramClient(str(SESSION_PATH), API_ID, API_HASH)
    
    # Register event handler for NEW messages
    @client.on(events.NewMessage)
    async def handler(event):
        if event.message.out:
            return
        
        log.info("📨 New message | chat_id=%s | is_private=%s", event.chat_id, event.is_private)
        
        if not event.is_private:
            return
        
        sender = await event.get_sender()
        if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
            return
        
        text = (event.message.text or "").strip()
        if not text:
            return
        
        await reply_to_message(client, event.chat_id, sender, text)

    await client.start()
    
    me = await client.get_me()
    log.info("Logged in as %s (id=%s)", getattr(me, "username", None) or me.first_name, me.id)
    print(f"\n✅ Logged in as {me.first_name} (@{me.username}). Auto-reply is ON.\nPress Ctrl+C to stop.\n")

    # Process UNREAD messages
    log.info("Checking for unread messages...")
    try:
        async for dialog in client.iter_dialogs(limit=50):
            if dialog.unread_count > 0 and dialog.is_user:
                log.info("📬 Found %d unread message(s) from %s", dialog.unread_count, dialog.name)
                
                # Get the sender (user entity)
                sender = dialog.entity
                if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                    continue
                
                # Get only the LAST unread message (avoid spamming 41 replies)
                async for message in client.iter_messages(dialog.entity, limit=1):
                    if not message.out and message.text:
                        await reply_to_message(client, dialog.id, sender, message.text.strip())
                        break
                
                await client.send_read_acknowledge(dialog.entity)
    except Exception as e:
        log.exception("Error processing unread: %s", e)

    log.info("✅ Ready! Waiting for new messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)
