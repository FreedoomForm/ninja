"""
Ninja Userbot - Native Windows GUI Application
Telegram Auto-Reply with AI (No web server, no localhost)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import asyncio
import json
import os
import sys
import base64
import re
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
import queue

# GUI imports
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False
    import tkinter as tk
    from tkinter import ttk

# Telegram
from telethon import TelegramClient, events
from telethon.tl.types import User, MessageMediaPhoto, MessageMediaGeo, MessageMediaGeoLive, DocumentAttributeSticker

# HTTP client
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
APP_NAME = "Ninja Userbot"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Ninja"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SESSION_PATH = DATA_DIR / "ninja"
CONFIG_FILE = DATA_DIR / "config.json"
LOGS_FILE = DATA_DIR / "logs.json"
LEADS_FILE = DATA_DIR / "leads.json"
ORDERS_FILE = DATA_DIR / "orders.json"
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# AI API Configuration (Direct API calls, no proxy)
AI_API_BASE = "https://open.bigmodel.cn/api/paas/v4"
AI_API_KEY = ""  # Will be set from config
AI_MODEL = "glm-4"

# ---------------------------------------------------------------------------
# Company Info
# ---------------------------------------------------------------------------
COMPANY_INFO = """
КОМПАНИЯ: Sog'lom taom (Соғлом таом) - здоровое питание с доставкой
ЛОКАЦИЯ: Ташкент, Сергели район (ошхона)
ГРАФИК: 5-дневка (пн-пт), шанба - день уборки

ПАКЕТЫ: Классик, Индивидуал, Диабет

КАЛОРИИ И ЦЕНЫ:
- 1000–1200 ккал — 84 000 сум
- 1400–1600 ккал — 98 000 сум
- 1800–2000 ккал — 112 000 сум
- 2200–2500 ккал — 126 000 сум

ДОСТАВКА: 17:00–22:00 по маршруту
ЗАКАЗ: До 21:00 за день до доставки
КАРТЫ: Humo, Uzum, Uzcard
"""

DEFAULT_SYSTEM_PROMPT = """Ты Бахром, 35-летний сотрудник компании Sog'lom taom из Ташкента.
Отвечаешь на сообщения клиентов в Telegram дружелюбно и профессионально.
Общаешься на узбекском и русском языках.
Используешь "Сиз" для новых клиентов, "Сен" для постоянных.

