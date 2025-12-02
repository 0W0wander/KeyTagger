#include "Database.h"
#include <QSqlQuery>
#include <QSqlError>
#include <QDir>
#include <QFileInfo>
#include <QDebug>
#include <QUuid>

namespace KeyTagger {

Database::Database(const QString& baseDir, QObject* parent)
    : QObject(parent)
    , m_baseDir(QDir(baseDir).absolutePath())
    , m_connectionName(QUuid::createUuid().toString())
{
    QDir dir(m_baseDir);
    if (!dir.exists()) {
        dir.mkpath(".");
    }
    m_dbPath = dir.filePath("keytag.sqlite");
    initializeSchema();
}

Database::~Database() {
    {
        QSqlDatabase db = QSqlDatabase::database(m_connectionName);
        if (db.isOpen()) {
            db.close();
        }
    }
    QSqlDatabase::removeDatabase(m_connectionName);
}

QSqlDatabase Database::getConnection() {
    if (QSqlDatabase::contains(m_connectionName)) {
        return QSqlDatabase::database(m_connectionName);
    }
    
    QSqlDatabase db = QSqlDatabase::addDatabase("QSQLITE", m_connectionName);
    db.setDatabaseName(m_dbPath);
    
    if (!db.open()) {
        qWarning() << "Failed to open database:" << db.lastError().text();
    }
    
    return db;
}

void Database::initializeSchema() {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    // Enable WAL mode for better concurrency
    query.exec("PRAGMA journal_mode=WAL");
    query.exec("PRAGMA synchronous=NORMAL");
    
    // Media table
    query.exec(R"(
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY,
            file_path TEXT NOT NULL UNIQUE,
            root_dir TEXT NOT NULL,
            file_name TEXT NOT NULL,
            sha256 TEXT,
            p_hash TEXT,
            width INTEGER,
            height INTEGER,
            size_bytes INTEGER,
            captured_time_utc INTEGER,
            modified_time_utc INTEGER,
            media_type TEXT NOT NULL,
            thumbnail_path TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            error TEXT
        )
    )");
    
    // Indexes
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_sha256 ON media(sha256)");
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_phash ON media(p_hash)");
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_file_path ON media(file_path)");
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_modified ON media(modified_time_utc)");
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_root_dir ON media(root_dir)");
    
    // Tags table
    query.exec(R"(
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    )");
    
    // Media-Tags junction table
    query.exec(R"(
        CREATE TABLE IF NOT EXISTS media_tags (
            media_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (media_id, tag_id),
            FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    )");
    
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_tags_media_id ON media_tags(media_id)");
    query.exec("CREATE INDEX IF NOT EXISTS idx_media_tags_tag_id ON media_tags(tag_id)");
}

qint64 Database::upsertMedia(const MediaRecord& record) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare(R"(
        INSERT INTO media (
            file_path, root_dir, file_name, sha256, p_hash, width, height,
            size_bytes, captured_time_utc, modified_time_utc, media_type, 
            thumbnail_path, status, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        ON CONFLICT(file_path) DO UPDATE SET
            sha256=excluded.sha256,
            p_hash=excluded.p_hash,
            width=excluded.width,
            height=excluded.height,
            size_bytes=excluded.size_bytes,
            captured_time_utc=excluded.captured_time_utc,
            modified_time_utc=excluded.modified_time_utc,
            media_type=excluded.media_type,
            thumbnail_path=excluded.thumbnail_path,
            status='active',
            error=excluded.error
    )");
    
    query.addBindValue(record.filePath);
    query.addBindValue(record.rootDir);
    query.addBindValue(record.fileName);
    query.addBindValue(record.sha256.isEmpty() ? QVariant() : record.sha256);
    query.addBindValue(record.pHash.isEmpty() ? QVariant() : record.pHash);
    query.addBindValue(record.width.has_value() ? QVariant(record.width.value()) : QVariant());
    query.addBindValue(record.height.has_value() ? QVariant(record.height.value()) : QVariant());
    query.addBindValue(record.sizeBytes.has_value() ? QVariant(record.sizeBytes.value()) : QVariant());
    query.addBindValue(record.capturedTimeUtc.has_value() ? QVariant(record.capturedTimeUtc.value()) : QVariant());
    query.addBindValue(record.modifiedTimeUtc.has_value() ? QVariant(record.modifiedTimeUtc.value()) : QVariant());
    query.addBindValue(MediaRecord::mediaTypeToString(record.mediaType));
    query.addBindValue(record.thumbnailPath.isEmpty() ? QVariant() : record.thumbnailPath);
    query.addBindValue(record.error.isEmpty() ? QVariant() : record.error);
    
    if (!query.exec()) {
        qWarning() << "Failed to upsert media:" << query.lastError().text();
        return 0;
    }
    
    // Get the ID
    query.prepare("SELECT id FROM media WHERE file_path = ?");
    query.addBindValue(record.filePath);
    if (query.exec() && query.next()) {
        emit databaseChanged();
        return query.value(0).toLongLong();
    }
    
    return 0;
}

std::optional<MediaRecord> Database::getMedia(qint64 id) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare("SELECT * FROM media WHERE id = ?");
    query.addBindValue(id);
    
