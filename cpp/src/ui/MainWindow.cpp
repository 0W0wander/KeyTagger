#include "MainWindow.h"
#include "Database.h"
#include "Scanner.h"
#include "ThumbnailCache.h"
#include "Config.h"
#include "GalleryView.h"
#include "GalleryModel.h"
#include "Sidebar.h"
#include "MediaViewer.h"
#include "TagWidget.h"
#include "TagInputWidget.h"
#include "HotkeyManager.h"

#include <QSplitter>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QFileDialog>
#include <QMessageBox>
#include <QProgressDialog>
#include <QMenuBar>
#include <QMenu>
#include <QAction>
#include <QSlider>
#include <QPushButton>
#include <QLabel>
#include <QCloseEvent>
#include <QKeyEvent>
#include <QDesktopServices>
#include <QUrl>
#include <QTimer>
#include <QApplication>
#include <QDebug>

namespace KeyTagger {

MainWindow::MainWindow(QWidget* parent)
    : QMainWindow(parent)
{
    setWindowTitle("KeyTagger");
    setMinimumSize(1024, 768);
    
    // Initialize core components
    m_db = std::make_unique<Database>(".");
    m_scanner = std::make_unique<Scanner>(m_db.get());
    m_thumbnailCache = std::make_unique<ThumbnailCache>(500);
    m_hotkeyManager = std::make_unique<HotkeyManager>(this);
    
    // Load configuration
    Config::instance().load();
    m_darkMode = Config::instance().darkMode();
    
    setupUi();
    setupConnections();
    loadSettings();
    applyTheme();
    
    // Initial refresh
    refreshGallery();
}

MainWindow::~MainWindow() {
    saveSettings();
}

void MainWindow::setupUi() {
    // Central widget with main splitter
    QWidget* centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);
    
    QHBoxLayout* mainLayout = new QHBoxLayout(centralWidget);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);
    
    // Sidebar
    m_sidebar = new Sidebar(m_db.get(), this);
    mainLayout->addWidget(m_sidebar);
    
    // Main content splitter (gallery and viewer)
    m_mainSplitter = new QSplitter(Qt::Vertical, this);
    mainLayout->addWidget(m_mainSplitter, 1);
    
    // Gallery
    m_galleryModel = new GalleryModel(m_db.get(), m_thumbnailCache.get(), this);
    m_galleryView = new GalleryView(this);
    m_galleryView->setThumbnailCache(m_thumbnailCache.get());
    m_galleryView->setModel(m_galleryModel);
    m_mainSplitter->addWidget(m_galleryView);
    
    // Viewer container
    m_viewerContainer = new QWidget(this);
    QVBoxLayout* viewerLayout = new QVBoxLayout(m_viewerContainer);
    viewerLayout->setContentsMargins(8, 8, 8, 8);
    viewerLayout->setSpacing(8);
    
    // Tag widget (for tagging mode)
    m_tagWidget = new TagWidget(m_viewerContainer);
    m_tagWidget->hide();
    viewerLayout->addWidget(m_tagWidget);
    
    // Tag input (for tagging mode)
    m_tagInput = new TagInputWidget(m_db.get(), m_viewerContainer);
    m_tagInput->hide();
    viewerLayout->addWidget(m_tagInput);
    
    // Media viewer
    m_mediaViewer = new MediaViewer(m_viewerContainer);
    viewerLayout->addWidget(m_mediaViewer, 1);
    
    // Video controls
    m_videoControls = new QWidget(m_viewerContainer);
    QHBoxLayout* controlsLayout = new QHBoxLayout(m_videoControls);
    controlsLayout->setContentsMargins(0, 0, 0, 0);
    
    m_playPauseBtn = new QPushButton("Pause", m_videoControls);
    m_playPauseBtn->setFixedWidth(80);
    controlsLayout->addWidget(m_playPauseBtn);
    
    m_seekSlider = new QSlider(Qt::Horizontal, m_videoControls);
    controlsLayout->addWidget(m_seekSlider, 1);
    
    m_timeLabel = new QLabel("00:00 / 00:00", m_videoControls);
    controlsLayout->addWidget(m_timeLabel);
    
    m_videoControls->hide();
    viewerLayout->addWidget(m_videoControls);
    
    m_viewerContainer->hide();
    m_mainSplitter->addWidget(m_viewerContainer);
    
    // Menu bar
    QMenuBar* menuBar = new QMenuBar(this);
    setMenuBar(menuBar);
    
    QMenu* fileMenu = menuBar->addMenu("&File");
    fileMenu->addAction("&Pick Folder...", this, &MainWindow::onPickFolder, QKeySequence::Open);
    fileMenu->addAction("&Scan Folder", this, &MainWindow::onScanFolder);
    fileMenu->addSeparator();
    fileMenu->addAction("&Settings...", this, &MainWindow::openSettings);
    fileMenu->addSeparator();
    fileMenu->addAction("E&xit", this, &QMainWindow::close, QKeySequence::Quit);
    
    QMenu* viewMenu = menuBar->addMenu("&View");
    QAction* darkModeAction = viewMenu->addAction("&Dark Mode", this, &MainWindow::toggleDarkMode);
    darkModeAction->setCheckable(true);
    darkModeAction->setChecked(m_darkMode);
    viewMenu->addSeparator();
    viewMenu->addAction("&Viewing Mode", this, [this]() {
        onViewingModeToggled(!m_viewingMode);
    });
    viewMenu->addAction("&Tagging Mode", this, [this]() {
        onTaggingModeToggled(!m_taggingMode);
    });
    
    QMenu* editMenu = menuBar->addMenu("&Edit");
    editMenu->addAction("Select &All", m_galleryView, &GalleryView::selectAll, QKeySequence::SelectAll);
    editMenu->addAction("&Deselect All", m_galleryView, &GalleryView::clearSelection);
    
    // Set initial thumbnail size
    int thumbSize = Config::instance().thumbnailSize();
    m_galleryView->setThumbnailSize(thumbSize);
    m_galleryModel->setThumbnailSize(thumbSize);
}

