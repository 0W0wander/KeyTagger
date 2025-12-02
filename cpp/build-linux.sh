#!/bin/bash

# KeyTagger C++ Linux Build Script

set -e

echo "=== KeyTagger C++ Build Script ==="

# Default paths (adjust for your system)
QT_DIR="${QT_DIR:-/usr/lib/qt6}"
BUILD_TYPE="${BUILD_TYPE:-Release}"

# Check for Qt
if ! command -v qmake6 &> /dev/null && ! command -v qmake &> /dev/null; then
    echo "Error: Qt6 not found. Install with:"
    echo "  Ubuntu/Debian: sudo apt install qt6-base-dev qt6-multimedia-dev"
    echo "  Arch: sudo pacman -S qt6-base qt6-multimedia"
    exit 1
fi

echo "Qt found!"

# Check for OpenCV
if ! pkg-config --exists opencv4; then
    echo "Warning: OpenCV4 not found via pkg-config"
    echo "Scanner functionality may not work"
    echo "Install with: sudo apt install libopencv-dev"
fi

# Create build directory
mkdir -p build
cd build

# Configure
echo ""
echo "Configuring with CMake..."

cmake .. \
    -DCMAKE_BUILD_TYPE=$BUILD_TYPE \
    -DCMAKE_PREFIX_PATH="$QT_DIR"

# Build
echo ""
echo "Building $BUILD_TYPE..."

cmake --build . --config $BUILD_TYPE --parallel $(nproc)

echo ""
echo "=== Build Complete! ==="
echo "Executable: $(pwd)/KeyTagger"
echo ""
echo "To run:"
echo "  ./KeyTagger"