ИНФОРМАЦИЯ О КОМПАНИИ:
""" + COMPANY_INFO

DEFAULT_CONFIG = {
    "api_id": "36244324",
    "api_hash": "15657d847ab4b8ae111ade8e2cbca51f",
    "ai_api_key": "",
    "ai_model": "glm-4",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "phone": "",
}

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class ClientOrder:
    chat_id: int
    client_name: str = ""
    phone: str = ""
    address: str = ""
    calories: str = ""
    total_price: int = 0
    payment_confirmed: bool = False

# ---------------------------------------------------------------------------
# AI Functions (Direct API)
# ---------------------------------------------------------------------------
async def call_ai_direct(messages: list, api_key: str, model: str = "glm-4") -> str:
    """Call AI API directly without proxy server"""
    url = f"{AI_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Add time context
    now = datetime.now()
    time_context = f"\n[ТЕКУЩЕЕ ВРЕМЯ: {now.strftime('%d.%m.%Y %H:%M')}]"

    clean_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
            content = "\n".join(text_parts)
        clean_messages.append({"role": msg["role"], "content": str(content)})

    # Add time to system message
    if clean_messages and clean_messages[0]["role"] == "system":
        clean_messages[0]["content"] += time_context

    payload = {
        "model": model,
        "messages": clean_messages,
        "temperature": 0.7,
        "max_tokens": 1000,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            raise Exception(f"AI API Error: {response.status_code}")

async def describe_image_with_ai(image_base64: str, api_key: str) -> str:
    """Describe image using AI Vision API"""
    url = f"{AI_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Опиши это изображение кратко. Если это чек - укажи сумму. Если стикер - опиши эмоцию."},
            {"type": "image_url", "image_url": {"url": image_base64}}
        ]
    }]

    payload = {
        "model": "glm-4v",
        "messages": messages,
        "max_tokens": 300,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        return "изображение"

# ---------------------------------------------------------------------------
# Main Application Class
# ---------------------------------------------------------------------------
class NinjaApp:
    def __init__(self):
        self.config = self.load_config()
        self.client: Optional[TelegramClient] = None
        self.bot_running = False
        self.conversation_history: Dict[int, list] = {}
        self.message_queue = queue.Queue()

        # Create GUI
        self.setup_gui()

        # Start message processor
        self.process_messages()

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

    def setup_gui(self):
        """Setup the main GUI window"""
        if CTK_AVAILABLE:
            self.setup_ctk_gui()
        else:
            self.setup_tk_gui()

    def setup_ctk_gui(self):
        """Setup modern CustomTkinter GUI"""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("🥷 Ninja Userbot")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Create tabview
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        # Tabs
        self.tab_main = self.tabview.add("🏠 Главная")
        self.tab_settings = self.tabview.add("⚙️ Настройки")
        self.tab_logs = self.tabview.add("📋 Логи")

        self.setup_main_tab()
        self.setup_settings_tab()
        self.setup_logs_tab()

        # Status bar
        self.status_var = ctk.StringVar(value="⏹️ Бот остановлен")
        self.status_bar = ctk.CTkLabel(self.root, textvariable=self.status_var,
                                        height=30, corner_radius=0)
        self.status_bar.pack(fill="x", side="bottom")

    def setup_tk_gui(self):
        """Fallback to standard Tkinter"""
        self.root = tk.Tk()
        self.root.title("🥷 Ninja Userbot")
        self.root.geometry("900x700")

        # Notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Main tab
        self.tab_main = ttk.Frame(notebook)
        notebook.add(self.tab_main, text="Главная")
        self.setup_main_tab_tk()

        # Settings tab
        self.tab_settings = ttk.Frame(notebook)
        notebook.add(self.tab_settings, text="Настройки")
        self.setup_settings_tab_tk()

        # Status bar
        self.status_var = tk.StringVar(value="⏹️ Бот остановлен")
        status_bar = ttk.Label(self.root, textvariable=self.status_var)
        status_bar.pack(fill="x", side="bottom")

    def setup_main_tab(self):
        """Main control panel"""
        if CTK_AVAILABLE:
            # Top frame - Auth
            auth_frame = ctk.CTkFrame(self.tab_main)
            auth_frame.pack(fill="x", padx=10, pady=10)

            ctk.CTkLabel(auth_frame, text="📱 Авторизация Telegram",
                        font=("", 16, "bold")).pack(pady=10)

            # Phone input
            phone_frame = ctk.CTkFrame(auth_frame, fg_color="transparent")
            phone_frame.pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(phone_frame, text="Телефон:").pack(side="left")
            self.phone_entry = ctk.CTkEntry(phone_frame, width=200)
            self.phone_entry.pack(side="left", padx=10)
            self.phone_entry.insert(0, self.config.get("phone", ""))

            # Auth button
            self.auth_btn = ctk.CTkButton(auth_frame, text="🔑 Войти",
                                          command=self.start_auth, width=150)
            self.auth_btn.pack(pady=10)

            # Code input (hidden initially)
            self.code_frame = ctk.CTkFrame(auth_frame, fg_color="transparent")
            ctk.CTkLabel(self.code_frame, text="Код:").pack(side="left")
            self.code_entry = ctk.CTkEntry(self.code_frame, width=100)
            self.code_entry.pack(side="left", padx=10)
            self.code_btn = ctk.CTkButton(self.code_frame, text="OK",
                                          command=self.submit_code, width=50)
            self.code_btn.pack(side="left")

            # Bot control
            control_frame = ctk.CTkFrame(self.tab_main)
            control_frame.pack(fill="x", padx=10, pady=10)

            self.start_btn = ctk.CTkButton(control_frame, text="▶️ Запустить бота",
                                           command=self.start_bot,
                                           width=200, height=40,
                                           fg_color="green", hover_color="darkgreen")
            self.start_btn.pack(side="left", padx=20, pady=10)

            self.stop_btn = ctk.CTkButton(control_frame, text="⏹️ Остановить",
                                          command=self.stop_bot,
                                          width=200, height=40,
                                          fg_color="red", hover_color="darkred",
                                          state="disabled")
            self.stop_btn.pack(side="left", padx=20, pady=10)

            # Stats
            stats_frame = ctk.CTkFrame(self.tab_main)
            stats_frame.pack(fill="x", padx=10, pady=10)

            self.stats_label = ctk.CTkLabel(stats_frame,
                                            text="📊 Сообщений: 0 | Лидов: 0",
                                            font=("", 14))
            self.stats_label.pack(pady=10)

            self.message_count = 0
            self.lead_count = 0

    def setup_main_tab_tk(self):
        """Tkinter version of main tab"""
        # Auth frame
        auth_frame = ttk.LabelFrame(self.tab_main, text="Авторизация Telegram")
        auth_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(auth_frame, text="Телефон:").grid(row=0, column=0, padx=5, pady=5)
        self.phone_entry = ttk.Entry(auth_frame, width=20)
        self.phone_entry.grid(row=0, column=1, padx=5, pady=5)
        self.phone_entry.insert(0, self.config.get("phone", ""))

        self.auth_btn = ttk.Button(auth_frame, text="Войти", command=self.start_auth)
        self.auth_btn.grid(row=0, column=2, padx=5, pady=5)

        # Code frame
        code_frame = ttk.Frame(auth_frame)
        code_frame.grid(row=1, column=0, columnspan=3, pady=5)

        ttk.Label(code_frame, text="Код:").pack(side="left")
        self.code_entry = ttk.Entry(code_frame, width=10)
        self.code_entry.pack(side="left", padx=5)

        self.code_btn = ttk.Button(code_frame, text="OK", command=self.submit_code)
        self.code_btn.pack(side="left")

        # Control frame
        control_frame = ttk.Frame(self.tab_main)
        control_frame.pack(fill="x", padx=10, pady=10)

        self.start_btn = ttk.Button(control_frame, text="▶️ Запустить бота",
                                    command=self.start_bot)
        self.start_btn.pack(side="left", padx=10, pady=10)

        self.stop_btn = ttk.Button(control_frame, text="⏹️ Остановить",
                                   command=self.stop_bot, state="disabled")
        self.stop_btn.pack(side="left", padx=10, pady=10)

        # Stats
        self.stats_label = ttk.Label(self.tab_main, text="📊 Сообщений: 0 | Лидов: 0")
        self.stats_label.pack(pady=10)

    def setup_settings_tab(self):
        """Settings configuration"""
        if CTK_AVAILABLE:
            # API Settings
            api_frame = ctk.CTkFrame(self.tab_settings)
            api_frame.pack(fill="x", padx=10, pady=10)

            ctk.CTkLabel(api_frame, text="🤖 AI API Настройки",
                        font=("", 16, "bold")).pack(pady=10)

            # API Key
            key_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
            key_frame.pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(key_frame, text="API Key:").pack(side="left")
            self.api_key_entry = ctk.CTkEntry(key_frame, width=400, show="*")
            self.api_key_entry.pack(side="left", padx=10)
            self.api_key_entry.insert(0, self.config.get("ai_api_key", ""))

            # Model
            model_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
            model_frame.pack(fill="x", padx=20, pady=5)

            ctk.CTkLabel(model_frame, text="Модель:").pack(side="left")
            self.model_entry = ctk.CTkEntry(model_frame, width=200)
            self.model_entry.pack(side="left", padx=10)
            self.model_entry.insert(0, self.config.get("ai_model", "glm-4"))

            # System Prompt
            prompt_frame = ctk.CTkFrame(self.tab_settings)
            prompt_frame.pack(fill="both", expand=True, padx=10, pady=10)

            ctk.CTkLabel(prompt_frame, text="📝 Системный промпт",
                        font=("", 14, "bold")).pack(pady=5)

            self.prompt_text = ctk.CTkTextbox(prompt_frame, height=300)
            self.prompt_text.pack(fill="both", expand=True, padx=10, pady=5)
            self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

            # Save button
            ctk.CTkButton(self.tab_settings, text="💾 Сохранить настройки",
                         command=self.save_settings, width=200).pack(pady=10)

    def setup_settings_tab_tk(self):
        """Tkinter version of settings"""
        # API Frame
        api_frame = ttk.LabelFrame(self.tab_settings, text="AI API Настройки")
        api_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(api_frame, text="API Key:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.api_key_entry = ttk.Entry(api_frame, width=50, show="*")
        self.api_key_entry.grid(row=0, column=1, padx=5, pady=5)
        self.api_key_entry.insert(0, self.config.get("ai_api_key", ""))

        ttk.Label(api_frame, text="Модель:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.model_entry = ttk.Entry(api_frame, width=20)
        self.model_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.model_entry.insert(0, self.config.get("ai_model", "glm-4"))

        # Prompt
        prompt_frame = ttk.LabelFrame(self.tab_settings, text="Системный промпт")
        prompt_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, height=20)
        self.prompt_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT))

        ttk.Button(self.tab_settings, text="💾 Сохранить",
                  command=self.save_settings).pack(pady=10)

    def setup_logs_tab(self):
        """Message logs display"""
        if CTK_AVAILABLE:
            self.log_text = ctk.CTkTextbox(self.tab_logs)
            self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

            ctk.CTkButton(self.tab_logs, text="🗑️ Очистить логи",
                         command=self.clear_logs, width=150).pack(pady=5)
        else:
            self.log_text = scrolledtext.ScrolledText(self.tab_logs)
            self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

            ttk.Button(self.tab_logs, text="Очистить",
                      command=self.clear_logs).pack(pady=5)

    def clear_logs(self):
        if CTK_AVAILABLE:
            self.log_text.delete("1.0", "end")
        else:
            self.log_text.delete("1.0", tk.END)

    def log_message(self, message: str, sender: str = "System"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {sender}: {message}\n"

        if CTK_AVAILABLE:
            self.log_text.insert("end", log_entry)
            self.log_text.see("end")
        else:
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)

    def save_settings(self):
        self.config["ai_api_key"] = self.api_key_entry.get()
        self.config["ai_model"] = self.model_entry.get()

        if CTK_AVAILABLE:
            self.config["system_prompt"] = self.prompt_text.get("1.0", "end-1c")
        else:
            self.config["system_prompt"] = self.prompt_text.get("1.0", tk.END).strip()

        self.save_config()
        self.log_message("✅ Настройки сохранены")
        messagebox.showinfo("Сохранено", "Настройки успешно сохранены!")

    def start_auth(self):
        """Start Telegram authentication"""
        phone = self.phone_entry.get().strip()
        if not phone:
            messagebox.showerror("Ошибка", "Введите номер телефона")
            return

        self.config["phone"] = phone
        self.save_config()

        self.log_message(f"📱 Начинаем авторизацию: {phone}")

        # Start auth in background
        threading.Thread(target=self._do_auth, daemon=True).start()

    def _do_auth(self):
        """Do actual auth in background"""
        async def auth():
            try:
                self.client = TelegramClient(
                    str(SESSION_PATH),
                    int(self.config.get("api_id", "0")),
                    self.config.get("api_hash", "")
                )
                await self.client.connect()

                if await self.client.is_user_authorized():
                    self.message_queue.put(("auth_success", "Already authorized"))
                    return

                # Send code
                result = await self.client.send_code_request(self.config["phone"])
                self.phone_code_hash = result.phone_code_hash
                self.message_queue.put(("code_needed", ""))

            except Exception as e:
                self.message_queue.put(("auth_error", str(e)))

        asyncio.run(auth())

    def submit_code(self):
        """Submit verification code"""
        code = self.code_entry.get().strip()
        if not code:
            return

        threading.Thread(target=self._do_sign_in, args=(code,), daemon=True).start()

    def _do_sign_in(self, code: str):
        """Sign in with code"""
        async def sign_in():
            try:
                await self.client.sign_in(
                    self.config["phone"],
                    code,
                    phone_code_hash=self.phone_code_hash
                )
                self.message_queue.put(("auth_success", ""))
            except Exception as e:
                self.message_queue.put(("auth_error", str(e)))

        asyncio.run(sign_in())

    def start_bot(self):
        """Start the bot"""
        if not self.client or not self.client.is_connected():
            messagebox.showerror("Ошибка", "Сначала авторизуйтесь в Telegram")
            return

        if not self.config.get("ai_api_key"):
            messagebox.showwarning("Внимание", "Укажите AI API Key в настройках")

        self.bot_running = True

        if CTK_AVAILABLE:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
        else:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")

        self.status_var.set("✅ Бот работает")

        # Start bot loop
        threading.Thread(target=self._bot_loop, daemon=True).start()
        self.log_message("🤖 Бот запущен!")

    def stop_bot(self):
        """Stop the bot"""
        self.bot_running = False

        if CTK_AVAILABLE:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        else:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

        self.status_var.set("⏹️ Бот остановлен")
        self.log_message("⏹️ Бот остановлен")

    def _bot_loop(self):
        """Main bot loop"""
        async def run_bot():
            @self.client.on(events.NewMessage(incoming=True))
            async def handler(event):
                if not self.bot_running:
                    return

                try:
                    sender = await event.get_sender()
                    if isinstance(sender, User) and not sender.bot:
                        await self.process_message(event, sender)
                except Exception as e:
                    self.log_message(f"Ошибка: {e}")

            await self.client.run_until_disconnected()

        asyncio.run(run_bot())

    async def process_message(self, event, sender: User):
        """Process incoming message"""
        chat_id = event.chat_id
        text = event.text or ""
        sender_name = sender.first_name or "Unknown"

        self.message_count += 1
        self.message_queue.put(("stats", f"{self.message_count}:{self.lead_count}"))

        self.log_message(text[:100], sender_name)

        # Skip if no API key
        if not self.config.get("ai_api_key"):
            return

        # Build conversation
        if chat_id not in self.conversation_history:
            self.conversation_history[chat_id] = []

        # Add user message
        self.conversation_history[chat_id].append({
            "role": "user",
            "content": text
        })

        # Build messages for AI
        messages = [
            {"role": "system", "content": self.config.get("system_prompt", DEFAULT_SYSTEM_PROMPT)}
        ]
        messages.extend(self.conversation_history[chat_id][-10:])

        try:
            # Get AI response
            response = await call_ai_direct(
                messages,
                self.config["ai_api_key"],
                self.config.get("ai_model", "glm-4")
            )

            # Send response
            await event.reply(response)

            # Add to history
            self.conversation_history[chat_id].append({
                "role": "assistant",
                "content": response
            })

            self.log_message(response[:100], "AI")

        except Exception as e:
            self.log_message(f"AI Error: {e}")

    def process_messages(self):
        """Process messages from background threads"""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()

                if msg_type == "auth_success":
                    self.log_message("✅ Авторизация успешна!")
                    self.status_var.set("✅ Авторизован")

                elif msg_type == "code_needed":
                    self.log_message("📱 Введите код из Telegram")
                    if CTK_AVAILABLE:
                        self.code_frame.pack(pady=5)
                    messagebox.showinfo("Код", "Введите код из Telegram")

                elif msg_type == "auth_error":
                    self.log_message(f"❌ Ошибка: {data}")
                    messagebox.showerror("Ошибка авторизации", data)

                elif msg_type == "stats":
                    msg_count, lead_count = data.split(":")
                    self.stats_label.configure(
                        text=f"📊 Сообщений: {msg_count} | Лидов: {lead_count}"
                    )
        except queue.Empty:
            pass

        # Schedule next check
        self.root.after(100, self.process_messages)

    def run(self):
        """Run the application"""
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main():
    # Hide console on Windows
    if sys.platform == 'win32':
        try:
            import ctypes
            console = ctypes.windll.kernel32.GetConsoleWindow()
            if console:
                ctypes.windll.user32.ShowWindow(console, 0)
        except:
            pass

    app = NinjaApp()
    app.run()


if __name__ == "__main__":
    main()