void MainWindow::setupConnections() {
    // Sidebar
    connect(m_sidebar, &Sidebar::pickFolderClicked, this, &MainWindow::onPickFolder);
    connect(m_sidebar, &Sidebar::scanFolderClicked, this, &MainWindow::onScanFolder);
    connect(m_sidebar, &Sidebar::settingsClicked, this, &MainWindow::openSettings);
    connect(m_sidebar, &Sidebar::openDatabaseFolderClicked, this, &MainWindow::openDatabaseFolder);
    connect(m_sidebar, &Sidebar::viewingModeToggled, this, &MainWindow::onViewingModeToggled);
    connect(m_sidebar, &Sidebar::taggingModeToggled, this, &MainWindow::onTaggingModeToggled);
    connect(m_sidebar, &Sidebar::thumbnailSizeChanged, this, &MainWindow::onThumbnailSizeChanged);
    connect(m_sidebar, &Sidebar::filterChanged, this, &MainWindow::onFilterChanged);
    
    // Gallery
    connect(m_galleryView, &GalleryView::mediaSelected, this, &MainWindow::onMediaSelected);
    connect(m_galleryView, &GalleryView::mediaActivated, this, &MainWindow::onMediaActivated);
    connect(m_galleryView, &GalleryView::contextMenuRequested, this, &MainWindow::onContextMenuRequested);
    
    // Scanner
    connect(m_scanner.get(), &Scanner::scanProgress, this, &MainWindow::onScanProgress);
    connect(m_scanner.get(), &Scanner::scanFinished, this, &MainWindow::onScanFinished);
    
    // Tag input
    connect(m_tagInput, &TagInputWidget::tagSubmitted, this, &MainWindow::onTagSubmitted);
    
    // Hotkey manager
    connect(m_hotkeyManager.get(), &HotkeyManager::hotkeyPressed, this, &MainWindow::onHotkeyPressed);
    connect(m_hotkeyManager.get(), &HotkeyManager::prevPressed, this, &MainWindow::onNavigatePrev);
    connect(m_hotkeyManager.get(), &HotkeyManager::nextPressed, this, &MainWindow::onNavigateNext);
    
    // Video controls
    connect(m_playPauseBtn, &QPushButton::clicked, m_mediaViewer, &MediaViewer::togglePlayPause);
    connect(m_mediaViewer, &MediaViewer::playbackStateChanged, this, [this](bool playing) {
        m_playPauseBtn->setText(playing ? "Pause" : "Play");
    });
    connect(m_mediaViewer, &MediaViewer::positionChanged, this, [this](qint64 pos) {
        if (!m_seekSlider->isSliderDown()) {
            m_seekSlider->setValue(static_cast<int>(pos));
        }
        qint64 dur = m_mediaViewer->duration();
        int posSec = static_cast<int>(pos / 1000);
        int durSec = static_cast<int>(dur / 1000);
        m_timeLabel->setText(QString("%1:%2 / %3:%4")
            .arg(posSec / 60, 2, 10, QChar('0'))
            .arg(posSec % 60, 2, 10, QChar('0'))
            .arg(durSec / 60, 2, 10, QChar('0'))
            .arg(durSec % 60, 2, 10, QChar('0')));
    });
    connect(m_mediaViewer, &MediaViewer::durationChanged, this, [this](qint64 dur) {
        m_seekSlider->setMaximum(static_cast<int>(dur));
    });
    connect(m_seekSlider, &QSlider::sliderMoved, this, [this](int value) {
        m_mediaViewer->seek(value);
    });
    
    // Config changes
    connect(&Config::instance(), &Config::hotkeysChanged, this, [this]() {
        m_hotkeyManager->setHotkeys(Config::instance().hotkeys());
    });
    
    // Initialize hotkey manager
    m_hotkeyManager->setHotkeys(Config::instance().hotkeys());
    m_hotkeyManager->setTaggingNavKeys(
        Config::instance().taggingPrevKey(),
        Config::instance().taggingNextKey()
    );
}

