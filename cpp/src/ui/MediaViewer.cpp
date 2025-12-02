#include "MediaViewer.h"
#include "MediaRecord.h"
#include <QVBoxLayout>
#include <QResizeEvent>
#include <QContextMenuEvent>
#include <QAudioOutput>
#include <QPainter>
#include <QFileInfo>
#include <QDebug>

namespace KeyTagger {

MediaViewer::MediaViewer(QWidget* parent)
    : QWidget(parent)
{
    QVBoxLayout* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    
    // Image display
    m_imageLabel = new QLabel(this);
    m_imageLabel->setAlignment(Qt::AlignCenter);
    m_imageLabel->setScaledContents(false);
    m_imageLabel->hide();
    layout->addWidget(m_imageLabel, 1);
    
    // Video display
    m_videoWidget = new QVideoWidget(this);
    m_videoWidget->hide();
    layout->addWidget(m_videoWidget, 1);
    
    // Media player for video/audio
    m_mediaPlayer = new QMediaPlayer(this);
    m_mediaPlayer->setVideoOutput(m_videoWidget);
    
    QAudioOutput* audioOutput = new QAudioOutput(this);
    m_mediaPlayer->setAudioOutput(audioOutput);
    
    connect(m_mediaPlayer, &QMediaPlayer::mediaStatusChanged,
            this, &MediaViewer::onMediaStatusChanged);
    connect(m_mediaPlayer, &QMediaPlayer::playbackStateChanged,
            this, &MediaViewer::onPlaybackStateChanged);
    connect(m_mediaPlayer, &QMediaPlayer::positionChanged,
            this, &MediaViewer::onPositionChanged);
    connect(m_mediaPlayer, &QMediaPlayer::durationChanged,
            this, &MediaViewer::onDurationChanged);
    
    setDarkMode(true);
}

MediaViewer::~MediaViewer() {
    clear();
}

void MediaViewer::setMedia(const MediaRecord& record) {
    clear();
    
    if (!record.isValid()) return;
    
    m_currentPath = record.filePath;
    
    switch (record.mediaType) {
        case MediaType::Image: {
            QString ext = QFileInfo(record.filePath).suffix().toLower();
            if (ext == "gif") {
                showGif(record.filePath);
            } else {
                showImage(record.filePath);
            }
            break;
        }
        case MediaType::Video:
            showVideo(record.filePath);
            break;
        case MediaType::Audio:
            showAudio(record.filePath);
            break;
        default:
            break;
    }
}

void MediaViewer::clear() {
    hideAll();
    
    m_mediaPlayer->stop();
    m_mediaPlayer->setSource(QUrl());
    
    if (m_gifMovie) {
        m_gifMovie->stop();
        delete m_gifMovie;
        m_gifMovie = nullptr;
    }
    
    m_currentPath.clear();
    m_currentImage = QPixmap();
    m_displayMode = DisplayMode::None;
}

void MediaViewer::setDarkMode(bool dark) {
    m_darkMode = dark;
    
    QPalette pal = palette();
    QColor bgColor = dark ? QColor(10, 15, 26) : QColor(246, 247, 251);
    pal.setColor(QPalette::Window, bgColor);
    pal.setColor(QPalette::Base, bgColor);
    setPalette(pal);
    setAutoFillBackground(true);
}

void MediaViewer::play() {
    if (m_displayMode == DisplayMode::Video || m_displayMode == DisplayMode::Audio) {
        m_mediaPlayer->play();
    } else if (m_displayMode == DisplayMode::Gif && m_gifMovie) {
        m_gifMovie->start();
    }
}

void MediaViewer::pause() {
    if (m_displayMode == DisplayMode::Video || m_displayMode == DisplayMode::Audio) {
        m_mediaPlayer->pause();
    } else if (m_displayMode == DisplayMode::Gif && m_gifMovie) {
        m_gifMovie->setPaused(true);
    }
}

void MediaViewer::togglePlayPause() {
    if (isPlaying()) {
        pause();
    } else {
        play();
    }
}

void MediaViewer::seek(qint64 position) {
    if (m_displayMode == DisplayMode::Video || m_displayMode == DisplayMode::Audio) {
        m_mediaPlayer->setPosition(position);
    }
}

bool MediaViewer::isPlaying() const {
    if (m_displayMode == DisplayMode::Video || m_displayMode == DisplayMode::Audio) {
        return m_mediaPlayer->playbackState() == QMediaPlayer::PlayingState;
    }
    if (m_displayMode == DisplayMode::Gif && m_gifMovie) {
        return m_gifMovie->state() == QMovie::Running;
    }
    return false;
}

qint64 MediaViewer::duration() const {
    if (m_displayMode == DisplayMode::Video || m_displayMode == DisplayMode::Audio) {
        return m_mediaPlayer->duration();
    }
    return 0;
}

qint64 MediaViewer::position() const {
    if (m_displayMode == DisplayMode::Video || m_displayMode == DisplayMode::Audio) {
        return m_mediaPlayer->position();
    }
    return 0;
}

void MediaViewer::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    
    if (m_displayMode == DisplayMode::Image && !m_currentImage.isNull()) {
        updateImageDisplay();
    }
}

