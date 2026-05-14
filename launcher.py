#!/usr/bin/env python3
"""
Ninja Launcher - Запускает AI Proxy и Python Bot вместе
========================================================
Запускает:
1. Next.js AI Proxy на порту 3000 (GLM AI)
2. Python Telegram Bot на порту 3030
"""

import os
import sys
import time
import signal
import subprocess
import threading
import http.client
from pathlib import Path

# Получаем директорию скрипта
SCRIPT_DIR = Path(__file__).parent.absolute()
AI_PROXY_DIR = SCRIPT_DIR / "ai-proxy"
APP_DIR = SCRIPT_DIR / "app"

# PID процессов
processes = []


def log(msg: str, level: str = "INFO"):
    """Логирование с временным штампом"""
    timestamp = time.strftime("%H:%M:%S")
    prefix = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "START": "🚀"}
    print(f"[{timestamp}] {prefix.get(level, '')} {msg}")


def check_port(port: int) -> bool:
    """Проверить, занят ли порт"""
    try:
        conn = http.client.HTTPConnection("localhost", port, timeout=1)
        conn.request("GET", "/")
        conn.getresponse()
        return True
    except:
        return False


def wait_for_service(port: int, path: str = "/", timeout: int = 30) -> bool:
    """Ожидание запуска сервиса"""
    log(f"Ожидание запуска сервиса на порту {port}...", "INFO")
    
    for i in range(timeout):
        try:
            conn = http.client.HTTPConnection("localhost", port, timeout=1)
            conn.request("GET", path)
            response = conn.getresponse()
            if response.status < 500:
                log(f"Сервис на порту {port} готов", "OK")
                return True
        except:
            pass
        time.sleep(1)
    
    log(f"Таймаут ожидания сервиса на порту {port}", "ERROR")
    return False


def run_command(cmd: list, cwd: Path, name: str) -> subprocess.Popen:
    """Запуск команды в отдельном процессе"""
    log(f"Запуск {name}...", "START")
    log(f"Команда: {' '.join(cmd)}", "INFO")
    log(f"Директория: {cwd}", "INFO")
    
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True
    )
    
    # Поток для вывода логов
    def log_output():
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"[{name}] {line.rstrip()}")
    
    thread = threading.Thread(target=log_output, daemon=True)
    thread.start()
    
    return process


def setup_ai_proxy():
    """Настройка и запуск AI Proxy"""
    log("Настройка AI Proxy...", "INFO")
    
    if not AI_PROXY_DIR.exists():
        log(f"Директория AI Proxy не найдена: {AI_PROXY_DIR}", "ERROR")
        return None
    
    # Проверяем node_modules
    node_modules = AI_PROXY_DIR / "node_modules"
    if not node_modules.exists():
        log("Установка зависимостей AI Proxy (npm install)...", "INFO")
        subprocess.run(["npm", "install"], cwd=str(AI_PROXY_DIR), check=True)
    
    # Проверяем .next (сборка)
    next_dir = AI_PROXY_DIR / ".next"
    if not next_dir.exists():
        log("Сборка AI Proxy (npm run build)...", "INFO")
        subprocess.run(["npm", "run", "build"], cwd=str(AI_PROXY_DIR), check=True)
    
    # Запускаем
    process = run_command(
        ["npm", "run", "start"],
        AI_PROXY_DIR,
        "AI-Proxy"
    )
    
    return process


def setup_python_bot():
    """Настройка и запуск Python бота"""
    log("Настройка Python бота...", "INFO")
    
    if not APP_DIR.exists():
        log(f"Директория App не найдена: {APP_DIR}", "ERROR")
        return None
    
    # Проверяем venv
    venv_dir = APP_DIR / "venv"
    if not venv_dir.exists():
        log("Создание виртуального окружения...", "INFO")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    
    # Путь к python в venv
    venv_python = venv_dir / "bin" / "python"
    if not venv_python.exists():
        venv_python = venv_dir / "Scripts" / "python.exe"  # Windows
    
    # Устанавливаем зависимости
    requirements = APP_DIR / "requirements.txt"
    if requirements.exists():
        log("Установка зависимостей Python...", "INFO")
        subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(requirements), "-q"], check=True)
    
    # Запускаем
    process = run_command(
        [str(venv_python), "main.py"],
        APP_DIR,
        "Bot"
    )
    
    return process


def cleanup(signum=None, frame=None):
    """Остановка всех процессов"""
    log("Остановка всех сервисов...", "WARN")
    
    for process in processes:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()
    
    log("Все сервисы остановлены", "OK")
    sys.exit(0)


def main():
    global processes
    
    print("\n" + "=" * 50)
    print("🥷 NINJA USERBOT - LAUNCHER")
    print("=" * 50)
    print()
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Проверяем Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        log(f"Node.js версия: {result.stdout.strip()}", "INFO")
    except FileNotFoundError:
        log("Node.js не найден! Установите Node.js для работы AI Proxy", "ERROR")
        sys.exit(1)
    
    # Проверяем Python
    log(f"Python версия: {sys.version.split()[0]}", "INFO")
    
    print()
    
    # 1. Запуск AI Proxy
    if check_port(3000):
        log("Порт 3000 занят. AI Proxy может не запуститься.", "WARN")
    
    ai_proxy_process = setup_ai_proxy()
    if ai_proxy_process:
        processes.append(ai_proxy_process)
    
    # Ждем запуска AI Proxy
    if not wait_for_service(3000, "/api/ai"):
        log("Не удалось запустить AI Proxy. Продолжаем без него...", "WARN")
    
    print()
    
    # 2. Запуск Python бота
    if check_port(3030):
        log("Порт 3030 занят. Python бот может не запуститься.", "WARN")
    
    bot_process = setup_python_bot()
    if bot_process:
        processes.append(bot_process)
    
    print()
    print("=" * 50)
    print("🌐 AI Proxy:   http://localhost:3000")
    print("🤖 Python Bot: http://localhost:3030")
    print("📋 Web UI:     откройте app/web/index.html")
    print("=" * 50)
    print("Нажмите Ctrl+C для остановки")
    print("=" * 50)
    print()
    
    # Ожидаем завершения любого процесса
    while True:
        for i, process in enumerate(processes):
            if process and process.poll() is not None:
                log(f"Процесс завершился с кодом: {process.returncode}", "WARN")
                cleanup()
        time.sleep(1)


if __name__ == "__main__":
    main()