void MainWindow::loadSettings() {
    QString lastDir = Config::instance().lastRootDir();
    if (!lastDir.isEmpty()) {
        m_sidebar->setCurrentFolder(lastDir);
        m_galleryModel->setRootDir(lastDir);
    }
    
    QByteArray geometry = Config::instance().windowGeometry();
    if (!geometry.isEmpty()) {
        restoreGeometry(geometry);
    }
    
    QByteArray state = Config::instance().windowState();
    if (!state.isEmpty()) {
        restoreState(state);
    }
}

void MainWindow::saveSettings() {
    Config::instance().setWindowGeometry(saveGeometry());
    Config::instance().setWindowState(saveState());
    Config::instance().save();
}

void MainWindow::applyTheme() {
    m_galleryView->setDarkMode(m_darkMode);
    m_sidebar->setDarkMode(m_darkMode);
    m_mediaViewer->setDarkMode(m_darkMode);
    m_tagWidget->setDarkMode(m_darkMode);
    m_tagInput->setDarkMode(m_darkMode);
    
    // Apply to main window
    if (m_darkMode) {
        setStyleSheet(R"(
            QMainWindow {
                background-color: #0f172a;
            }
            QMenuBar {
                background-color: #111827;
                color: #f3f4f6;
            }
            QMenuBar::item:selected {
                background-color: #374151;
            }
            QMenu {
                background-color: #1f2937;
                color: #f3f4f6;
                border: 1px solid #374151;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
            }
            QSplitter::handle {
                background-color: #374151;
            }
            QScrollBar:vertical {
                background: #020617;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background: #1f2937;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #374151;
            }
            QScrollBar:horizontal {
                background: #020617;
                height: 12px;
            }
            QScrollBar::handle:horizontal {
                background: #1f2937;
                border-radius: 6px;
            }
            QProgressDialog {
                background-color: #1f2937;
                color: #f3f4f6;
            }
        )");
    } else {
        setStyleSheet(R"(
            QMainWindow {
                background-color: #f6f7fb;
            }
            QMenuBar {
                background-color: #ffffff;
                color: #111827;
            }
            QMenu {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
            }
            QMenu::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
            QSplitter::handle {
                background-color: #e5e7eb;
            }
        )");
    }
}

void MainWindow::closeEvent(QCloseEvent* event) {
    saveSettings();
    event->accept();
}

void MainWindow::keyPressEvent(QKeyEvent* event) {
    // Don't process hotkeys when typing in tag input
    if (m_tagInput->hasFocus()) {
        QMainWindow::keyPressEvent(event);
        return;
    }
    
    // Process through hotkey manager
    if (m_hotkeyManager->processKeyEvent(
            static_cast<Qt::Key>(event->key()), 
            event->modifiers())) {
        event->accept();
        return;
    }
    
    QMainWindow::keyPressEvent(event);
}

void MainWindow::onPickFolder() {
    QString dir = QFileDialog::getExistingDirectory(
        this, "Select Media Folder", m_sidebar->currentFolder());
    
    if (!dir.isEmpty()) {
        m_sidebar->setCurrentFolder(dir);
        Config::instance().setLastRootDir(dir);
        Config::instance().save();
        
        m_galleryModel->setRootDir(dir);
    }
}

void MainWindow::onScanFolder() {
    QString folder = m_sidebar->currentFolder();
    if (folder.isEmpty()) {
        onPickFolder();
        folder = m_sidebar->currentFolder();
        if (folder.isEmpty()) return;
    }
    
    m_progressDialog = new QProgressDialog("Scanning...", "Cancel", 0, 100, this);
    m_progressDialog->setWindowModality(Qt::WindowModal);
    m_progressDialog->setAutoClose(true);
    m_progressDialog->setMinimumDuration(0);
    
    connect(m_progressDialog, &QProgressDialog::canceled, m_scanner.get(), &Scanner::cancel);
    
    QString thumbDir = QDir(folder).filePath("thumbnails");
    m_scanner->scanDirectory(folder, thumbDir);
}

