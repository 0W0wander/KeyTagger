# Requires: pip install pyinstaller

$ErrorActionPreference = "Stop"

# Clean
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue executable\KeyTagger

# Build (Tkinter desktop)
pyinstaller `
	--distpath "executable" `
	KeyTagger.spec

Write-Host "Build complete. See executable/KeyTagger" -ForegroundColor Green
