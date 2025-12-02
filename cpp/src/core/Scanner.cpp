#include "Scanner.h"
#include "Database.h"
#include "MediaRecord.h"

#include <QDir>
#include <QDirIterator>
#include <QFileInfo>
#include <QCryptographicHash>
#include <QImage>
#include <QImageReader>
#include <QPainter>
#include <QDebug>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/videoio.hpp>

namespace KeyTagger {

static const QSet<QString> IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"
};

static const QSet<QString> VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".3gp"
};

static const QSet<QString> AUDIO_EXTENSIONS = {
    ".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac"
};

// ======================== ScannerWorker ========================

ScannerWorker::ScannerWorker(Database* db, const QString& rootDir, 
                             const QString& thumbnailsDir, QObject* parent)
    : QObject(parent)
    , m_db(db)
    , m_rootDir(QDir(rootDir).absolutePath())
    , m_thumbnailsDir(thumbnailsDir)
{
    if (m_thumbnailsDir.isEmpty()) {
        m_thumbnailsDir = QDir(m_rootDir).filePath("thumbnails");
    }
}

void ScannerWorker::cancel() {
    m_cancelled = true;
}

QString ScannerWorker::computeSha256(const QString& filePath) {
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly)) {
        return QString();
    }
    
    QCryptographicHash hash(QCryptographicHash::Sha256);
    
    const qint64 chunkSize = 1024 * 1024; // 1MB chunks
    while (!file.atEnd()) {
        hash.addData(file.read(chunkSize));
    }
    
    return hash.result().toHex();
}

QString ScannerWorker::computeImagePHash(const QString& filePath) {
    // Simple perceptual hash using DCT approach
    try {
        cv::Mat img = cv::imread(filePath.toStdString(), cv::IMREAD_GRAYSCALE);
        if (img.empty()) return QString();
        
        // Resize to 32x32
        cv::Mat resized;
        cv::resize(img, resized, cv::Size(32, 32), 0, 0, cv::INTER_LINEAR);
        
        // Convert to float
        cv::Mat floatImg;
        resized.convertTo(floatImg, CV_32F);
        
        // Apply DCT
        cv::Mat dct;
        cv::dct(floatImg, dct);
        
        // Take top-left 8x8
        cv::Mat dctLow = dct(cv::Rect(0, 0, 8, 8));
        
        // Compute mean (excluding DC component)
        double sum = 0;
        for (int i = 0; i < 8; i++) {
            for (int j = 0; j < 8; j++) {
                if (i == 0 && j == 0) continue;
                sum += dctLow.at<float>(i, j);
            }
        }
        double mean = sum / 63.0;
        
        // Generate hash
        quint64 hash = 0;
        for (int i = 0; i < 8; i++) {
            for (int j = 0; j < 8; j++) {
                if (dctLow.at<float>(i, j) > mean) {
                    hash |= (1ULL << (i * 8 + j));
                }
            }
        }
        
        return QString::number(hash, 16).rightJustified(16, '0');
    } catch (...) {
        return QString();
    }
}

bool ScannerWorker::createImageThumbnail(const QString& sourcePath, const QString& destPath, int maxSize) {
    try {
        QImage img(sourcePath);
        if (img.isNull()) return false;
        
        // Scale to fit in maxSize x maxSize
        QImage scaled = img.scaled(maxSize, maxSize, Qt::KeepAspectRatio, Qt::SmoothTransformation);
        
        // Convert to RGB if necessary
        if (scaled.hasAlphaChannel()) {
            QImage rgb(scaled.size(), QImage::Format_RGB32);
            rgb.fill(Qt::black);
            QPainter painter(&rgb);
            painter.drawImage(0, 0, scaled);
            painter.end();
            scaled = rgb;
        }
        
        QDir().mkpath(QFileInfo(destPath).absolutePath());
        return scaled.save(destPath, "JPEG", 85);
    } catch (...) {
        return false;
    }
}

bool ScannerWorker::createVideoThumbnail(const QString& sourcePath, const QString& destPath, int maxSize) {
    try {
        cv::VideoCapture cap(sourcePath.toStdString());
        if (!cap.isOpened()) return false;
        
        // Seek to middle frame
        int frameCount = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_COUNT));
        if (frameCount > 0) {
            cap.set(cv::CAP_PROP_POS_FRAMES, frameCount / 2);
        }
        
        cv::Mat frame;
        if (!cap.read(frame)) {
            cap.release();
            return false;
        }
        
        // Convert BGR to RGB
        cv::Mat rgb;
        cv::cvtColor(frame, rgb, cv::COLOR_BGR2RGB);
        
        // Create QImage
        QImage img(rgb.data, rgb.cols, rgb.rows, static_cast<int>(rgb.step), QImage::Format_RGB888);
        QImage copy = img.copy(); // Make a deep copy since cv::Mat will be destroyed
        
        cap.release();
        
        // Scale
        QImage scaled = copy.scaled(maxSize, maxSize, Qt::KeepAspectRatio, Qt::SmoothTransformation);
        
        QDir().mkpath(QFileInfo(destPath).absolutePath());
        return scaled.save(destPath, "JPEG", 85);
    } catch (...) {
        return false;
    }
}