void MainWindow::onScanProgress(int current, int total, const QString& file) {
    if (m_progressDialog) {
        m_progressDialog->setMaximum(total);
        m_progressDialog->setValue(current);
        m_progressDialog->setLabelText(QString("Scanning %1/%2\n%3")
            .arg(current).arg(total).arg(QFileInfo(file).fileName()));
    }
}

void MainWindow::onScanFinished(ScanResult result) {
    if (m_progressDialog) {
        m_progressDialog->close();
        m_progressDialog->deleteLater();
        m_progressDialog = nullptr;
    }
    
    refreshGallery();
    m_sidebar->refreshTags();
    
    showToast(QString("Scan complete: %1 scanned, %2 added/updated, %3 errors")
        .arg(result.scanned).arg(result.addedOrUpdated).arg(result.errors));
}

void MainWindow::openSettings() {
    // TODO: Settings dialog
    QMessageBox::information(this, "Settings", 
        "Settings dialog not yet implemented.\n\n"
        "Configure hotkeys in the Tags & Hotkeys tab in the sidebar.");
}

void MainWindow::openDatabaseFolder() {
    QDesktopServices::openUrl(QUrl::fromLocalFile(QDir::currentPath()));
}

void MainWindow::toggleDarkMode() {
    m_darkMode = !m_darkMode;
    Config::instance().setDarkMode(m_darkMode);
    Config::instance().save();
    applyTheme();
}

void MainWindow::onViewingModeToggled(bool enabled) {
    m_viewingMode = enabled;
    
    if (m_taggingMode && enabled) {
        m_taggingMode = false;
        m_tagWidget->hide();
        m_tagInput->hide();
    }
    
    if (enabled) {
        m_viewerContainer->show();
        m_mainSplitter->setSizes({height() * 2 / 3, height() / 3});
        updateViewerMedia();
    } else {
        m_viewerContainer->hide();
        m_mediaViewer->clear();
    }
}

void MainWindow::onTaggingModeToggled(bool enabled) {
    m_taggingMode = enabled;
    
    if (m_viewingMode && enabled) {
        m_viewingMode = false;
    }
    
    if (enabled) {
        m_viewerContainer->show();
        m_tagWidget->show();
        m_tagInput->show();
        m_mainSplitter->setSizes({height() / 4, height() * 3 / 4});
        updateViewerMedia();
        m_tagInput->setFocus();
    } else {
        m_tagWidget->hide();
        m_tagInput->hide();
        if (!m_viewingMode) {
            m_viewerContainer->hide();
        }
    }
}

void MainWindow::onMediaSelected(qint64 mediaId) {
    m_currentMediaId = mediaId;
    
    if (m_viewingMode || m_taggingMode) {
        updateViewerMedia();
    }
}

void MainWindow::onMediaActivated(qint64 mediaId) {
    if (!m_viewingMode && !m_taggingMode) {
        onViewingModeToggled(true);
    }
    
    showMedia(mediaId);
}

void MainWindow::onContextMenuRequested(qint64 mediaId, const QPoint& globalPos) {
    QMenu menu;
    
    auto record = m_galleryModel->getRecord(mediaId);
    if (!record.has_value()) return;
    
    menu.addAction("Open File", this, [this, record]() {
        QDesktopServices::openUrl(QUrl::fromLocalFile(record->filePath));
    });
    
    menu.addAction("Open Folder", this, [this, record]() {
        QDesktopServices::openUrl(QUrl::fromLocalFile(
            QFileInfo(record->filePath).absolutePath()));
    });
    
    menu.addSeparator();
    
    // Tag submenu
    QMenu* tagMenu = menu.addMenu("Add Tag");
    QStringList allTags = m_db->allTags();
    QStringList currentTags = m_db->getMediaTags(mediaId);
    
    for (const QString& tag : allTags) {
        QAction* action = tagMenu->addAction(tag);
        action->setCheckable(true);
        action->setChecked(currentTags.contains(tag));
        connect(action, &QAction::triggered, this, [this, tag, mediaId](bool checked) {
            if (checked) {
                m_db->addMediaTags(mediaId, {tag});
            } else {
                m_db->removeMediaTags(mediaId, {tag});
            }
            m_galleryModel->onTagsChanged();
            if (m_currentMediaId == mediaId) {
                updateCurrentMediaTags();
            }
        });
    }
    
    menu.addSeparator();
    
    menu.addAction("Delete from Database", this, [this, mediaId, record]() {
        int result = QMessageBox::question(this, "Delete",
            QString("Remove '%1' from database?\n\n"
                    "The file will not be deleted from disk.")
                .arg(record->fileName));
        if (result == QMessageBox::Yes) {
            m_db->deleteMedia(record->filePath);
            refreshGallery();
        }
    });
    
    menu.exec(globalPos);
}