    if (!query.exec() || !query.next()) {
        return std::nullopt;
    }
    
    MediaRecord record;
    record.id = query.value("id").toLongLong();
    record.filePath = query.value("file_path").toString();
    record.rootDir = query.value("root_dir").toString();
    record.fileName = query.value("file_name").toString();
    record.sha256 = query.value("sha256").toString();
    record.pHash = query.value("p_hash").toString();
    if (!query.value("width").isNull()) record.width = query.value("width").toInt();
    if (!query.value("height").isNull()) record.height = query.value("height").toInt();
    if (!query.value("size_bytes").isNull()) record.sizeBytes = query.value("size_bytes").toLongLong();
    if (!query.value("captured_time_utc").isNull()) record.capturedTimeUtc = query.value("captured_time_utc").toLongLong();
    if (!query.value("modified_time_utc").isNull()) record.modifiedTimeUtc = query.value("modified_time_utc").toLongLong();
    record.mediaType = MediaRecord::stringToMediaType(query.value("media_type").toString());
    record.thumbnailPath = query.value("thumbnail_path").toString();
    record.status = query.value("status").toString();
    record.error = query.value("error").toString();
    
    return record;
}

std::optional<MediaRecord> Database::getMediaByPath(const QString& filePath) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare("SELECT * FROM media WHERE file_path = ?");
    query.addBindValue(filePath);
    
    if (!query.exec() || !query.next()) {
        return std::nullopt;
    }
    
    MediaRecord record;
    record.id = query.value("id").toLongLong();
    record.filePath = query.value("file_path").toString();
    record.rootDir = query.value("root_dir").toString();
    record.fileName = query.value("file_name").toString();
    record.sha256 = query.value("sha256").toString();
    record.pHash = query.value("p_hash").toString();
    if (!query.value("width").isNull()) record.width = query.value("width").toInt();
    if (!query.value("height").isNull()) record.height = query.value("height").toInt();
    if (!query.value("size_bytes").isNull()) record.sizeBytes = query.value("size_bytes").toLongLong();
    if (!query.value("captured_time_utc").isNull()) record.capturedTimeUtc = query.value("captured_time_utc").toLongLong();
    if (!query.value("modified_time_utc").isNull()) record.modifiedTimeUtc = query.value("modified_time_utc").toLongLong();
    record.mediaType = MediaRecord::stringToMediaType(query.value("media_type").toString());
    record.thumbnailPath = query.value("thumbnail_path").toString();
    record.status = query.value("status").toString();
    record.error = query.value("error").toString();
    
    return record;
}