void MediaViewer::mouseDoubleClickEvent(QMouseEvent* event) {
    Q_UNUSED(event);
    emit openFileRequested();
}

void MediaViewer::contextMenuEvent(QContextMenuEvent* event) {
    emit contextMenuRequested(event->globalPos());
    event->accept();
}

void MediaViewer::onMediaStatusChanged(QMediaPlayer::MediaStatus status) {
    if (status == QMediaPlayer::LoadedMedia) {
        if (m_displayMode == DisplayMode::Video) {
            m_mediaPlayer->play();
        }
    }
}

void MediaViewer::onPlaybackStateChanged(QMediaPlayer::PlaybackState state) {
    emit playbackStateChanged(state == QMediaPlayer::PlayingState);
}

void MediaViewer::onPositionChanged(qint64 position) {
    emit positionChanged(position);
}

void MediaViewer::onDurationChanged(qint64 duration) {
    emit durationChanged(duration);
}

void MediaViewer::showImage(const QString& path) {
    m_displayMode = DisplayMode::Image;
    
    m_currentImage.load(path);
    
    if (!m_currentImage.isNull()) {
        updateImageDisplay();
        m_imageLabel->show();
    }
}

void MediaViewer::updateImageDisplay() {
    if (m_currentImage.isNull()) return;
    
    QSize availableSize = size();
    if (availableSize.isEmpty()) return;
    
    QPixmap scaled = m_currentImage.scaled(
        availableSize, 
        Qt::KeepAspectRatio, 
        Qt::SmoothTransformation
    );
    
    m_imageLabel->setPixmap(scaled);
}

void MediaViewer::showVideo(const QString& path) {
    m_displayMode = DisplayMode::Video;
    
    m_videoWidget->show();
    m_mediaPlayer->setSource(QUrl::fromLocalFile(path));
}

void MediaViewer::showGif(const QString& path) {
    m_displayMode = DisplayMode::Gif;
    
    m_gifMovie = new QMovie(path);
    if (m_gifMovie->isValid()) {
        m_imageLabel->setMovie(m_gifMovie);
        m_imageLabel->show();
        m_gifMovie->start();
    } else {
        // Fall back to static image
        delete m_gifMovie;
        m_gifMovie = nullptr;
        showImage(path);
    }
}

void MediaViewer::showAudio(const QString& path) {
    m_displayMode = DisplayMode::Audio;
    
    // Show audio placeholder
    QPixmap placeholder(size());
    placeholder.fill(m_darkMode ? QColor(31, 41, 55) : QColor(230, 235, 240));
    
    QPainter painter(&placeholder);
    painter.setRenderHint(QPainter::Antialiasing);
    
    QColor textColor = m_darkMode ? QColor(229, 231, 235) : QColor(50, 50, 60);
    painter.setPen(textColor);
    
    QFont font = painter.font();
    font.setPixelSize(32);
    font.setBold(true);
    painter.setFont(font);
    
    painter.drawText(placeholder.rect(), Qt::AlignCenter, "♪ Audio");
    painter.end();
    
    m_imageLabel->setPixmap(placeholder);
    m_imageLabel->show();
    
    m_mediaPlayer->setSource(QUrl::fromLocalFile(path));
}

void MediaViewer::hideAll() {
    m_imageLabel->hide();
    m_imageLabel->clear();
    m_videoWidget->hide();
}

} // namespace KeyTagger

