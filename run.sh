#!/bin/bash

echo "🥷 NINJA USERBOT - Установка и запуск"
echo "========================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден"
    exit 1
fi

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Install dependencies
echo "📥 Установка зависимостей..."
./venv/bin/pip install -r requirements.txt -q

echo ""
echo "🚀 Запуск бэкенда на http://localhost:3030"
echo "🌐 Веб UI: откройте index.html в браузере"
echo ""
echo "Для первого входа понадобится номер телефона"
echo ""

# Start the backend
./venv/bin/python main.py