bool Database::deleteMedia(const QString& filePath) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare("DELETE FROM media WHERE file_path = ?");
    query.addBindValue(filePath);
    
    bool success = query.exec() && query.numRowsAffected() > 0;
    if (success) {
        emit databaseChanged();
    }
    return success;
}

bool Database::updateThumbnailPath(const QString& filePath, const QString& thumbnailPath) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare("UPDATE media SET thumbnail_path = ? WHERE file_path = ?");
    query.addBindValue(thumbnailPath.isEmpty() ? QVariant() : thumbnailPath);
    query.addBindValue(filePath);
    
    return query.exec();
}

Database::QueryResult Database::queryMedia(
    const QStringList& requiredTags,
    const QString& searchText,
    int limit,
    int offset,
    const QString& orderBy,
    const QString& rootDir,
    bool tagsMatchAll
) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    QStringList whereClauses;
    QVariantList params;
    
    whereClauses << "status='active'";
    
    if (!searchText.isEmpty()) {
        whereClauses << "file_name LIKE ?";
        params << QString("%%1%").arg(searchText);
    }
    
    if (!requiredTags.isEmpty()) {
        QStringList normalizedTags;
        for (const QString& tag : requiredTags) {
            normalizedTags << tag.trimmed().toLower();
        }
        
        QString placeholders = QString("?,").repeated(normalizedTags.size());
        placeholders.chop(1);
        
        if (tagsMatchAll) {
            whereClauses << QString(
                "id IN (SELECT media_id FROM media_tags WHERE tag_id IN "
                "(SELECT id FROM tags WHERE name IN (%1)) "
                "GROUP BY media_id HAVING COUNT(DISTINCT tag_id) = %2)"
            ).arg(placeholders).arg(normalizedTags.size());
        } else {
            whereClauses << QString(
                "id IN (SELECT DISTINCT media_id FROM media_tags WHERE tag_id IN "
                "(SELECT id FROM tags WHERE name IN (%1)))"
            ).arg(placeholders);
        }
        
        for (const QString& tag : normalizedTags) {
            params << tag;
        }
    }
    
    if (!rootDir.isEmpty()) {
        whereClauses << "root_dir = ?";
        params << QDir(rootDir).absolutePath();
    }
    
    QString whereSQL = whereClauses.join(" AND ");
    
    // Count total
    query.prepare(QString("SELECT COUNT(*) FROM media WHERE %1").arg(whereSQL));
    for (const QVariant& param : params) {
        query.addBindValue(param);
    }
    
    int totalCount = 0;
    if (query.exec() && query.next()) {
        totalCount = query.value(0).toInt();
    }
    
    // Get records
    query.prepare(QString("SELECT * FROM media WHERE %1 ORDER BY %2 LIMIT ? OFFSET ?")
        .arg(whereSQL).arg(orderBy));
    for (const QVariant& param : params) {
        query.addBindValue(param);
    }
    query.addBindValue(limit);
    query.addBindValue(offset);
    
    QVector<MediaRecord> records;
    if (query.exec()) {
        while (query.next()) {
            MediaRecord record;
            record.id = query.value("id").toLongLong();
            record.filePath = query.value("file_path").toString();
            record.rootDir = query.value("root_dir").toString();
            record.fileName = query.value("file_name").toString();
            record.sha256 = query.value("sha256").toString();
            record.pHash = query.value("p_hash").toString();
            if (!query.value("width").isNull()) record.width = query.value("width").toInt();
            if (!query.value("height").isNull()) record.height = query.value("height").toInt();
            if (!query.value("size_bytes").isNull()) record.sizeBytes = query.value("size_bytes").toLongLong();
            if (!query.value("captured_time_utc").isNull()) record.capturedTimeUtc = query.value("captured_time_utc").toLongLong();
            if (!query.value("modified_time_utc").isNull()) record.modifiedTimeUtc = query.value("modified_time_utc").toLongLong();
            record.mediaType = MediaRecord::stringToMediaType(query.value("media_type").toString());
            record.thumbnailPath = query.value("thumbnail_path").toString();
            record.status = query.value("status").toString();
            record.error = query.value("error").toString();
            records.append(record);
        }
    }
    
    return {records, totalCount};
}

