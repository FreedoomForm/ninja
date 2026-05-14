"""
Ninja Launcher (компилируется в ninja.exe)
------------------------------------------
Скачивает Python, Node.js, устанавливает зависимости, запускает бота с AI Proxy.
Без консоли!
"""

import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
import threading
from pathlib import Path

# Скрыть консоль на Windows
if sys.platform == 'win32':
    try:
        import ctypes
        console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if console_hwnd:
            ctypes.windll.user32.ShowWindow(console_hwnd, 0)
    except:
        pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_NAME = "Ninja"
PY_VERSION = "3.11.9"
NODE_VERSION = "20.11.0"

PY_EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"

RAW_BASE = os.environ.get(
    "NINJA_RAW_BASE",
    "https://raw.githubusercontent.com/FreedoomForm/ninja/main",
)
FILES_TO_FETCH = ["main.py", "requirements.txt"]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
ROOT = APPDATA / APP_NAME
PY_DIR = ROOT / "python"
NODE_DIR = ROOT / "nodejs"
APP_DIR = ROOT / "app"
AI_PROXY_DIR = ROOT / "ai-proxy"
WEB_DIR = APP_DIR / "web"
PY_EXE = PY_DIR / "python.exe"
NODE_EXE = NODE_DIR / "node.exe"
NPM_EXE = NODE_DIR / "npm.cmd"
MARK = ROOT / ".installed"
LOG_FILE = ROOT / "launcher.log"

# Process references
ai_proxy_process = None
bot_process = None


def log(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} | {msg}\n")
    except:
        pass


def download(url: str, dest: Path) -> None:
    log(f"Downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def download_bytes(url: str) -> bytes:
    log(f"Downloading {url}")
    with urllib.request.urlopen(url) as r:
        return r.read()


def install_python() -> None:
    log("Installing embedded Python...")
    PY_DIR.mkdir(parents=True, exist_ok=True)

    data = download_bytes(PY_EMBED_URL)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(PY_DIR)

    # Enable site-packages
    for pth in PY_DIR.glob("python*._pth"):
        text = pth.read_text()
        lines = text.split('\n')
        new_lines = []
        for line in lines:
            if line.strip() == "#import site":
                new_lines.append("import site")
            else:
                new_lines.append(line)
        new_lines.append("Lib/site-packages")
        pth.write_text('\n'.join(new_lines))

    getpip = ROOT / "get-pip.py"
    download(GETPIP_URL, getpip)
    log("Bootstrapping pip...")

    subprocess.run(
        [str(PY_EXE), str(getpip), "--no-warn-script-location"],
        capture_output=True
    )
    getpip.unlink(missing_ok=True)
    log("Python installed")


def install_nodejs() -> None:
    """Install Node.js embedded for AI Proxy"""
    log("Installing Node.js...")
    NODE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        data = download_bytes(NODE_URL)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Extract to temp, then move
            temp_dir = ROOT / "node_temp"
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            zf.extractall(temp_dir)

            # Move contents from node-v20.11.0-win-x64 to NODE_DIR
            extracted = list(temp_dir.iterdir())[0]
            log(f"Extracted Node.js from: {extracted}")
            for item in extracted.iterdir():
                dest = NODE_DIR / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest, ignore_errors=True)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))
                log(f"Moved: {item.name}")

            shutil.rmtree(temp_dir, ignore_errors=True)

        # Verify installation
        if NODE_EXE.exists():
            log(f"node.exe installed at: {NODE_EXE}")
        else:
            log(f"WARNING: node.exe not found at {NODE_EXE}")

        if NPM_EXE.exists():
            log(f"npm.cmd installed at: {NPM_EXE}")
        else:
            log(f"WARNING: npm.cmd not found at {NPM_EXE}")
            # List what we have
            log(f"NODE_DIR contents: {[f.name for f in NODE_DIR.iterdir()]}")

        log("Node.js installed")
    except Exception as e:
        log(f"ERROR installing Node.js: {e}")
        raise


def fetch_app() -> None:
    log("Fetching app files...")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(exist_ok=True)

    cache_buster = int(time.time())

    for name in FILES_TO_FETCH:
        download(f"{RAW_BASE}/app/{name}?t={cache_buster}", APP_DIR / name)

    download(f"{RAW_BASE}/app/web/index.html?t={cache_buster}", WEB_DIR / "index.html")


def fetch_ai_proxy() -> None:
    """Download AI Proxy files from GitHub"""
    log("Fetching AI Proxy files...")
    AI_PROXY_DIR.mkdir(parents=True, exist_ok=True)

    cache_buster = int(time.time())

    # Core files needed for Next.js standalone
    ai_proxy_files = [
        "package.json",
        "next.config.js",
        "tsconfig.json",
        "next-env.d.ts",
    ]

    # App files
    app_files = [
        "app/layout.tsx",
        "app/page.tsx",
        "app/api/ai/route.ts",
        "app/api/ai/vision/route.ts",
        "app/api/chat/completions/route.ts",
    ]

    all_files = ai_proxy_files + app_files

    for file_path in all_files:
        url = f"{RAW_BASE}/ai-proxy/{file_path}?t={cache_buster}"
        dest = AI_PROXY_DIR / file_path
        try:
            download(url, dest)
        except Exception as e:
            log(f"Warning: Could not download {file_path}: {e}")


