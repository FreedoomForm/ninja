"""
Ninja Launcher (compiled to ninja.exe)
--------------------------------------
A tiny bootstrapper.  On first run it:

    1. Creates  %LOCALAPPDATA%\\Ninja
    2. Downloads embeddable Python (3.11)
    3. Enables `site` + bootstraps `pip`
    4. Downloads main.py + requirements.txt from this GitHub repo
    5. `pip install -r requirements.txt`
    6. Launches main.py (Native Windows GUI - NO CONSOLE)

On every later run it just launches main.py with the local Python.
"""

import ctypes
import io
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# HIDE CONSOLE IMMEDIATELY
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Hide console window
console_hwnd = kernel32.GetConsoleWindow()
if console_hwnd:
    user32.ShowWindow(console_hwnd, 0)  # SW_HIDE = 0

# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
APP_NAME = "Ninja"
PY_VERSION = "3.11.9"
PY_EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# Where main.py + requirements.txt live in the GitHub repo.
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
PY_EXE = PY_DIR / "python.exe"
MARK = ROOT / ".installed"
LOG_FILE = ROOT / "launcher.log"


def log(msg: str) -> None:
    """Log to file instead of console"""
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
    
    # Download and extract embedded Python
    data = download_bytes(PY_EMBED_URL)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(PY_DIR)

    # The embed distro disables `site` by default. Enable it so pip works.
    for pth in PY_DIR.glob("python*._pth"):
        text = pth.read_text()
        text = text.replace("#import site", "import site")
        pth.write_text(text)

    # Bootstrap pip
    getpip = ROOT / "get-pip.py"
    download(GETPIP_URL, getpip)
    log("Bootstrapping pip...")
    subprocess.check_call(
        [str(PY_EXE), str(getpip)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    getpip.unlink(missing_ok=True)


def fetch_app() -> None:
    log("Fetching app sources...")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # Add timestamp to bypass GitHub CDN cache
    cache_buster = int(time.time())
    for name in FILES_TO_FETCH:
        download(f"{RAW_BASE}/{name}?t={cache_buster}", APP_DIR / name)


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
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def first_run() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    install_python()
    fetch_app()
    pip_install()
    MARK.write_text("ok")
    log("Install complete ✓")


def update_app_quietly() -> None:
    """Always pull fresh main.py / requirements.txt; ignore network errors."""
    try:
        fetch_app()
        # Always run pip install to ensure new dependencies are installed
        pip_install()
    except Exception as e:
        log(f"Could not refresh sources: {e}")


def run_app() -> int:
    main_py = APP_DIR / "main.py"
    log(f"Launching {main_py}")
    
    # Run with CREATE_NO_WINDOW to ensure no console appears
    result = subprocess.call(
        [str(PY_EXE), str(main_py)],
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    
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
