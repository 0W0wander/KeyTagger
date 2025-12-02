#include "ThumbnailCache.h"
#include <QImage>
#include <QPainter>
#include <QFileInfo>
#include <QDebug>
#include <QApplication>

namespace KeyTagger {

ThumbnailCache::ThumbnailCache(int cacheSize, QObject* parent)
    : QObject(parent)
    , m_cache(cacheSize)
{
    // Configure thread pool for optimal thumbnail loading
    int threadCount = qMax(2, QThread::idealThreadCount() / 2);
    m_threadPool.setMaxThreadCount(threadCount);
}

ThumbnailCache::~ThumbnailCache() {
    cancelPendingRequests();
    m_threadPool.waitForDone(3000);
}

QString ThumbnailCache::cacheKey(qint64 mediaId, int targetSize) const {
    return QString("%1_%2").arg(mediaId).arg(targetSize);
}

QPixmap ThumbnailCache::getThumbnail(qint64 mediaId, const QString& thumbnailPath, int targetSize) {
    QString key = cacheKey(mediaId, targetSize);
    
    QMutexLocker locker(&m_mutex);
    
    if (QPixmap* cached = m_cache.object(key)) {
        return *cached;
    }
    
    // Check if placeholder size needs update
    if (m_currentPlaceholderSize != targetSize) {
        m_placeholder = createPlaceholder(targetSize);
        m_audioPlaceholder = createAudioPlaceholder(targetSize);
        m_currentPlaceholderSize = targetSize;
    }
    
    return m_placeholder;
}

void ThumbnailCache::requestThumbnail(qint64 mediaId, const QString& thumbnailPath, int targetSize) {
    QString key = cacheKey(mediaId, targetSize);
    
    QMutexLocker locker(&m_mutex);
    
    // Already cached
    if (m_cache.contains(key)) {
        if (QPixmap* cached = m_cache.object(key)) {
            QMetaObject::invokeMethod(this, [this, mediaId, pix = *cached]() {
                emit thumbnailLoaded(mediaId, pix);
            }, Qt::QueuedConnection);
        }
        return;
    }
    
    // Already pending
    if (m_pendingRequests.contains(mediaId)) {
        return;
    }
    
    // No thumbnail path - emit failure
    if (thumbnailPath.isEmpty() || !QFileInfo::exists(thumbnailPath)) {
        QMetaObject::invokeMethod(this, [this, mediaId]() {
            emit thumbnailFailed(mediaId);
        }, Qt::QueuedConnection);
        return;
    }
    
    m_pendingRequests.insert(mediaId);
    locker.unlock();
    
    // Queue load task
    auto task = new ThumbnailLoadTask(this, mediaId, thumbnailPath, targetSize);
    m_threadPool.start(task);
}

void ThumbnailCache::cancelPendingRequests() {
    QMutexLocker locker(&m_mutex);
    m_pendingRequests.clear();
    m_threadPool.clear();
}

void ThumbnailCache::cancelRequest(qint64 mediaId) {
    QMutexLocker locker(&m_mutex);
    m_pendingRequests.remove(mediaId);
}

void ThumbnailCache::clear() {
    QMutexLocker locker(&m_mutex);
    m_cache.clear();
}

void ThumbnailCache::onThumbnailLoaded(qint64 mediaId, int targetSize, const QPixmap& pixmap) {
    QString key = cacheKey(mediaId, targetSize);
    
    QMutexLocker locker(&m_mutex);
    
    // Check if request was cancelled
    if (!m_pendingRequests.contains(mediaId)) {
        return;
    }
    
    m_pendingRequests.remove(mediaId);
    
    if (!pixmap.isNull()) {
        m_cache.insert(key, new QPixmap(pixmap));
        locker.unlock();
        emit thumbnailLoaded(mediaId, pixmap);
    } else {
        locker.unlock();
        emit thumbnailFailed(mediaId);
    }
}

QPixmap ThumbnailCache::createPlaceholder(int size, bool isDarkMode) {
    QPixmap pix(size, size);
    pix.fill(isDarkMode ? QColor(50, 50, 55) : QColor(220, 220, 225));
    
    QPainter painter(&pix);
    painter.setRenderHint(QPainter::Antialiasing);
    
    // Draw loading indicator
    QColor barColor = isDarkMode ? QColor(80, 80, 90) : QColor(180, 180, 190);
    int barHeight = 6;
    int barWidth = size / 2;
    int x = (size - barWidth) / 2;
    int y = (size - barHeight) / 2;
    
    painter.fillRect(x, y, barWidth, barHeight, barColor);
    
    return pix;
}

QPixmap ThumbnailCache::createAudioPlaceholder(int size, bool isDarkMode) {
    QPixmap pix(size, size);
    pix.fill(isDarkMode ? QColor(31, 41, 55) : QColor(230, 235, 240));
    
    QPainter painter(&pix);
    painter.setRenderHint(QPainter::Antialiasing);
    
    QColor textColor = isDarkMode ? QColor(229, 231, 235) : QColor(50, 50, 60);
    painter.setPen(textColor);
    
    QFont font = painter.font();
    font.setPixelSize(size / 5);
    font.setBold(true);
    painter.setFont(font);
    
    painter.drawText(pix.rect(), Qt::AlignCenter, "audio");
    
    return pix;
}

QPixmap ThumbnailCache::createVideoOverlay(int size) {
    QPixmap pix(size, size);
    pix.fill(Qt::transparent);
    
    QPainter painter(&pix);
    painter.setRenderHint(QPainter::Antialiasing);
    
    // Draw play button
    int buttonSize = size / 4;
    int cx = size / 2;
    int cy = size / 2;
    
    // Semi-transparent circle
    painter.setBrush(QColor(0, 0, 0, 150));
    painter.setPen(Qt::NoPen);
    painter.drawEllipse(QPoint(cx, cy), buttonSize, buttonSize);
    
    // Play triangle
    painter.setBrush(Qt::white);
    QPolygon triangle;
    int triSize = buttonSize / 2;
    triangle << QPoint(cx - triSize/2 + 2, cy - triSize)
             << QPoint(cx - triSize/2 + 2, cy + triSize)
             << QPoint(cx + triSize, cy);
    painter.drawPolygon(triangle);
    
    return pix;
}

int ThumbnailCache::cacheCount() const {
    return m_cache.count();
}

int ThumbnailCache::pendingCount() const {
    QMutexLocker locker(&const_cast<ThumbnailCache*>(this)->m_mutex);
    return m_pendingRequests.size();
}

// ======================== ThumbnailLoadTask ========================

ThumbnailLoadTask::ThumbnailLoadTask(ThumbnailCache* cache, qint64 mediaId,
                                     const QString& path, int targetSize)
    : m_cache(cache)
    , m_mediaId(mediaId)
    , m_path(path)
    , m_targetSize(targetSize)
{
    setAutoDelete(true);
}

void ThumbnailLoadTask::run() {
    QPixmap result;
    
    if (!m_path.isEmpty() && QFileInfo::exists(m_path)) {
        QImage img(m_path);
        if (!img.isNull()) {
            // Scale to fit target size (square with padding)
            QImage scaled = img.scaled(m_targetSize, m_targetSize, 
                                       Qt::KeepAspectRatio, 
                                       Qt::SmoothTransformation);
            
            // Create square canvas with centered image
            QImage canvas(m_targetSize, m_targetSize, QImage::Format_RGB32);
            canvas.fill(QColor(15, 23, 42)); // Dark background
            
            QPainter painter(&canvas);
            int x = (m_targetSize - scaled.width()) / 2;
            int y = (m_targetSize - scaled.height()) / 2;
            painter.drawImage(x, y, scaled);
            painter.end();
            
            result = QPixmap::fromImage(canvas);
        }
    }
    
    // Invoke callback on the main thread
    QMetaObject::invokeMethod(m_cache, [this, result]() {
        m_cache->onThumbnailLoaded(m_mediaId, m_targetSize, result);
    }, Qt::QueuedConnection);
}

} // namespace KeyTagger

