# KeyTagger C++ Windows Build Script
# Requires: Qt6, OpenCV, CMake, Visual Studio

param(
    [string]$QtDir = "C:\Qt\6.5.3\msvc2019_64",
    [string]$OpenCVDir = "C:\opencv\build",
    [string]$BuildType = "Release"
)

$ErrorActionPreference = "Stop"

Write-Host "=== KeyTagger C++ Build Script ===" -ForegroundColor Cyan

# Validate Qt installation
if (-not (Test-Path "$QtDir\bin\qmake.exe")) {
    Write-Host "Error: Qt not found at $QtDir" -ForegroundColor Red
    Write-Host "Please set the -QtDir parameter to your Qt installation path" -ForegroundColor Yellow
    Write-Host "Example: .\build-windows.ps1 -QtDir 'C:\Qt\6.5.3\msvc2019_64'" -ForegroundColor Yellow
    exit 1
}

Write-Host "Qt found at: $QtDir" -ForegroundColor Green

# Create build directory
$BuildDir = Join-Path $PSScriptRoot "build"
if (-not (Test-Path $BuildDir)) {
    New-Item -ItemType Directory -Path $BuildDir | Out-Null
}

Set-Location $BuildDir

# Configure with CMake
Write-Host "`nConfiguring with CMake..." -ForegroundColor Yellow

$CMakeArgs = @(
    "..",
    "-G", "Visual Studio 17 2022",
    "-A", "x64",
    "-DCMAKE_PREFIX_PATH=$QtDir",
    "-DCMAKE_BUILD_TYPE=$BuildType"
)

if (Test-Path $OpenCVDir) {
    $CMakeArgs += "-DOpenCV_DIR=$OpenCVDir"
    Write-Host "OpenCV found at: $OpenCVDir" -ForegroundColor Green
} else {
    Write-Host "Warning: OpenCV not found at $OpenCVDir" -ForegroundColor Yellow
    Write-Host "Scanner functionality may not work" -ForegroundColor Yellow
}

cmake @CMakeArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "CMake configuration failed!" -ForegroundColor Red
    exit 1
}

# Build
Write-Host "`nBuilding $BuildType configuration..." -ForegroundColor Yellow

cmake --build . --config $BuildType --parallel

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

# Copy Qt DLLs using windeployqt
Write-Host "`nDeploying Qt dependencies..." -ForegroundColor Yellow

$OutputDir = Join-Path $BuildDir $BuildType
$WinDeployQt = Join-Path $QtDir "bin\windeployqt.exe"
$Executable = Join-Path $OutputDir "KeyTagger.exe"

if (Test-Path $Executable) {
    & $WinDeployQt $Executable --no-translations
} else {
    Write-Host "Warning: Executable not found at $Executable" -ForegroundColor Yellow
}

Write-Host "`n=== Build Complete! ===" -ForegroundColor Green
Write-Host "Executable: $Executable" -ForegroundColor Cyan
Write-Host "`nTo run:" -ForegroundColor White
Write-Host "  cd $OutputDir" -ForegroundColor Gray
Write-Host "  .\KeyTagger.exe" -ForegroundColor Gray