QHash<QString, QHash<QString, QVariant>> Database::existingMediaMapForRoot(const QString& rootDir) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare(R"(
        SELECT file_path, size_bytes, modified_time_utc, thumbnail_path, sha256, media_type
        FROM media
        WHERE root_dir = ? AND status = 'active'
    )");
    query.addBindValue(QDir(rootDir).absolutePath());
    
    QHash<QString, QHash<QString, QVariant>> result;
    if (query.exec()) {
        while (query.next()) {
            QHash<QString, QVariant> entry;
            entry["size_bytes"] = query.value("size_bytes");
            entry["modified_time_utc"] = query.value("modified_time_utc");
            entry["thumbnail_path"] = query.value("thumbnail_path");
            entry["sha256"] = query.value("sha256");
            entry["media_type"] = query.value("media_type");
            result[query.value("file_path").toString()] = entry;
        }
    }
    
    return result;
}

int Database::markMissingFilesDeleted(const QStringList& existingPaths, const QString& rootDir) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    QString absRootDir = QDir(rootDir).absolutePath();
    
    if (existingPaths.isEmpty()) {
        query.prepare("UPDATE media SET status='deleted' WHERE root_dir = ? AND status='active'");
        query.addBindValue(absRootDir);
    } else {
        QString placeholders = QString("?,").repeated(existingPaths.size());
        placeholders.chop(1);
        
        query.prepare(QString(
            "UPDATE media SET status='deleted' "
            "WHERE root_dir = ? AND status='active' AND file_path NOT IN (%1)"
        ).arg(placeholders));
        
        query.addBindValue(absRootDir);
        for (const QString& path : existingPaths) {
            query.addBindValue(path);
        }
    }
    
    if (query.exec()) {
        int affected = query.numRowsAffected();
        if (affected > 0) {
            emit databaseChanged();
        }
        return affected;
    }
    
    return 0;
}

QVector<qint64> Database::upsertTags(const QStringList& tagNames) {
    QVector<qint64> tagIds;
    if (tagNames.isEmpty()) return tagIds;
    
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    for (const QString& name : tagNames) {
        QString normalized = name.trimmed().toLower();
        if (normalized.isEmpty()) continue;
        
        query.prepare("INSERT INTO tags(name) VALUES (?) ON CONFLICT(name) DO NOTHING");
        query.addBindValue(normalized);
        query.exec();
        
        query.prepare("SELECT id FROM tags WHERE name = ?");
        query.addBindValue(normalized);
        if (query.exec() && query.next()) {
            tagIds.append(query.value(0).toLongLong());
        }
    }
    
    return tagIds;
}

void Database::setMediaTags(qint64 mediaId, const QStringList& tagNames) {
    QVector<qint64> tagIds = upsertTags(tagNames);
    
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare("DELETE FROM media_tags WHERE media_id = ?");
    query.addBindValue(mediaId);
    query.exec();
    
    for (qint64 tagId : tagIds) {
        query.prepare("INSERT OR IGNORE INTO media_tags(media_id, tag_id) VALUES (?, ?)");
        query.addBindValue(mediaId);
        query.addBindValue(tagId);
        query.exec();
    }
    
    emit tagsChanged();
}

void Database::addMediaTags(qint64 mediaId, const QStringList& tagNames) {
    QVector<qint64> tagIds = upsertTags(tagNames);
    
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    for (qint64 tagId : tagIds) {
        query.prepare("INSERT OR IGNORE INTO media_tags(media_id, tag_id) VALUES (?, ?)");
        query.addBindValue(mediaId);
        query.addBindValue(tagId);
        query.exec();
    }
    
    emit tagsChanged();
}

