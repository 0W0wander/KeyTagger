# KeyTagger C++ 

A high-performance media tagging application written in C++17 with Qt6.

This is a complete rewrite of the Python/Tkinter KeyTagger application, designed to handle 
thousands of media files efficiently using Qt's model/view architecture with virtual scrolling.

## Features

- **High-Performance Gallery View**: Uses `QListView` with custom delegate for smooth scrolling 
  with 1000+ items (solving the 500+ widget limitation of Tkinter)
- **Async Thumbnail Loading**: Background thumbnail generation inspired by digiKam's approach
- **Multiple View Modes**:
  - Gallery Mode: Browse all media in a grid
  - Viewing Mode: Gallery with large preview panel
  - Tagging Mode: Full-screen media with tag input and keyboard navigation
- **Hotkey System**: Configure keyboard shortcuts for rapid tagging
- **SQLite Database**: Fast queries with indexed tags
- **Media Support**: Images (JPG, PNG, WebP, GIF), Videos (MP4, MKV, MOV), Audio (MP3, M4A)
- **Dark/Light Theme**: Toggle between themes

## Requirements

- CMake 3.20+
- Qt 6.2+ (Core, Gui, Widgets, Sql, Multimedia, MultimediaWidgets, Concurrent)
- OpenCV 4.x (core, imgproc, imgcodecs, videoio)
- C++17 compatible compiler

### Windows (MSVC)

1. Install Qt 6 from https://www.qt.io/download
2. Install OpenCV via vcpkg or download binaries
3. Set Qt6_DIR and OpenCV_DIR environment variables

### Linux (Ubuntu/Debian)

```bash
sudo apt install qt6-base-dev qt6-multimedia-dev libopencv-dev cmake build-essential
```

## Building

```bash
cd cpp
mkdir build
cd build

# Configure
cmake .. -DCMAKE_PREFIX_PATH="/path/to/Qt/6.x/gcc_64"

# Build
cmake --build . --config Release

# Run
./KeyTagger
```

### Windows with Visual Studio

```powershell
cd cpp
mkdir build
cd build

# Configure (adjust paths as needed)
cmake .. -G "Visual Studio 17 2022" -A x64 `
    -DCMAKE_PREFIX_PATH="C:/Qt/6.5.0/msvc2019_64" `
    -DOpenCV_DIR="C:/opencv/build"

# Build
cmake --build . --config Release

# Run
.\Release\KeyTagger.exe
```

## Project Structure

```
cpp/
├── CMakeLists.txt          # Build configuration
├── src/
│   ├── main.cpp            # Application entry point
│   ├── core/               # Core business logic
│   │   ├── Database.h/cpp  # SQLite database operations
│   │   ├── Scanner.h/cpp   # Directory scanning & metadata extraction
│   │   ├── ThumbnailCache.h/cpp  # Async thumbnail loading
│   │   ├── Config.h/cpp    # Configuration management
│   │   └── MediaRecord.h/cpp # Data structures
│   └── ui/                 # User interface
│       ├── MainWindow.h/cpp    # Main application window
│       ├── GalleryView.h/cpp   # Thumbnail grid (QListView)
│       ├── GalleryModel.h/cpp  # Data model for gallery
│       ├── GalleryDelegate.h/cpp # Custom item painting
│       ├── Sidebar.h/cpp       # Left panel controls
│       ├── MediaViewer.h/cpp   # Full-size media display
│       ├── TagWidget.h/cpp     # Tag badge display
│       ├── TagInputWidget.h/cpp # Tag input with autocomplete
│       └── HotkeyManager.h/cpp # Keyboard shortcut handling
└── resources/
    └── resources.qrc       # Qt resource file
```

## Architecture Notes

### Virtual Scrolling (The Key Performance Improvement)

The original Tkinter app created a widget for each thumbnail, causing performance issues 
with 500+ items. This C++ version uses Qt's model/view architecture:

- `GalleryModel`: Holds all media data, only provides data when requested
- `GalleryView` (QListView): Only creates visual elements for visible items
- `GalleryDelegate`: Custom painting for each visible item
- `ThumbnailCache`: Async loading with LRU cache

### Thumbnail Loading (Inspired by digiKam)

- Thumbnails are loaded on-demand as items become visible
- Background thread pool handles loading
- LRU cache prevents memory bloat
- Placeholder images shown during loading
- Fast scrolling cancels pending loads to prevent backlog

### Database Compatibility

Uses the same SQLite schema as the Python version, so you can switch between versions
without losing data.

## Usage

1. **Pick Folder**: Select a directory containing media files
2. **Scan Folder**: Index all media and generate thumbnails
3. **Browse**: Click items to select, double-click to view
4. **Tag**: 
   - Use hotkeys (configure in Tags & Hotkeys tab)
   - Or enter Tagging Mode for sequential tagging with keyboard
5. **Filter**: Click tag checkboxes in sidebar to filter

## Keyboard Shortcuts

- `Ctrl+O`: Pick folder
- `Ctrl+A`: Select all
- `Escape`: Clear selection
- `Enter`: View selected item
- `A/D` (in Tagging Mode): Navigate previous/next
- Custom hotkeys: Configure in sidebar

## License

MIT License - See LICENSE file

