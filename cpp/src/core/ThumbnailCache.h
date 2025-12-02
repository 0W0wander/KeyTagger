#pragma once

#include <QObject>
#include <QPixmap>
#include <QCache>
#include <QHash>
#include <QSet>
#include <QMutex>
#include <QThreadPool>
#include <QRunnable>
#include <memory>

namespace KeyTagger {

/**
 * ThumbnailCache - High-performance thumbnail loading system inspired by digiKam
 * 
 * Key features:
 * - Async thumbnail loading with priority queue
 * - Memory-efficient LRU cache
 * - Automatic downscaling for display
 * - Placeholder generation for missing thumbnails
 * - Thread-safe design for concurrent access
 */
class ThumbnailCache : public QObject {
    Q_OBJECT

public:
    explicit ThumbnailCache(int cacheSize = 500, QObject* parent = nullptr);
    ~ThumbnailCache();

    // Get thumbnail synchronously (returns placeholder if not cached)
    QPixmap getThumbnail(qint64 mediaId, const QString& thumbnailPath, int targetSize);
    
    // Request async load (emits thumbnailLoaded when ready)
    void requestThumbnail(qint64 mediaId, const QString& thumbnailPath, int targetSize);
    
    // Cancel pending requests (e.g., when scrolling fast)
    void cancelPendingRequests();
    void cancelRequest(qint64 mediaId);
    
    // Clear cache
    void clear();
    
    // Get placeholder pixmap
    static QPixmap createPlaceholder(int size, bool isDarkMode = true);
    static QPixmap createAudioPlaceholder(int size, bool isDarkMode = true);
    static QPixmap createVideoOverlay(int size);

    // Cache statistics
    int cacheCount() const;
    int pendingCount() const;

signals:
    void thumbnailLoaded(qint64 mediaId, const QPixmap& thumbnail);
    void thumbnailFailed(qint64 mediaId);

private:
    friend class ThumbnailLoadTask;
    
    void onThumbnailLoaded(qint64 mediaId, int targetSize, const QPixmap& pixmap);
    QString cacheKey(qint64 mediaId, int targetSize) const;

    QCache<QString, QPixmap> m_cache;
    QSet<qint64> m_pendingRequests;
    QMutex m_mutex;
    QThreadPool m_threadPool;
    
    QPixmap m_placeholder;
    QPixmap m_audioPlaceholder;
    int m_currentPlaceholderSize = 0;
};

class ThumbnailLoadTask : public QRunnable {
public:
    ThumbnailLoadTask(ThumbnailCache* cache, qint64 mediaId, 
                      const QString& path, int targetSize);
    void run() override;

private:
    ThumbnailCache* m_cache;
    qint64 m_mediaId;
    QString m_path;
    int m_targetSize;
};

} // namespace KeyTagger

