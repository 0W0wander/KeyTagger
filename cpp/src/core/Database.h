#pragma once

#include <QObject>
#include <QString>
#include <QSqlDatabase>
#include <QVector>
#include <QHash>
#include <QPair>
#include <memory>
#include "MediaRecord.h"

namespace KeyTagger {

class Database : public QObject {
    Q_OBJECT

public:
    explicit Database(const QString& baseDir, QObject* parent = nullptr);
    ~Database();

    // Media operations
    qint64 upsertMedia(const MediaRecord& record);
    std::optional<MediaRecord> getMedia(qint64 id);
    std::optional<MediaRecord> getMediaByPath(const QString& filePath);
    bool deleteMedia(const QString& filePath);
    bool updateThumbnailPath(const QString& filePath, const QString& thumbnailPath);
    
    // Query operations
    struct QueryResult {
        QVector<MediaRecord> records;
        int totalCount;
    };
    
    QueryResult queryMedia(
        const QStringList& requiredTags = {},
        const QString& searchText = QString(),
        int limit = 200,
        int offset = 0,
        const QString& orderBy = "modified_time_utc DESC, id DESC",
        const QString& rootDir = QString(),
        bool tagsMatchAll = true
    );
    
    // Existing media map for incremental scanning
    QHash<QString, QHash<QString, QVariant>> existingMediaMapForRoot(const QString& rootDir);
    int markMissingFilesDeleted(const QStringList& existingPaths, const QString& rootDir);
    
    // Tag operations
    QVector<qint64> upsertTags(const QStringList& tagNames);
    void setMediaTags(qint64 mediaId, const QStringList& tagNames);
    void addMediaTags(qint64 mediaId, const QStringList& tagNames);
    void removeMediaTags(qint64 mediaId, const QStringList& tagNames);
    int removeTagGlobally(const QString& tagName);
    QStringList getMediaTags(qint64 mediaId);
    QStringList allTags();
    
    // Tag counts for sidebar
    QVector<QPair<QString, int>> tagCounts();
    int untaggedCount();

signals:
    void databaseChanged();
    void tagsChanged();

private:
    void initializeSchema();
    QSqlDatabase getConnection();
    
    QString m_baseDir;
    QString m_dbPath;
    QString m_connectionName;
};

} // namespace KeyTagger

