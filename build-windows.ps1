# Requires: pip install pyinstaller

$ErrorActionPreference = "Stop"

# Clean
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue executable\KeyTagger

# Build (Tkinter desktop)
pyinstaller `
	--name KeyTagger `
	--noconsole `
	--distpath "executable" `
	--add-data "keytagger;keytagger" `
	--add-data "requirements.txt;." `
	--hidden-import PIL `
	--hidden-import imagehash `
	--hidden-import cv2 `
	--hidden-import numpy `
	tkapp.py

Write-Host "Build complete. See executable/KeyTagger" -ForegroundColor Green
