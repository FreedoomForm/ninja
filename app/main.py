"""
Ninja Auto-Reply
----------------
Logs into your Telegram account with Telethon, listens for incoming
private messages, and auto-replies using Mistral AI.

On first run it will ask for your phone number and the code Telegram
sends you, then store the session in `ninja.session` next to the script
so subsequent launches are silent.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx
from telethon import TelegramClient, events, types
from telethon.tl.types import User, PeerUser

# ---------------------------------------------------------------------------
# Hard-coded credentials (provided by user)
# ---------------------------------------------------------------------------
API_ID = int(os.environ.get("TELEGRAM_API_ID", "36244324"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "15657d847ab4b8ae111ade8e2cbca51f")
MISTRAL_API_KEY = os.environ.get(
    "MISTRAL_API_KEY", "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v"
)
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

# Where to store the Telethon session and the chat history cache
DATA_DIR = Path(os.environ.get("NINJA_DATA_DIR", Path.home() / ".ninja"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"  # Telethon will append .session

# Conversation memory (per-chat).  Kept small to stay inside Mistral context.
HISTORY_LIMIT = 12
_history: dict[int, list[dict]] = {}

SYSTEM_PROMPT = (
    "You are the personal AI assistant replying on behalf of the account owner "
    "in Telegram private chats. Be friendly, concise, and natural. Reply in the "
    "same language the user wrote in. Never reveal that you are an AI unless "
    "the user explicitly asks. Keep answers short (1-3 sentences) unless a "
    "longer answer is clearly needed."
)

# ---------------------------------------------------------------------------
# Logging - reduce Telethon noise
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ninja")
log.setLevel(logging.DEBUG)

# Silence Telethon's verbose debug logging
logging.getLogger("telethon").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Mistral helper
# ---------------------------------------------------------------------------
async def mistral_chat(messages: list[dict]) -> str:
    """Call Mistral chat-completions and return the assistant text."""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 400,
    }
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"].strip()


def _push_history(chat_id: int, role: str, content: str) -> None:
    buf = _history.setdefault(chat_id, [])
    buf.append({"role": role, "content": content})
    # Trim
    if len(buf) > HISTORY_LIMIT:
        del buf[0 : len(buf) - HISTORY_LIMIT]


def _build_messages(chat_id: int) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}] + _history.get(chat_id, [])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    log.info("Starting Ninja auto-reply…")
    log.info("Session file: %s.session", SESSION_PATH)

    client = TelegramClient(str(SESSION_PATH), API_ID, API_HASH)
    
    # Register event handler BEFORE starting client
    @client.on(events.NewMessage)
    async def handler(event):
        # Get the message
        message = event.message
        
        # Skip outgoing messages
        if message.out:
            log.debug("Skipped: outgoing message")
            return
        
        # Log that we received something
        log.info("📨 Received message | chat_id=%s | is_private=%s", event.chat_id, event.is_private)
        
        # Only reply to private chats
        if not event.is_private:
            log.debug("Skipped: not private chat")
            return
        
        # Get sender info
        sender = await event.get_sender()
        if not isinstance(sender, User):
            log.debug("Skipped: sender is not a User (type=%s)", type(sender).__name__)
            return
        
        # Skip self and bots
        if sender.is_self:
            log.debug("Skipped: message from self")
            return
        
        is_bot = getattr(sender, 'bot', False)
        if is_bot:
            log.debug("Skipped: message from bot")
            return

        # Get message text
        text = (message.text or "").strip()
        if not text:
            log.debug("Skipped: empty message")
            return
        
        chat_id = event.chat_id
        sender_name = sender.first_name or sender.last_name or str(sender.id)
        log.info("← [%s] %s", sender_name, text[:120])

        _push_history(chat_id, "user", text)

        try:
            async with client.action(chat_id, "typing"):
                reply = await mistral_chat(_build_messages(chat_id))
        except Exception as e:
            log.exception("Mistral error: %s", e)
            return

        _push_history(chat_id, "assistant", reply)
        await event.reply(reply)
        log.info("→ [%s] %s", sender_name, reply[:120])

    # Now start the client
    await client.start()
    
    me = await client.get_me()
    log.info("Logged in as %s (id=%s)", getattr(me, "username", None) or me.first_name, me.id)
    print(f"\n✅ Logged in as {me.first_name} (@{me.username}). Auto-reply is ON.\n"
          f"Press Ctrl+C to stop.\n")

    log.info("Waiting for messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)
