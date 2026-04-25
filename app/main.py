"""
Ninja Auto-Reply with Desktop UI
--------------------------------
Telegram auto-reply bot with Mistral AI
"""

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import httpx
from telethon import TelegramClient, events
from telethon.tl.types import User

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("NINJA_DATA_DIR", Path.home() / ".ninja"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.txt"

# Default values
DEFAULT_CONFIG = {
    "api_id": "36244324",
    "api_hash": "15657d847ab4b8ae111ade8e2cbca51f",
    "mistral_key": "bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v",
    "mistral_model": "mistral-small-latest",
    "system_prompt": "You are the personal AI assistant replying on behalf of the account owner in Telegram private chats. Be friendly, concise, and natural. Reply in the same language the user wrote in.",
}

# Conversation memory
HISTORY_LIMIT = 12
_history: dict[int, list[dict]] = {}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ninja")


def load_config() -> dict:
    """Load config from file."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        config[key] = value
        except Exception:
            pass
    return config


def save_config(config: dict) -> None:
    """Save config to file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")


async def mistral_chat(messages: list[dict], api_key: str, model: str) -> str:
    """Call Mistral API."""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 400}
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


def push_history(chat_id: int, role: str, content: str) -> None:
    buf = _history.setdefault(chat_id, [])
    buf.append({"role": role, "content": content})
    if len(buf) > HISTORY_LIMIT:
        del buf[0 : len(buf) - HISTORY_LIMIT]


def build_messages(chat_id: int, system_prompt: str) -> list[dict]:
    return [{"role": "system", "content": system_prompt}] + _history.get(chat_id, [])


