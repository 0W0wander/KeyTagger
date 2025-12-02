#pragma once

#include <QAbstractListModel>
#include <QVector>
#include <QSet>
#include "MediaRecord.h"

namespace KeyTagger {

class Database;
class ThumbnailCache;

/**
 * GalleryModel - Data model for the gallery view
 * 
 * Uses Qt's model/view architecture for:
 * - Efficient handling of 1000+ items
 * - Virtual scrolling (only visible items are rendered)
 * - Async thumbnail loading
 * - Multi-selection support
 */
class GalleryModel : public QAbstractListModel {
    Q_OBJECT

public:
    enum Roles {
        MediaIdRole = Qt::UserRole + 1,
        FilePathRole,
        FileNameRole,
        ThumbnailPathRole,
        MediaTypeRole,
        TagsRole,
        IsSelectedRole,
        WidthRole,
        HeightRole,
        SizeBytesRole,
        ModifiedTimeRole
    };

    explicit GalleryModel(Database* db, ThumbnailCache* cache, QObject* parent = nullptr);
    
    // QAbstractListModel interface
    int rowCount(const QModelIndex& parent = QModelIndex()) const override;
    QVariant data(const QModelIndex& index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;
    
    // Data management
    void refresh();
    void setFilter(const QStringList& tags, const QString& searchText = QString(),
                   bool tagsMatchAll = true);
    void setRootDir(const QString& rootDir);
    
    // Selection
    void select(qint64 mediaId, bool selected = true);
    void toggleSelection(qint64 mediaId);
    void selectRange(qint64 startId, qint64 endId);
    void selectAll();
    void clearSelection();
    QSet<qint64> selectedIds() const;
    bool isSelected(qint64 mediaId) const;
    int selectionCount() const;
    
    // Get record by ID
    std::optional<MediaRecord> getRecord(qint64 mediaId) const;
    MediaRecord recordAt(int row) const;
    int rowForMediaId(qint64 mediaId) const;
    
    // Total count (for pagination info)
    int totalCount() const;
    
    // Thumbnail size
    int thumbnailSize() const;
    void setThumbnailSize(int size);

signals:
    void selectionChanged();
    void dataRefreshed();

public slots:
    void onThumbnailLoaded(qint64 mediaId, const QPixmap& thumbnail);
    void onTagsChanged();

private:
    void loadPage(int offset, int limit);
    
    Database* m_db;
    ThumbnailCache* m_cache;
    
    QVector<MediaRecord> m_records;
    QHash<qint64, int> m_idToRow;
    QSet<qint64> m_selectedIds;
    
    // Filter state
    QStringList m_filterTags;
    QString m_searchText;
    bool m_tagsMatchAll = true;
    QString m_rootDir;
    
    int m_totalCount = 0;
    int m_thumbnailSize = 320;
    
    // Tags cache
    mutable QHash<qint64, QStringList> m_tagsCache;
};

} // namespace KeyTagger

