"""
Ninja Launcher (компилируется в ninja.exe)
------------------------------------------
Скачивает Python, устанавливает зависимости, запускает бота.
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
PY_EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"

RAW_BASE = os.environ.get(
    "NINJA_RAW_BASE",
    "https://raw.githubusercontent.com/FreedoomForm/ninja/main/app",
)
FILES_TO_FETCH = ["main.py", "requirements.txt"]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
ROOT = APPDATA / APP_NAME
PY_DIR = ROOT / "python"
APP_DIR = ROOT / "app"
WEB_DIR = APP_DIR / "web"
PY_EXE = PY_DIR / "python.exe"
MARK = ROOT / ".installed"
LOG_FILE = ROOT / "launcher.log"


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


def fetch_app() -> None:
    log("Fetching app files...")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(exist_ok=True)
    
    cache_buster = int(time.time())
    
    for name in FILES_TO_FETCH:
        download(f"{RAW_BASE}/{name}?t={cache_buster}", APP_DIR / name)
    
    download(f"{RAW_BASE}/web/index.html?t={cache_buster}", WEB_DIR / "index.html")


def pip_install() -> bool:
    log("Installing dependencies...")
    
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


def first_run() -> bool:
    ROOT.mkdir(parents=True, exist_ok=True)
    install_python()
    fetch_app()
    if not pip_install():
        log("WARNING: pip install had issues, continuing anyway...")
    MARK.write_text("ok")
    log("Installation complete")
    return True


def update_app() -> None:
    try:
        fetch_app()
        pip_install()
    except Exception as e:
        log(f"Update failed: {e}")


def run_app() -> int:
    main_py = APP_DIR / "main.py"
    log(f"Launching {main_py}")
    
    # CREATE_NO_WINDOW = 0x08000000
    if sys.platform == 'win32':
        return subprocess.call(
            [str(PY_EXE), str(main_py)],
            creationflags=0x08000000
        )
    else:
        return subprocess.call([str(PY_EXE), str(main_py)])


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