# ---------------------------------------------------------------------------
# Telegram Bot Logic
# ---------------------------------------------------------------------------
class TelegramBot:
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.running = False
        self.config = load_config()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.username: Optional[str] = None
        self.message_count = 0
        self.log_callback = None

    def log_msg(self, message: str):
        """Log message."""
        if self.log_callback:
            self.log_callback(message)
        log.info(message)
        print(message)

    async def reply_to_message(self, chat_id: int, sender: User, text: str) -> None:
        """Send auto-reply."""
        sender_name = sender.first_name or sender.last_name or str(sender.id)
        self.log_msg(f"← [{sender_name}] {text[:80]}...")
        
        push_history(chat_id, "user", text)
        
        try:
            async with self.client.action(chat_id, "typing"):
                reply = await mistral_chat(
                    build_messages(chat_id, self.config["system_prompt"]),
                    self.config["mistral_key"],
                    self.config["mistral_model"]
                )
        except Exception as e:
            self.log_msg(f"❌ Mistral error: {e}")
            return
        
        push_history(chat_id, "assistant", reply)
        await self.client.send_message(chat_id, reply)
        self.message_count += 1
        self.log_msg(f"→ [{sender_name}] {reply[:80]}...")

    async def run_bot(self):
        """Main bot loop."""
        try:
            self.client = TelegramClient(
                str(SESSION_PATH),
                int(self.config["api_id"]),
                self.config["api_hash"]
            )

            @self.client.on(events.NewMessage)
            async def handler(event):
                if event.message.out:
                    return
                if not event.is_private:
                    return
                sender = await event.get_sender()
                if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                    return
                text = (event.message.text or "").strip()
                if not text:
                    return
                await self.reply_to_message(event.chat_id, sender, text)

            await self.client.start()
            
            me = await self.client.get_me()
            self.username = f"@{me.username}" if me.username else me.first_name
            self.log_msg(f"✅ Logged in as {self.username}")
            self.running = True
            
            # Process unread messages
            self.log_msg("📧 Checking unread messages...")
            async for dialog in self.client.iter_dialogs(limit=50):
                if dialog.unread_count > 0 and dialog.is_user:
                    sender = dialog.entity
                    if not isinstance(sender, User) or sender.is_self or getattr(sender, 'bot', False):
                        continue
                    async for message in self.client.iter_messages(dialog.entity, limit=1):
                        if not message.out and message.text:
                            await self.reply_to_message(dialog.id, sender, message.text.strip())
                            break
                    await self.client.send_read_acknowledge(dialog.entity)
            
            self.log_msg("🟢 Bot is running! Waiting for messages...")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            self.log_msg(f"❌ Error: {e}")
            self.running = False

    def start(self):
        """Start bot in background thread."""
        if self.running:
            return
        
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self.run_bot())
            finally:
                self.loop.close()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the bot."""
        if self.client and self.loop:
            async def disconnect():
                await self.client.disconnect()
            
            if self.loop.is_running():
                asyncio.run_coroutine_threadsafe(disconnect(), self.loop)
        
        self.running = False
        self.log_msg("🔴 Bot stopped")


# ---------------------------------------------------------------------------
# Try Tkinter GUI, fallback to Console
# ---------------------------------------------------------------------------
def run_gui():
    """Run with Tkinter GUI."""
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    import webbrowser
    
    class NinjaApp:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("🥷 Ninja Bot - Telegram Auto-Reply")
            self.root.geometry("700x600")
            self.root.minsize(600, 500)
            
            # Bot instance
            self.bot = TelegramBot()
            self.bot.log_callback = self.add_log
            
            # Build UI
            self.setup_ui()
            
            # Load saved config
            self.load_config_to_ui()
            
            # Protocol for closing
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            
        def setup_ui(self):
            """Create the UI elements."""
            # Main container
            main_frame = ttk.Frame(self.root, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # ===== TOP: Status Bar =====
            status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
            status_frame.pack(fill=tk.X, pady=(0, 10))
            
            # Status indicator
            self.status_var = tk.StringVar(value="⚫ Stopped")
            self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=('Segoe UI', 11, 'bold'))
            self.status_label.pack(side=tk.LEFT)
            
            # Username
            self.user_var = tk.StringVar(value="Not logged in")
            ttk.Label(status_frame, textvariable=self.user_var, font=('Segoe UI', 10)).pack(side=tk.LEFT, padx=(20, 0))
            
            # Message count
            self.msg_count_var = tk.StringVar(value="Messages: 0")
            ttk.Label(status_frame, textvariable=self.msg_count_var, font=('Segoe UI', 10)).pack(side=tk.RIGHT)
            
            # ===== MIDDLE: Notebook (Tabs) =====
            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            # --- Tab 1: Control ---
            control_frame = ttk.Frame(notebook, padding="10")
            notebook.add(control_frame, text="🎮 Control")
            
            # Start/Stop buttons
            btn_frame = ttk.Frame(control_frame)
            btn_frame.pack(fill=tk.X, pady=(0, 20))
            
            self.start_btn = ttk.Button(btn_frame, text="▶️ Start Bot", command=self.start_bot, width=15)
            self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
            
            self.stop_btn = ttk.Button(btn_frame, text="⏹️ Stop Bot", command=self.stop_bot, width=15, state=tk.DISABLED)
            self.stop_btn.pack(side=tk.LEFT)
            
            # Logs
            ttk.Label(control_frame, text="📋 Activity Log:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W)
            
            self.log_text = scrolledtext.ScrolledText(control_frame, height=15, font=('Consolas', 9), state=tk.DISABLED)
            self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
            
            # Clear log button
            ttk.Button(control_frame, text="Clear Log", command=self.clear_log).pack(anchor=tk.W, pady=(5, 0))
            
            # --- Tab 2: Settings ---
            settings_frame = ttk.Frame(notebook, padding="10")
            notebook.add(settings_frame, text="⚙️ Settings")
            
            # API ID
            ttk.Label(settings_frame, text="Telegram API ID:", font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 5))
            self.api_id_entry = ttk.Entry(settings_frame, width=50)
            self.api_id_entry.pack(fill=tk.X, pady=(0, 10))
            ttk.Label(settings_frame, text="Get from my.telegram.org", font=('Segoe UI', 8), foreground='gray').pack(anchor=tk.W, pady=(0, 10))
            
            # API Hash
            ttk.Label(settings_frame, text="Telegram API Hash:", font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 5))
            self.api_hash_entry = ttk.Entry(settings_frame, width=50, show="*")
            self.api_hash_entry.pack(fill=tk.X, pady=(0, 10))
            ttk.Label(settings_frame, text="Get from my.telegram.org", font=('Segoe UI', 8), foreground='gray').pack(anchor=tk.W, pady=(0, 10))
            
            # Mistral Key
            ttk.Label(settings_frame, text="Mistral API Key:", font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 5))
            self.mistral_key_entry = ttk.Entry(settings_frame, width=50, show="*")
            self.mistral_key_entry.pack(fill=tk.X, pady=(0, 10))
            ttk.Label(settings_frame, text="Get from console.mistral.ai", font=('Segoe UI', 8), foreground='gray').pack(anchor=tk.W, pady=(0, 10))
            
            # Model
            ttk.Label(settings_frame, text="Mistral Model:", font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 5))
            self.model_entry = ttk.Entry(settings_frame, width=50)
            self.model_entry.pack(fill=tk.X, pady=(0, 10))
            self.model_entry.insert(0, "mistral-small-latest")
            
            # System Prompt
            ttk.Label(settings_frame, text="System Prompt:", font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 5))
            self.prompt_text = tk.Text(settings_frame, height=5, font=('Segoe UI', 9), wrap=tk.WORD)
            self.prompt_text.pack(fill=tk.X, pady=(0, 10))
            
            # Save button
            ttk.Button(settings_frame, text="💾 Save Settings", command=self.save_config_from_ui).pack(anchor=tk.W)
            
            # --- Tab 3: About ---
            about_frame = ttk.Frame(notebook, padding="10")
            notebook.add(about_frame, text="ℹ️ About")
            
            about_text = """
🥷 Ninja Bot v1.0

Telegram Auto-Reply with Mistral AI

This bot automatically replies to private 
messages in your Telegram account using AI.

Features:
• Auto-reply to private messages
• Mistral AI integration
• Conversation memory
• Easy configuration

