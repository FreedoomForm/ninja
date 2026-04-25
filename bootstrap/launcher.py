"""
Ninja Launcher (compiled to ninja.exe)
--------------------------------------
Downloads embedded Python, installs dependencies, and launches the app.
Hides console window on Windows.
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

# Try to hide console window on Windows
if sys.platform == 'win32':
    try:
        import ctypes
        console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if console_hwnd:
            ctypes.windll.user32.ShowWindow(console_hwnd, 0)  # SW_HIDE
    except:
        pass

# ---------------------------------------------------------------------------
# config
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
# paths
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

    for pth in PY_DIR.glob("python*._pth"):
        text = pth.read_text()
        text = text.replace("#import site", "import site")
        pth.write_text(text)

    getpip = ROOT / "get-pip.py"
    download(GETPIP_URL, getpip)
    log("Bootstrapping pip...")
    subprocess.check_call(
        [str(PY_EXE), str(getpip)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    getpip.unlink(missing_ok=True)
    
    # Download pythonw.exe from full Python to hide console
    # Note: embedded Python doesn't include pythonw.exe
    # We'll use subprocess.CREATE_NO_WINDOW instead
    log("Python installation complete")


def fetch_app() -> None:
    log("Fetching app sources...")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    WEB_DIR.mkdir(exist_ok=True)
    
    cache_buster = int(time.time())
    
    # Download main files
    for name in FILES_TO_FETCH:
        download(f"{RAW_BASE}/{name}?t={cache_buster}", APP_DIR / name)
    
    # Download web files
    download(f"{RAW_BASE}/web/index.html?t={cache_buster}", WEB_DIR / "index.html")


def pip_install() -> None:
    log("Installing Python dependencies...")
    subprocess.check_call(
        [
            str(PY_EXE),
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "-r",
            str(APP_DIR / "requirements.txt"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def first_run() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    install_python()
    fetch_app()
    pip_install()
    MARK.write_text("ok")
    log("Install complete ✓")


def update_app_quietly() -> None:
    try:
        fetch_app()
        pip_install()
    except Exception as e:
        log(f"Could not refresh sources: {e}")


def run_app() -> int:
    main_py = APP_DIR / "main.py"
    log(f"Launching {main_py}")
    
    # Use CREATE_NO_WINDOW to hide console (works with embedded Python)
    # 0x08000000 = CREATE_NO_WINDOW
    if sys.platform == 'win32':
        result = subprocess.call(
            [str(PY_EXE), str(main_py)],
            creationflags=0x08000000
        )
    else:
        result = subprocess.call([str(PY_EXE), str(main_py)])
    
    return result


def main() -> int:
    log("=" * 50)
    log("Ninja Launcher Starting")
    log("=" * 50)
    
    if not MARK.exists() or not PY_EXE.exists():
        try:
            first_run()
        except Exception as e:
            log(f"FATAL: install failed: {e}")
            return 1
    else:
        update_app_quietly()
    
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
