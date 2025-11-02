# KeyTagger

Lightweight media tagger with a SQLite backend and a Tkinter desktop UI. Scan folders, generate thumbnails, and tag images/videos quickly.

## Features

- Scan a folder recursively and index images and videos
- Compute perceptual hashes (pHash) for images and generate thumbnails
- Store media metadata and tags in SQLite
- Filter by filename and required tags; assign tags inline
- Hotkey support with configurable mappings (e.g., `a`, `ctrl+1`, etc.)

## Quickstart (Windows/macOS/Linux)

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

pip install -U pip setuptools wheel
pip install -r requirements.txt
python tkapp.py
```

### TL;DR (Windows quick run)

```powershell
# First time setup (creates venv, installs deps, runs app)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m venv .venv
\.\.venv\Scripts\Activate.ps1
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
python tkapp.py
```

```powershell
# Next time (reuse venv and run)
\.\.venv\Scripts\Activate.ps1
python tkapp.py
```

```powershell
# Build and launch Windows EXE
\.\.venv\Scripts\Activate.ps1
python -m pip install pyinstaller
./build-windows.ps1
Start-Process .\executable\KeyTagger\KeyTagger.exe
```

## Package a Windows EXE (optional)

Run in Windows PowerShell (not WSL):

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
./build-windows.ps1
Start-Process .\executable\KeyTagger\KeyTagger.exe
```

The binary will be created at `executable/KeyTagger/KeyTagger.exe` and the command above will open it.

## Usage

1. Open the app: `python tkapp.py`.
2. Click "Pick Folder" and choose a root folder to scan.
3. Click "Scan Folder". The app will index supported images/videos and build thumbnails.
4. Select items and apply tags; use "Hotkey Settings" to configure key → tag mappings.
5. Tags are written to SQLite and now appear immediately on cards after applying.

Notes:

- The database file is `keytag.sqlite` in the project directory.
- Thumbnails are saved under `thumbnails/` by default; the UI also creates square thumbnails under `thumbnails_square/` for uniform grids.
- The last selected root directory and hotkeys are stored in `keytag_config.json` (not tracked in git).
