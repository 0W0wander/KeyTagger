#pragma once

#include <QWidget>
#include <QLabel>
#include <QMediaPlayer>
#include <QVideoWidget>
#include <QMovie>
#include <memory>

namespace KeyTagger {

class MediaRecord;

/**
 * MediaViewer - Full-size media preview with playback controls
 * 
 * Supports:
 * - Static images (scaled to fit)
 * - Animated GIFs
 * - Videos with play/pause/seek
 * - Audio with playback indicator
 */
class MediaViewer : public QWidget {
    Q_OBJECT

public:
    explicit MediaViewer(QWidget* parent = nullptr);
    ~MediaViewer();
    
    void setMedia(const MediaRecord& record);
    void clear();
    
    void setDarkMode(bool dark);
    
    // Playback controls
    void play();
    void pause();
    void togglePlayPause();
    void seek(qint64 position);
    bool isPlaying() const;
    qint64 duration() const;
    qint64 position() const;

signals:
    void openFileRequested();
    void contextMenuRequested(const QPoint& globalPos);
    void playbackStateChanged(bool playing);
    void positionChanged(qint64 position);
    void durationChanged(qint64 duration);

protected:
    void resizeEvent(QResizeEvent* event) override;
    void mouseDoubleClickEvent(QMouseEvent* event) override;
    void contextMenuEvent(QContextMenuEvent* event) override;

private slots:
    void onMediaStatusChanged(QMediaPlayer::MediaStatus status);
    void onPlaybackStateChanged(QMediaPlayer::PlaybackState state);
    void onPositionChanged(qint64 position);
    void onDurationChanged(qint64 duration);
    void updateImageDisplay();

private:
    void showImage(const QString& path);
    void showVideo(const QString& path);
    void showGif(const QString& path);
    void showAudio(const QString& path);
    void hideAll();
    
    QLabel* m_imageLabel = nullptr;
    QVideoWidget* m_videoWidget = nullptr;
    QMediaPlayer* m_mediaPlayer = nullptr;
    QMovie* m_gifMovie = nullptr;
    
    QString m_currentPath;
    QPixmap m_currentImage;
    bool m_darkMode = true;
    
    enum class DisplayMode {
        None,
        Image,
        Video,
        Gif,
        Audio
    };
    DisplayMode m_displayMode = DisplayMode::None;
};

} // namespace KeyTagger

