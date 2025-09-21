# Requires: pip install pyinstaller

$ErrorActionPreference = "Stop"

# Clean
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build

# Build
pyinstaller `
	--name KeyTagger `
	--noconsole `
	--add-data "app.py;." `
	--add-data "keytagger;keytagger" `
	--add-data "requirements.txt;." `
	--hidden-import streamlit `
	--hidden-import PIL `
	--hidden-import imagehash `
	--hidden-import cv2 `
	--hidden-import numpy `
	desktop.py

Write-Host "Build complete. See dist/KeyTagger" -ForegroundColor Green
