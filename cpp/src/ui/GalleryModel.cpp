#include "GalleryModel.h"
#include "Database.h"
#include "ThumbnailCache.h"
#include <QDebug>

namespace KeyTagger {

GalleryModel::GalleryModel(Database* db, ThumbnailCache* cache, QObject* parent)
    : QAbstractListModel(parent)
    , m_db(db)
    , m_cache(cache)
{
    connect(m_cache, &ThumbnailCache::thumbnailLoaded, 
            this, &GalleryModel::onThumbnailLoaded);
    connect(m_db, &Database::tagsChanged,
            this, &GalleryModel::onTagsChanged);
}

int GalleryModel::rowCount(const QModelIndex& parent) const {
    if (parent.isValid()) return 0;
    return m_records.size();
}

QVariant GalleryModel::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() < 0 || index.row() >= m_records.size()) {
        return QVariant();
    }
    
    const MediaRecord& record = m_records.at(index.row());
    
    switch (role) {
        case Qt::DisplayRole:
        case FileNameRole:
            return record.fileName;
            
        case MediaIdRole:
            return record.id;
            
        case FilePathRole:
            return record.filePath;
            
        case ThumbnailPathRole:
            return record.thumbnailPath;
            
        case MediaTypeRole:
            return static_cast<int>(record.mediaType);
            
        case TagsRole: {
            if (!m_tagsCache.contains(record.id)) {
                m_tagsCache[record.id] = m_db->getMediaTags(record.id);
            }
            return m_tagsCache.value(record.id);
        }
            
        case IsSelectedRole:
            return m_selectedIds.contains(record.id);
            
        case WidthRole:
            return record.width.has_value() ? record.width.value() : 0;
            
        case HeightRole:
            return record.height.has_value() ? record.height.value() : 0;
            
        case SizeBytesRole:
            return record.sizeBytes.has_value() ? record.sizeBytes.value() : 0;
            
        case ModifiedTimeRole:
            return record.modifiedTimeUtc.has_value() ? record.modifiedTimeUtc.value() : 0;
            
        case Qt::DecorationRole: {
            // Request async thumbnail load and return placeholder
            QPixmap thumb = m_cache->getThumbnail(record.id, record.thumbnailPath, m_thumbnailSize);
            m_cache->requestThumbnail(record.id, record.thumbnailPath, m_thumbnailSize);
            return thumb;
        }
            
        default:
            return QVariant();
    }
}

QHash<int, QByteArray> GalleryModel::roleNames() const {
    QHash<int, QByteArray> roles;
    roles[Qt::DisplayRole] = "display";
    roles[Qt::DecorationRole] = "decoration";
    roles[MediaIdRole] = "mediaId";
    roles[FilePathRole] = "filePath";
    roles[FileNameRole] = "fileName";
    roles[ThumbnailPathRole] = "thumbnailPath";
    roles[MediaTypeRole] = "mediaType";
    roles[TagsRole] = "tags";
    roles[IsSelectedRole] = "isSelected";
    roles[WidthRole] = "width";
    roles[HeightRole] = "height";
    roles[SizeBytesRole] = "sizeBytes";
    roles[ModifiedTimeRole] = "modifiedTime";
    return roles;
}

void GalleryModel::refresh() {
    beginResetModel();
    
    m_cache->cancelPendingRequests();
    m_records.clear();
    m_idToRow.clear();
    m_tagsCache.clear();
    
    auto result = m_db->queryMedia(
        m_filterTags,
        m_searchText,
        10000,  // Load all for now (pagination can be added later)
        0,
        "modified_time_utc DESC, id DESC",
        m_rootDir,
        m_tagsMatchAll
    );
    
    m_records = result.records;
    m_totalCount = result.totalCount;
    
    for (int i = 0; i < m_records.size(); ++i) {
        m_idToRow[m_records[i].id] = i;
    }
    
    endResetModel();
    emit dataRefreshed();
}

void GalleryModel::setFilter(const QStringList& tags, const QString& searchText, bool tagsMatchAll) {
    m_filterTags = tags;
    m_searchText = searchText;
    m_tagsMatchAll = tagsMatchAll;
    refresh();
}

