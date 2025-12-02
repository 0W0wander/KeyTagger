cmake_minimum_required(VERSION 3.20)
project(KeyTagger VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# Find Qt6 packages
find_package(Qt6 REQUIRED COMPONENTS
    Core
    Gui
    Widgets
    Sql
    Multimedia
    MultimediaWidgets
    Concurrent
)

# Find OpenCV for image processing and video thumbnails
find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs videoio)

# Source files
set(SOURCES
    src/main.cpp
    src/core/Database.cpp
    src/core/Scanner.cpp
    src/core/ThumbnailCache.cpp
    src/core/Config.cpp
    src/core/MediaRecord.cpp
    src/ui/MainWindow.cpp
    src/ui/GalleryView.cpp
    src/ui/GalleryModel.cpp
    src/ui/GalleryDelegate.cpp
    src/ui/Sidebar.cpp
    src/ui/MediaViewer.cpp
    src/ui/TagWidget.cpp
    src/ui/HotkeyManager.cpp
    src/ui/TagInputWidget.cpp
)

set(HEADERS
    src/core/Database.h
    src/core/Scanner.h
    src/core/ThumbnailCache.h
    src/core/Config.h
    src/core/MediaRecord.h
    src/ui/MainWindow.h
    src/ui/GalleryView.h
    src/ui/GalleryModel.h
    src/ui/GalleryDelegate.h
    src/ui/Sidebar.h
    src/ui/MediaViewer.h
    src/ui/TagWidget.h
    src/ui/HotkeyManager.h
    src/ui/TagInputWidget.h
)

# Resources
set(RESOURCES
    resources/resources.qrc
)

# Create executable
add_executable(${PROJECT_NAME}
    ${SOURCES}
    ${HEADERS}
    ${RESOURCES}
)

# Link libraries
target_link_libraries(${PROJECT_NAME} PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    Qt6::Sql
    Qt6::Multimedia
    Qt6::MultimediaWidgets
    Qt6::Concurrent
    ${OpenCV_LIBS}
)

# Include directories
target_include_directories(${PROJECT_NAME} PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/core
    ${CMAKE_CURRENT_SOURCE_DIR}/src/ui
    ${OpenCV_INCLUDE_DIRS}
)

# Windows-specific settings
if(WIN32)
    set_target_properties(${PROJECT_NAME} PROPERTIES
        WIN32_EXECUTABLE TRUE
    )
    # Copy Qt DLLs to output directory
    add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:Qt6::Core>
            $<TARGET_FILE:Qt6::Gui>
            $<TARGET_FILE:Qt6::Widgets>
            $<TARGET_FILE:Qt6::Sql>
            $<TARGET_FILE:Qt6::Multimedia>
            $<TARGET_FILE:Qt6::MultimediaWidgets>
            $<TARGET_FILE:Qt6::Concurrent>
            $<TARGET_FILE_DIR:${PROJECT_NAME}>
    )
endif()

# Install rules
install(TARGETS ${PROJECT_NAME}
    RUNTIME DESTINATION bin
)

