"""
Ninja Launcher (compiled to ninja.exe)
--------------------------------------
A tiny bootstrapper.  On first run it:

    1. Creates  %LOCALAPPDATA%\\Ninja
    2. Downloads embeddable Python (3.11)
    3. Downloads Tkinter from standard Python distribution
    4. Enables `site` + bootstraps `pip`
    5. Downloads main.py + requirements.txt from this GitHub repo
    6. `pip install -r requirements.txt`
    7. Launches main.py

On every later run it just launches main.py with the local Python.
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

# --------------------------------------------------------------------------- config
APP_NAME = "Ninja"
PY_VERSION = "3.11.9"
PY_EMBED_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
PY_FULL_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-amd64.exe"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# Where main.py + requirements.txt live in the GitHub repo.
RAW_BASE = os.environ.get(
    "NINJA_RAW_BASE",
    "https://raw.githubusercontent.com/FreedoomForm/ninja/main/app",
)
FILES_TO_FETCH = ["main.py", "requirements.txt"]

# --------------------------------------------------------------------------- paths
APPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
ROOT = APPDATA / APP_NAME
PY_DIR = ROOT / "python"
APP_DIR = ROOT / "app"
PY_EXE = PY_DIR / "python.exe"
MARK = ROOT / ".installed"


def log(msg: str) -> None:
    print(f"[ninja] {msg}", flush=True)


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
    log("Installing embedded Python…")
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
    log("Bootstrapping pip…")
    subprocess.check_call([str(PY_EXE), str(getpip)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    getpip.unlink(missing_ok=True)


def install_tkinter() -> None:
    """Install Tkinter from standard Python distribution."""
    log("Installing Tkinter for GUI…")
    
    # Download full Python installer (it's a zip file)
    temp_exe = ROOT / "python-installer.exe"
    download(PY_FULL_URL, temp_exe)
    
    # Extract tkinter files from the installer
    # The installer is a zip file with a .exe wrapper
    try:
        with zipfile.ZipFile(temp_exe, 'r') as zf:
            # List of files we need for tkinter
            tk_files = []
            for name in zf.namelist():
                if 'tcl/' in name.lower() or 'tkinter' in name.lower() or '_tkinter' in name.lower():
                    tk_files.append(name)
                if 'tcltk' in name.lower():
                    tk_files.append(name)
            
            # Extract tkinter files
            for name in tk_files:
                try:
                    # Remove the leading directory (core._ or similar)
                    parts = name.split('/')
                    if len(parts) > 1:
                        # Reconstruct path without the prefix
                        if parts[0].startswith('core'):
                            # This is from the installer format
                            target_name = '/'.join(parts[1:])
                        else:
                            target_name = name
                        
                        # Extract to python directory
                        target_path = PY_DIR / target_name
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        with zf.open(name) as src, open(target_path, 'wb') as dst:
                            dst.write(src.read())
                except Exception:
                    pass
    except zipfile.BadZipFile:
        log("Warning: Could not extract tkinter from installer, trying alternate method…")
    finally:
        temp_exe.unlink(missing_ok=True)
    
    # Try alternate method: download tkinter wheels
    log("Installing tkinter via pip…")
    try:
        # Install tk via pip (for Windows)
        subprocess.call(
            [str(PY_EXE), "-m", "pip", "install", "tk", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def fetch_app() -> None:
    log("Fetching app sources…")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # Add timestamp to bypass GitHub CDN cache
    cache_buster = int(time.time())
    for name in FILES_TO_FETCH:
        download(f"{RAW_BASE}/{name}?t={cache_buster}", APP_DIR / name)


def pip_install() -> None:
    log("Installing Python dependencies…")
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
    )


def first_run() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    install_python()
    install_tkinter()
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
        log(f"(could not refresh sources: {e}) — using local copy")


def run_app() -> int:
    main_py = APP_DIR / "main.py"
    log(f"Launching {main_py}")
    env = os.environ.copy()
    
    # Set TCL library path for tkinter
    tcl_dir = PY_DIR / "tcl"
    if tcl_dir.exists():
        env["TCL_LIBRARY"] = str(tcl_dir / "tcl8.6")
        env["TK_LIBRARY"] = str(tcl_dir / "tk8.6")
    
    result = subprocess.call([str(PY_EXE), str(main_py)], env=env)
    
    # If error, pause to show message
    if result != 0:
        input("\nPress Enter to exit…")
    
    return result


def main() -> int:
    print("=" * 60)
    print(" Ninja Telegram Auto-Reply ")
    print("=" * 60)
    if not MARK.exists() or not PY_EXE.exists():
        try:
            first_run()
        except Exception as e:
            log(f"FATAL: install failed: {e}")
            input("Press Enter to exit…")
            return 1
    else:
        update_app_quietly()
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