QPair<int, int> ScannerWorker::getImageDimensions(const QString& filePath) {
    QImageReader reader(filePath);
    QSize size = reader.size();
    return {size.width(), size.height()};
}

QPair<int, int> ScannerWorker::getVideoDimensions(const QString& filePath) {
    try {
        cv::VideoCapture cap(filePath.toStdString());
        if (!cap.isOpened()) return {0, 0};
        
        int width = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_WIDTH));
        int height = static_cast<int>(cap.get(cv::CAP_PROP_FRAME_HEIGHT));
        cap.release();
        
        return {width, height};
    } catch (...) {
        return {0, 0};
    }
}

qint64 ScannerWorker::getImageCaptureTime(const QString& filePath) {
    // Try to extract EXIF DateTimeOriginal
    // This is a simplified version - for full EXIF support, consider using libexiv2
    QImageReader reader(filePath);
    QString text = reader.text("DateTimeOriginal");
    if (text.isEmpty()) {
        text = reader.text("DateTime");
    }
    
    if (!text.isEmpty()) {
        // Parse "YYYY:MM:DD HH:MM:SS" format
        QDateTime dt = QDateTime::fromString(text, "yyyy:MM:dd HH:mm:ss");
        if (dt.isValid()) {
            return dt.toSecsSinceEpoch();
        }
    }
    
    return 0;
}

void ScannerWorker::process() {
    ScanResult result;
    
    // Get list of media files
    QStringList files = Scanner::listMediaFiles(m_rootDir);
    
    // Mark missing files as deleted
    try {
        m_db->markMissingFilesDeleted(files, m_rootDir);
    } catch (...) {}
    
    int total = files.size();
    
    // Get existing media map for incremental scanning
    auto existingMap = m_db->existingMediaMapForRoot(m_rootDir);
    
    QDir().mkpath(m_thumbnailsDir);
    
    for (int idx = 0; idx < total && !m_cancelled; ++idx) {
        const QString& filePath = files[idx];
        emit progress(idx + 1, total, filePath);
        
        QFileInfo fi(filePath);
        QString fileName = fi.fileName();
        QString ext = fi.suffix().toLower();
        ext = "." + ext;
        
        try {
            qint64 sizeBytes = fi.size();
            qint64 modifiedTimeUtc = fi.lastModified().toSecsSinceEpoch();
            
            // Check if we can skip this file
            if (existingMap.contains(filePath)) {
                auto& prev = existingMap[filePath];
                if (prev["size_bytes"].toLongLong() == sizeBytes &&
                    prev["modified_time_utc"].toLongLong() == modifiedTimeUtc &&
                    !prev["sha256"].toString().isEmpty()) {
                    
                    // Check if thumbnail exists
                    QString existingThumb = prev["thumbnail_path"].toString();
                    if (!existingThumb.isEmpty() && QFile::exists(existingThumb)) {
                        result.scanned++;
                        continue;
                    }
                    
                    // Create missing thumbnail
                    QString sha256 = prev["sha256"].toString();
                    QString thumbPath = QDir(m_thumbnailsDir).filePath(sha256 + ".jpg");
                    
                    bool thumbCreated = false;
                    if (Scanner::isImageFile(filePath)) {
                        thumbCreated = createImageThumbnail(filePath, thumbPath);
                    } else if (Scanner::isVideoFile(filePath)) {
                        thumbCreated = createVideoThumbnail(filePath, thumbPath);
                    }
                    
                    if (thumbCreated && thumbPath != existingThumb) {
                        m_db->updateThumbnailPath(filePath, thumbPath);
                    }
                    
                    result.scanned++;
                    continue;
                }
            }
            
            // Full processing for new or changed files
            QString sha256 = computeSha256(filePath);
            QString pHash;
            int width = 0, height = 0;
            qint64 capturedTime = 0;
            QString thumbPath = QDir(m_thumbnailsDir).filePath(sha256 + ".jpg");
            
            MediaType mediaType = MediaRecord::typeFromExtension(ext);
            
            if (mediaType == MediaType::Image) {
                pHash = computeImagePHash(filePath);
                auto dims = getImageDimensions(filePath);
                width = dims.first;
                height = dims.second;
                capturedTime = getImageCaptureTime(filePath);
                
                if (!QFile::exists(thumbPath)) {
                    createImageThumbnail(filePath, thumbPath);
                }
            } else if (mediaType == MediaType::Video) {
                auto dims = getVideoDimensions(filePath);
                width = dims.first;
                height = dims.second;
                
                if (!QFile::exists(thumbPath)) {
                    if (!createVideoThumbnail(filePath, thumbPath)) {
                        thumbPath.clear();
                    }
                }
            } else {
                // Audio - no thumbnail
                thumbPath.clear();
            }
            
            MediaRecord record;
            record.filePath = filePath;
            record.rootDir = m_rootDir;
            record.fileName = fileName;
            record.sha256 = sha256;
            record.pHash = pHash;
            if (width > 0) record.width = width;
            if (height > 0) record.height = height;
            record.sizeBytes = sizeBytes;
            if (capturedTime > 0) record.capturedTimeUtc = capturedTime;
            record.modifiedTimeUtc = modifiedTimeUtc;
            record.mediaType = mediaType;
            record.thumbnailPath = thumbPath;
            
            qint64 mediaId = m_db->upsertMedia(record);
            if (mediaId > 0) {
                result.addedOrUpdated++;
            }
            
        } catch (const std::exception& e) {
            qWarning() << "Error processing" << filePath << ":" << e.what();
            
            // Insert error record
            MediaRecord errorRecord;
            errorRecord.filePath = filePath;
            errorRecord.rootDir = m_rootDir;
            errorRecord.fileName = fileName;
            errorRecord.mediaType = MediaRecord::typeFromExtension(ext);
            errorRecord.error = QString::fromStdString(e.what());
            m_db->upsertMedia(errorRecord);
            
            result.errors++;
        }
        
        result.scanned++;
    }
    
    emit finished(result);
}