void GalleryModel::setRootDir(const QString& rootDir) {
    m_rootDir = rootDir;
    refresh();
}

void GalleryModel::select(qint64 mediaId, bool selected) {
    if (selected) {
        m_selectedIds.insert(mediaId);
    } else {
        m_selectedIds.remove(mediaId);
    }
    
    int row = rowForMediaId(mediaId);
    if (row >= 0) {
        QModelIndex idx = index(row);
        emit dataChanged(idx, idx, {IsSelectedRole});
    }
    
    emit selectionChanged();
}

void GalleryModel::toggleSelection(qint64 mediaId) {
    select(mediaId, !m_selectedIds.contains(mediaId));
}

void GalleryModel::selectRange(qint64 startId, qint64 endId) {
    int startRow = rowForMediaId(startId);
    int endRow = rowForMediaId(endId);
    
    if (startRow < 0 || endRow < 0) return;
    
    if (startRow > endRow) std::swap(startRow, endRow);
    
    for (int row = startRow; row <= endRow; ++row) {
        m_selectedIds.insert(m_records[row].id);
    }
    
    QModelIndex startIdx = index(startRow);
    QModelIndex endIdx = index(endRow);
    emit dataChanged(startIdx, endIdx, {IsSelectedRole});
    emit selectionChanged();
}

void GalleryModel::selectAll() {
    for (const auto& record : m_records) {
        m_selectedIds.insert(record.id);
    }
    
    if (!m_records.isEmpty()) {
        emit dataChanged(index(0), index(m_records.size() - 1), {IsSelectedRole});
    }
    emit selectionChanged();
}

void GalleryModel::clearSelection() {
    QSet<qint64> oldSelection = m_selectedIds;
    m_selectedIds.clear();
    
    for (qint64 id : oldSelection) {
        int row = rowForMediaId(id);
        if (row >= 0) {
            QModelIndex idx = index(row);
            emit dataChanged(idx, idx, {IsSelectedRole});
        }
    }
    
    emit selectionChanged();
}

QSet<qint64> GalleryModel::selectedIds() const {
    return m_selectedIds;
}

bool GalleryModel::isSelected(qint64 mediaId) const {
    return m_selectedIds.contains(mediaId);
}

int GalleryModel::selectionCount() const {
    return m_selectedIds.size();
}

std::optional<MediaRecord> GalleryModel::getRecord(qint64 mediaId) const {
    int row = rowForMediaId(mediaId);
    if (row >= 0) {
        return m_records[row];
    }
    return std::nullopt;
}

MediaRecord GalleryModel::recordAt(int row) const {
    if (row >= 0 && row < m_records.size()) {
        return m_records[row];
    }
    return MediaRecord();
}

int GalleryModel::rowForMediaId(qint64 mediaId) const {
    return m_idToRow.value(mediaId, -1);
}

int GalleryModel::totalCount() const {
    return m_totalCount;
}

int GalleryModel::thumbnailSize() const {
    return m_thumbnailSize;
}

void GalleryModel::setThumbnailSize(int size) {
    if (m_thumbnailSize != size) {
        m_thumbnailSize = size;
        m_cache->clear();
        // Notify all rows that decoration changed
        if (!m_records.isEmpty()) {
            emit dataChanged(index(0), index(m_records.size() - 1), {Qt::DecorationRole});
        }
    }
}

void GalleryModel::onThumbnailLoaded(qint64 mediaId, const QPixmap& thumbnail) {
    Q_UNUSED(thumbnail);
    int row = rowForMediaId(mediaId);
    if (row >= 0) {
        QModelIndex idx = index(row);
        emit dataChanged(idx, idx, {Qt::DecorationRole});
    }
}

void GalleryModel::onTagsChanged() {
    m_tagsCache.clear();
    if (!m_records.isEmpty()) {
        emit dataChanged(index(0), index(m_records.size() - 1), {TagsRole});
    }
}

} // namespace KeyTagger