def pip_install() -> bool:
    log("Installing Python dependencies...")

    # First install setuptools
    result = subprocess.run(
        [str(PY_EXE), "-m", "pip", "install", "--no-warn-script-location", "setuptools"],
        capture_output=True
    )

    # Then install the rest
    result = subprocess.run(
        [str(PY_EXE), "-m", "pip", "install", "--no-warn-script-location", "-r", str(APP_DIR / "requirements.txt")],
        capture_output=True
    )

    return result.returncode == 0


def npm_install_ai_proxy() -> bool:
    """Install npm dependencies and build AI Proxy"""
    log("Installing AI Proxy dependencies...")

    # Проверяем наличие npm
    if not NPM_EXE.exists():
        log(f"ERROR: npm.cmd not found at {NPM_EXE}")
        return False

    if sys.platform == 'win32':
        # npm install с shell=True
        result = subprocess.run(
            f'"{str(NPM_EXE)}" install',
            cwd=str(AI_PROXY_DIR),
            shell=True,
            capture_output=True
        )
    else:
        result = subprocess.run(
            [str(NPM_EXE), "install"],
            cwd=str(AI_PROXY_DIR),
            capture_output=True
        )

    if result.returncode != 0:
        log(f"npm install failed: {result.stderr.decode() if result.stderr else 'unknown'}")
        return False

    log("Building AI Proxy...")
    if sys.platform == 'win32':
        result = subprocess.run(
            f'"{str(NPM_EXE)}" run build',
            cwd=str(AI_PROXY_DIR),
            shell=True,
            capture_output=True
        )
    else:
        result = subprocess.run(
            [str(NPM_EXE), "run", "build"],
            cwd=str(AI_PROXY_DIR),
            capture_output=True
        )

    if result.returncode != 0:
        log(f"npm build failed: {result.stderr.decode() if result.stderr else 'unknown'}")
        return False

    log("AI Proxy ready")
    return True


def first_run() -> bool:
    ROOT.mkdir(parents=True, exist_ok=True)
    install_python()
    install_nodejs()
    fetch_app()
    fetch_ai_proxy()
    if not pip_install():
        log("WARNING: pip install had issues, continuing anyway...")
    if not npm_install_ai_proxy():
        log("WARNING: AI Proxy setup had issues, continuing anyway...")
    MARK.write_text("ok")
    log("Installation complete")
    return True


def update_app() -> None:
    try:
        fetch_app()
        pip_install()
        fetch_ai_proxy()
        npm_install_ai_proxy()
    except Exception as e:
        log(f"Update failed: {e}")


def start_ai_proxy():
    """Start AI Proxy server in background"""
    global ai_proxy_process
    log("Starting AI Proxy...")

    # Проверяем существование файлов
    if not NPM_EXE.exists():
        log(f"ERROR: npm.cmd not found at {NPM_EXE}")
        log(f"NODE_DIR contents: {list(NODE_DIR.iterdir()) if NODE_DIR.exists() else 'DIR NOT FOUND'}")
        return

    if not AI_PROXY_DIR.exists():
        log(f"ERROR: AI Proxy dir not found at {AI_PROXY_DIR}")
        return

    log(f"Using npm: {NPM_EXE}")
    log(f"Working dir: {AI_PROXY_DIR}")

    if sys.platform == 'win32':
        # На Windows нужно использовать shell=True для .cmd файлов
        ai_proxy_process = subprocess.Popen(
            f'"{str(NPM_EXE)}" run start',
            cwd=str(AI_PROXY_DIR),
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
    else:
        ai_proxy_process = subprocess.Popen(
            [str(NPM_EXE), "run", "start"],
            cwd=str(AI_PROXY_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    # Wait a bit for server to start
    time.sleep(5)
    log("AI Proxy started on port 3000")


def stop_ai_proxy():
    """Stop AI Proxy"""
    global ai_proxy_process
    if ai_proxy_process:
        try:
            ai_proxy_process.terminate()
            ai_proxy_process.wait(timeout=5)
        except:
            try:
                ai_proxy_process.kill()
            except:
                pass
        log("AI Proxy stopped")


def run_app() -> int:
    global bot_process
    main_py = APP_DIR / "main.py"
    log(f"Launching {main_py}")

    # Start AI Proxy first
    start_ai_proxy()

    # Start bot
    if sys.platform == 'win32':
        bot_process = subprocess.Popen(
            [str(PY_EXE), str(main_py)],
            creationflags=0x08000000
        )
    else:
        bot_process = subprocess.Popen([str(PY_EXE), str(main_py)])

    # Wait for bot to finish
    try:
        return bot_process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        stop_ai_proxy()


def main() -> int:
    log("=" * 50)
    log("Ninja Launcher Starting")
    log("=" * 50)

    if not MARK.exists() or not PY_EXE.exists():
        try:
            first_run()
        except Exception as e:
            log(f"FATAL: {e}")
            return 1
    else:
        update_app()

    return run_app()


if __name__ == "__main__":
    sys.exit(main())