Setup:
1. Get API credentials from my.telegram.org
2. Get Mistral API key from console.mistral.ai
3. Configure in Settings tab
4. Click Start Bot
            """
            ttk.Label(about_frame, text=about_text, font=('Segoe UI', 10), justify=tk.LEFT).pack(anchor=tk.W)
            
            # Link buttons
            link_frame = ttk.Frame(about_frame)
            link_frame.pack(anchor=tk.W, pady=(20, 0))
            
            ttk.Button(link_frame, text="my.telegram.org", command=lambda: webbrowser.open("https://my.telegram.org")).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(link_frame, text="console.mistral.ai", command=lambda: webbrowser.open("https://console.mistral.ai")).pack(side=tk.LEFT)
            
        def load_config_to_ui(self):
            """Load config into UI fields."""
            config = self.bot.config
            self.api_id_entry.delete(0, tk.END)
            self.api_id_entry.insert(0, config.get("api_id", ""))
            
            self.api_hash_entry.delete(0, tk.END)
            self.api_hash_entry.insert(0, config.get("api_hash", ""))
            
            self.mistral_key_entry.delete(0, tk.END)
            self.mistral_key_entry.insert(0, config.get("mistral_key", ""))
            
            self.model_entry.delete(0, tk.END)
            self.model_entry.insert(0, config.get("mistral_model", "mistral-small-latest"))
            
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", config.get("system_prompt", ""))
            
        def save_config_from_ui(self):
            """Save config from UI fields."""
            config = {
                "api_id": self.api_id_entry.get(),
                "api_hash": self.api_hash_entry.get(),
                "mistral_key": self.mistral_key_entry.get(),
                "mistral_model": self.model_entry.get(),
                "system_prompt": self.prompt_text.get("1.0", tk.END).strip(),
            }
            save_config(config)
            self.bot.config = config
            messagebox.showinfo("Saved", "Settings saved successfully!")
            
        def add_log(self, message: str):
            """Add message to log."""
            def _add():
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"{message}\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
            
            self.root.after(0, _add)
            
        def clear_log(self):
            """Clear the log."""
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            self.log_text.config(state=tk.DISABLED)
            
        def start_bot(self):
            """Start the bot."""
            # Validate config
            if not self.api_id_entry.get() or not self.api_hash_entry.get():
                messagebox.showerror("Error", "Please enter Telegram API ID and Hash in Settings")
                return
            
            if not self.mistral_key_entry.get():
                messagebox.showerror("Error", "Please enter Mistral API Key in Settings")
                return
            
            # Save config first
            self.save_config_from_ui()
            
            # Update UI
            self.status_var.set("🟢 Running")
            self.user_var.set("Connecting...")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            
            # Start bot
            self.add_log("🔄 Starting bot...")
            self.bot.start()
            
        def stop_bot(self):
            """Stop the bot."""
            self.bot.stop()
            self.status_var.set("⚫ Stopped")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            
        def update_status(self):
            """Periodic status update."""
            if self.bot.running:
                self.msg_count_var.set(f"Messages: {self.bot.message_count}")
                if self.bot.username:
                    self.user_var.set(self.bot.username)
            self.root.after(1000, self.update_status)
            
        def on_closing(self):
            """Handle window close."""
            if self.bot.running:
                self.bot.stop()
            self.root.destroy()
            
        def run(self):
            """Run the app."""
            self.update_status()
            self.root.mainloop()
    
    app = NinjaApp()
    app.run()


def run_console():
    """Run in console mode."""
    print("\n" + "=" * 50)
    print(" 🥷 NINJA BOT - Console Mode")
    print("=" * 50)
    print("\nTkinter not available. Running in console mode.\n")
    
    bot = TelegramBot()
    config = bot.config
    
    # Show current config
    print("Current Configuration:")
    print(f"  API ID: {config['api_id'][:8]}...")
    print(f"  Mistral Model: {config['mistral_model']}")
    print()
    
    print("Commands:")
    print("  start  - Start the bot")
    print("  stop   - Stop the bot")
    print("  status - Show status")
    print("  quit   - Exit")
    print()
    
    def input_loop():
        while True:
            try:
                cmd = input("> ").strip().lower()
                if cmd == "start":
                    if not bot.running:
                        print("Starting bot...")
                        bot.start()
                    else:
                        print("Bot is already running")
                elif cmd == "stop":
                    bot.stop()
                elif cmd == "status":
                    print(f"Running: {bot.running}")
                    print(f"User: {bot.username or 'Not logged in'}")
                    print(f"Messages: {bot.message_count}")
                elif cmd == "quit":
                    if bot.running:
                        bot.stop()
                    print("Bye!")
                    sys.exit(0)
                else:
                    print("Unknown command. Use: start, stop, status, quit")
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nBye!")
                sys.exit(0)
    
    # Start input loop in main thread
    input_loop()


if __name__ == "__main__":
    try:
        # Try to import tkinter
        import tkinter
        run_gui()
    except ImportError:
        print("Tkinter not available, using console mode...")
        run_console()
    except Exception as e:
        print(f"\nError: {e}")
        print("Falling back to console mode...")
        run_console()