void Database::removeMediaTags(qint64 mediaId, const QStringList& tagNames) {
    if (tagNames.isEmpty()) return;
    
    QStringList normalized;
    for (const QString& tag : tagNames) {
        QString n = tag.trimmed().toLower();
        if (!n.isEmpty()) normalized << n;
    }
    if (normalized.isEmpty()) return;
    
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    QString placeholders = QString("?,").repeated(normalized.size());
    placeholders.chop(1);
    
    // Get tag IDs
    query.prepare(QString("SELECT id FROM tags WHERE name IN (%1)").arg(placeholders));
    for (const QString& tag : normalized) {
        query.addBindValue(tag);
    }
    
    QVector<qint64> tagIds;
    if (query.exec()) {
        while (query.next()) {
            tagIds.append(query.value(0).toLongLong());
        }
    }
    
    for (qint64 tagId : tagIds) {
        query.prepare("DELETE FROM media_tags WHERE media_id = ? AND tag_id = ?");
        query.addBindValue(mediaId);
        query.addBindValue(tagId);
        query.exec();
    }
    
    emit tagsChanged();
}

int Database::removeTagGlobally(const QString& tagName) {
    QString normalized = tagName.trimmed().toLower();
    if (normalized.isEmpty()) return 0;
    
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare("SELECT id FROM tags WHERE name = ?");
    query.addBindValue(normalized);
    
    if (!query.exec() || !query.next()) return 0;
    
    qint64 tagId = query.value(0).toLongLong();
    
    query.prepare("DELETE FROM media_tags WHERE tag_id = ?");
    query.addBindValue(tagId);
    query.exec();
    int affected = query.numRowsAffected();
    
    // Remove tag if no references remain
    query.prepare("DELETE FROM tags WHERE id = ? AND NOT EXISTS (SELECT 1 FROM media_tags WHERE tag_id = ?)");
    query.addBindValue(tagId);
    query.addBindValue(tagId);
    query.exec();
    
    if (affected > 0) {
        emit tagsChanged();
    }
    
    return affected;
}

QStringList Database::getMediaTags(qint64 mediaId) {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.prepare(R"(
        SELECT t.name
        FROM tags t
        JOIN media_tags mt ON mt.tag_id = t.id
        WHERE mt.media_id = ?
        ORDER BY t.name ASC
    )");
    query.addBindValue(mediaId);
    
    QStringList tags;
    if (query.exec()) {
        while (query.next()) {
            tags << query.value(0).toString();
        }
    }
    
    return tags;
}

QStringList Database::allTags() {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.exec("SELECT name FROM tags ORDER BY name ASC");
    
    QStringList tags;
    while (query.next()) {
        tags << query.value(0).toString();
    }
    
    return tags;
}

QVector<QPair<QString, int>> Database::tagCounts() {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.exec(R"(
        SELECT t.name, COUNT(mt.media_id) as cnt
        FROM tags t
        LEFT JOIN media_tags mt ON mt.tag_id = t.id
        LEFT JOIN media m ON m.id = mt.media_id AND m.status = 'active'
        GROUP BY t.id
        ORDER BY t.name ASC
    )");
    
    QVector<QPair<QString, int>> result;
    while (query.next()) {
        result.append({query.value(0).toString(), query.value(1).toInt()});
    }
    
    return result;
}

int Database::untaggedCount() {
    QSqlDatabase db = getConnection();
    QSqlQuery query(db);
    
    query.exec(R"(
        SELECT COUNT(*) FROM media 
        WHERE status = 'active' 
        AND id NOT IN (SELECT DISTINCT media_id FROM media_tags)
    )");
    
    if (query.next()) {
        return query.value(0).toInt();
    }
    
    return 0;
}

} // namespace KeyTagger

