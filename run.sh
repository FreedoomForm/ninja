#!/bin/bash

echo "🥷 NINJA USERBOT - Установка и запуск"
echo "========================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_PROXY_DIR="$SCRIPT_DIR/ai-proxy"
APP_DIR="$SCRIPT_DIR/app"

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to wait for a service to be ready
wait_for_service() {
    local url=$1
    local max_attempts=30
    local attempt=0
    
    echo "⏳ Ожидание запуска сервиса: $url"
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "✅ Сервис готов: $url"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo "❌ Таймаут ожидания сервиса: $url"
    return 1
}

# Kill processes on exit
cleanup() {
    echo ""
    echo "🛑 Остановка сервисов..."
    
    # Kill AI Proxy
    if [ ! -z "$AI_PROXY_PID" ]; then
        kill $AI_PROXY_PID 2>/dev/null
        echo "✅ AI Proxy остановлен"
    fi
    
    # Kill Python bot
    if [ ! -z "$BOT_PID" ]; then
        kill $BOT_PID 2>/dev/null
        echo "✅ Python бот остановлен"
    fi
    
    exit 0
}

trap cleanup SIGINT SIGTERM

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js не найден. Установите Node.js для работы AI Proxy"
    exit 1
fi

# ===========================================
# SETUP AI PROXY (Next.js)
# ===========================================
echo ""
echo "🤖 НАСТРОЙКА AI PROXY"
echo "--------------------"

cd "$AI_PROXY_DIR"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Установка зависимостей AI Proxy..."
    npm install
fi

# Check if Next.js is built
if [ ! -d ".next" ]; then
    echo "🔨 Сборка AI Proxy..."
    npm run build
fi

# Check if port 3000 is available
if check_port 3000; then
    echo "⚠️  Порт 3000 занят. AI Proxy может не запуститься."
    echo "   Остановите процесс на порту 3000 или измените порт в конфигурации."
fi

# Start AI Proxy in background
echo "🚀 Запуск AI Proxy на http://localhost:3000"
npm run start &
AI_PROXY_PID=$!

# Wait for AI Proxy to be ready
if ! wait_for_service "http://localhost:3000/api/ai"; then
    echo "❌ Не удалось запустить AI Proxy"
    cleanup
    exit 1
fi

# ===========================================
# SETUP PYTHON BOT
# ===========================================
echo ""
echo "🐍 НАСТРОЙКА PYTHON БОТА"
echo "------------------------"

cd "$APP_DIR"

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Install dependencies
echo "📥 Установка зависимостей Python..."
./venv/bin/pip install -r requirements.txt -q

# Check if port 3030 is available
if check_port 3030; then
    echo "⚠️  Порт 3030 занят. Python бот может не запуститься."
fi

# ===========================================
# START PYTHON BOT
# ===========================================
echo ""
echo "🚀 Запуск Python бота на http://localhost:3030"
echo "🌐 Веб UI: откройте index.html в браузере"
echo ""
echo "Для первого входа понадобится номер телефона"
echo ""
echo "=========================================="
echo "Нажмите Ctrl+C для остановки всех сервисов"
echo "=========================================="
echo ""

# Start Python bot
./venv/bin/python main.py &
BOT_PID=$!

# Wait for either process to exit
wait -n $AI_PROXY_PID $BOT_PID

# If we get here, one of the processes exited
cleanup
