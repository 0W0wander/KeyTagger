
# KeyTagger

Lightweight media tagger with a SQLite backend and a Streamlit UI. Scan folders, generate thumbnails, and tag images/videos quickly.

## Features

- Scan a folder recursively and index images and videos
- Compute perceptual hashes (pHash) for images and generate thumbnails
- Store media metadata and tags in SQLite
- Filter by filename and required tags; assign tags inline
- Optional desktop window via PyWebview

## Quickstart (Linux/macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
streamlit run app.py
```

### Desktop Window

Run Streamlit in a native window instead of a browser tab:

```bash
python desktop.py
```

## Quickstart (Windows via WSL)

If `python3 -m venv` fails with ensurepip missing, install:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential
```

Then:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
python3 desktop.py  # or: streamlit run app.py
```

## Package a Windows EXE (optional)

- Run in Windows PowerShell (not WSL). Make sure Python and dependencies are installed in Windows:

```powershell
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m pip install pyinstaller
./build-windows.ps1
```

The binary will be created at `dist/KeyTagger/KeyTagger.exe`.

## Usage

1. Open the app (via `streamlit run app.py` or `python desktop.py`).
2. In the sidebar, click "Pick Folder" and choose a root folder to scan.
3. Click "Scan Folder". The app will index supported images/videos and build thumbnails.
4. Use "Search filename contains" and "Required tags" to filter results.
5. Add tags inline using the `+` control on each card. Tags are stored in SQLite.
6. Click "View" on a card to preview the media or thumbnail.

Notes:
- The database file is `keytag.sqlite` in the project directory.
- Thumbnails are saved under `thumbnails/` by default; the UI also builds square thumbnails for uniform grids.
- The last selected root directory is remembered in `keytag_config.json` (not tracked in git).