// ======================== Scanner ========================

Scanner::Scanner(Database* db, QObject* parent)
    : QObject(parent)
    , m_db(db)
{
}

Scanner::~Scanner() {
    cancel();
}

void Scanner::scanDirectory(const QString& rootDir, const QString& thumbnailsDir) {
    if (isRunning()) {
        cancel();
    }
    
    m_workerThread = new QThread(this);
    m_worker = new ScannerWorker(m_db, rootDir, thumbnailsDir);
    m_worker->moveToThread(m_workerThread);
    
    connect(m_workerThread, &QThread::started, m_worker, &ScannerWorker::process);
    connect(m_worker, &ScannerWorker::progress, this, &Scanner::scanProgress);
    connect(m_worker, &ScannerWorker::finished, this, [this](ScanResult result) {
        emit scanFinished(result);
        m_workerThread->quit();
    });
    connect(m_worker, &ScannerWorker::error, this, &Scanner::scanError);
    connect(m_workerThread, &QThread::finished, m_worker, &QObject::deleteLater);
    connect(m_workerThread, &QThread::finished, m_workerThread, &QObject::deleteLater);
    connect(m_workerThread, &QThread::finished, this, [this]() {
        m_worker = nullptr;
        m_workerThread = nullptr;
    });
    
    m_workerThread->start();
}

void Scanner::cancel() {
    if (m_worker) {
        m_worker->cancel();
    }
    if (m_workerThread) {
        m_workerThread->quit();
        m_workerThread->wait(5000);
    }
}

bool Scanner::isRunning() const {
    return m_workerThread && m_workerThread->isRunning();
}

QStringList Scanner::listMediaFiles(const QString& rootDir) {
    QStringList files;
    QString absRoot = QDir(rootDir).absolutePath();
    
    QDirIterator it(absRoot, QDir::Files, QDirIterator::Subdirectories);
    while (it.hasNext()) {
        QString path = it.next();
        QString ext = QFileInfo(path).suffix().toLower();
        ext = "." + ext;
        
        if (IMAGE_EXTENSIONS.contains(ext) || 
            VIDEO_EXTENSIONS.contains(ext) || 
            AUDIO_EXTENSIONS.contains(ext)) {
            files.append(path);
        }
    }
    
    return files;
}

bool Scanner::isImageFile(const QString& path) {
    QString ext = "." + QFileInfo(path).suffix().toLower();
    return IMAGE_EXTENSIONS.contains(ext);
}

bool Scanner::isVideoFile(const QString& path) {
    QString ext = "." + QFileInfo(path).suffix().toLower();
    return VIDEO_EXTENSIONS.contains(ext);
}

bool Scanner::isAudioFile(const QString& path) {
    QString ext = "." + QFileInfo(path).suffix().toLower();
    return AUDIO_EXTENSIONS.contains(ext);
}

} // namespace KeyTagger

