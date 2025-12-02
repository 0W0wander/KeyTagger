#pragma once

#include <QMainWindow>
#include <memory>

class QSplitter;
class QProgressDialog;
class QSlider;
class QLabel;

namespace KeyTagger {

class Database;
class Scanner;
class ThumbnailCache;
class GalleryView;
class GalleryModel;
class Sidebar;
class MediaViewer;
class TagWidget;
class TagInputWidget;
class HotkeyManager;
struct ScanResult;

/**
 * MainWindow - Main application window
 * 
 * Manages:
 * - Gallery mode (default): Grid of thumbnails
 * - Viewing mode: Gallery + large preview
 * - Tagging mode: Single image + tag input + navigation
 */
class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget* parent = nullptr);
    ~MainWindow();

protected:
    void closeEvent(QCloseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;

private slots:
    void onPickFolder();
    void onScanFolder();
    void onScanProgress(int current, int total, const QString& file);
    void onScanFinished(ScanResult result);
    void openSettings();
    void openDatabaseFolder();
    void toggleDarkMode();
    
    void onViewingModeToggled(bool enabled);
    void onTaggingModeToggled(bool enabled);
    
    void onMediaSelected(qint64 mediaId);
    void onMediaActivated(qint64 mediaId);
    void onContextMenuRequested(qint64 mediaId, const QPoint& globalPos);
    
    void onThumbnailSizeChanged(int size);
    void onFilterChanged();
    
    void onTagSubmitted(const QString& tag);
    void onHotkeyPressed(const QString& tag);
    void onNavigatePrev();
    void onNavigateNext();
    
    void applyTagToSelection(const QString& tag);
    void removeTagFromSelection(const QString& tag);
    void updateCurrentMediaTags();

private:
    void setupUi();
    void setupConnections();
    void loadSettings();
    void saveSettings();
    void applyTheme();
    void refreshGallery();
    void updateViewerMedia();
    void showMedia(qint64 mediaId);
    void navigateToIndex(int index);
    int currentMediaIndex() const;
    void showToast(const QString& message);

    // Core components
    std::unique_ptr<Database> m_db;
    std::unique_ptr<Scanner> m_scanner;
    std::unique_ptr<ThumbnailCache> m_thumbnailCache;
    
    // UI components
    QSplitter* m_mainSplitter = nullptr;
    QSplitter* m_viewerSplitter = nullptr;
    Sidebar* m_sidebar = nullptr;
    GalleryView* m_galleryView = nullptr;
    GalleryModel* m_galleryModel = nullptr;
    MediaViewer* m_mediaViewer = nullptr;
    TagWidget* m_tagWidget = nullptr;
    TagInputWidget* m_tagInput = nullptr;
    HotkeyManager* m_hotkeyManager = nullptr;
    
    // Viewer controls
    QWidget* m_viewerContainer = nullptr;
    QWidget* m_videoControls = nullptr;
    QPushButton* m_playPauseBtn = nullptr;
    QSlider* m_seekSlider = nullptr;
    QLabel* m_timeLabel = nullptr;
    
    // Progress dialog for scanning
    QProgressDialog* m_progressDialog = nullptr;
    
    // State
    bool m_darkMode = true;
    bool m_viewingMode = false;
    bool m_taggingMode = false;
    qint64 m_currentMediaId = 0;
};

} // namespace KeyTagger

