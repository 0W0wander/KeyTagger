#pragma once

#include <QObject>
#include <QString>
#include <QStringList>
#include <QThread>
#include <atomic>

namespace KeyTagger {

class Database;

struct ScanResult {
    int scanned = 0;
    int addedOrUpdated = 0;
    int errors = 0;
};

class ScannerWorker : public QObject {
    Q_OBJECT

public:
    explicit ScannerWorker(Database* db, const QString& rootDir, 
                           const QString& thumbnailsDir, QObject* parent = nullptr);

public slots:
    void process();
    void cancel();

signals:
    void progress(int current, int total, const QString& currentFile);
    void finished(ScanResult result);
    void error(const QString& message);

private:
    QString computeSha256(const QString& filePath);
    QString computeImagePHash(const QString& filePath);
    bool createImageThumbnail(const QString& sourcePath, const QString& destPath, int maxSize = 512);
    bool createVideoThumbnail(const QString& sourcePath, const QString& destPath, int maxSize = 512);
    QPair<int, int> getImageDimensions(const QString& filePath);
    QPair<int, int> getVideoDimensions(const QString& filePath);
    qint64 getImageCaptureTime(const QString& filePath);

    Database* m_db;
    QString m_rootDir;
    QString m_thumbnailsDir;
    std::atomic<bool> m_cancelled{false};
};

class Scanner : public QObject {
    Q_OBJECT

public:
    explicit Scanner(Database* db, QObject* parent = nullptr);
    ~Scanner();

    void scanDirectory(const QString& rootDir, const QString& thumbnailsDir = QString());
    void cancel();
    bool isRunning() const;

    static QStringList listMediaFiles(const QString& rootDir);
    static bool isImageFile(const QString& path);
    static bool isVideoFile(const QString& path);
    static bool isAudioFile(const QString& path);

signals:
    void scanProgress(int current, int total, const QString& currentFile);
    void scanFinished(ScanResult result);
    void scanError(const QString& message);

private:
    Database* m_db;
    QThread* m_workerThread = nullptr;
    ScannerWorker* m_worker = nullptr;
};

} // namespace KeyTagger