void MainWindow::onThumbnailSizeChanged(int size) {
    m_galleryView->setThumbnailSize(size);
    m_galleryModel->setThumbnailSize(size);
}

void MainWindow::onFilterChanged() {
    QStringList tags = m_sidebar->selectedFilterTags().values();
    QString search; // TODO: Add search box
    
    m_galleryModel->setFilter(tags, search, false);
}

void MainWindow::onTagSubmitted(const QString& tag) {
    applyTagToSelection(tag);
    
    // In tagging mode, auto-advance to next
    if (m_taggingMode) {
        onNavigateNext();
    }
}

void MainWindow::onHotkeyPressed(const QString& tag) {
    applyTagToSelection(tag);
    showToast(QString("Tagged: %1").arg(tag));
    
    // In tagging mode, auto-advance
    if (m_taggingMode) {
        onNavigateNext();
    }
}

void MainWindow::onNavigatePrev() {
    int index = currentMediaIndex();
    if (index > 0) {
        navigateToIndex(index - 1);
    }
}

void MainWindow::onNavigateNext() {
    int index = currentMediaIndex();
    if (index < m_galleryModel->rowCount() - 1) {
        navigateToIndex(index + 1);
    }
}

void MainWindow::applyTagToSelection(const QString& tag) {
    auto selectedIds = m_galleryModel->selectedIds();
    if (selectedIds.isEmpty() && m_currentMediaId > 0) {
        selectedIds.insert(m_currentMediaId);
    }
    
    for (qint64 id : selectedIds) {
        m_db->addMediaTags(id, {tag});
    }
    
    m_galleryModel->onTagsChanged();
    m_sidebar->refreshTags();
    updateCurrentMediaTags();
}

void MainWindow::removeTagFromSelection(const QString& tag) {
    auto selectedIds = m_galleryModel->selectedIds();
    if (selectedIds.isEmpty() && m_currentMediaId > 0) {
        selectedIds.insert(m_currentMediaId);
    }
    
    for (qint64 id : selectedIds) {
        m_db->removeMediaTags(id, {tag});
    }
    
    m_galleryModel->onTagsChanged();
    m_sidebar->refreshTags();
    updateCurrentMediaTags();
}

void MainWindow::updateCurrentMediaTags() {
    if (m_currentMediaId > 0) {
        QStringList tags = m_db->getMediaTags(m_currentMediaId);
        m_tagWidget->setTags(tags);
    } else {
        m_tagWidget->setTags({});
    }
}

void MainWindow::refreshGallery() {
    m_galleryModel->refresh();
}

void MainWindow::updateViewerMedia() {
    auto selectedIds = m_galleryModel->selectedIds();
    
    qint64 mediaId = 0;
    if (!selectedIds.isEmpty()) {
        mediaId = *selectedIds.begin();
    } else if (m_galleryModel->rowCount() > 0) {
        mediaId = m_galleryModel->recordAt(0).id;
    }
    
    if (mediaId > 0) {
        showMedia(mediaId);
    }
}

void MainWindow::showMedia(qint64 mediaId) {
    m_currentMediaId = mediaId;
    
    auto record = m_galleryModel->getRecord(mediaId);
    if (!record.has_value()) return;
    
    m_mediaViewer->setMedia(record.value());
    
    // Show/hide video controls
    bool isVideo = record->isVideo();
    m_videoControls->setVisible(isVideo);
    
    // Update tags
    updateCurrentMediaTags();
}

void MainWindow::navigateToIndex(int index) {
    if (index < 0 || index >= m_galleryModel->rowCount()) return;
    
    MediaRecord record = m_galleryModel->recordAt(index);
    if (!record.isValid()) return;
    
    m_galleryModel->clearSelection();
    m_galleryModel->select(record.id, true);
    m_galleryView->selectMediaId(record.id);
    
    showMedia(record.id);
}

int MainWindow::currentMediaIndex() const {
    if (m_currentMediaId <= 0) return -1;
    return m_galleryModel->rowForMediaId(m_currentMediaId);
}

void MainWindow::showToast(const QString& message) {
    // Simple status bar message
    statusBar()->showMessage(message, 3000);
}

} // namespace KeyTagger

