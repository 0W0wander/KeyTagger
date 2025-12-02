#pragma once

#include <QStyledItemDelegate>
#include <QPixmap>
#include <QHash>

namespace KeyTagger {

class ThumbnailCache;

/**
 * GalleryDelegate - Custom painting for gallery items
 * 
 * Features:
 * - Rounded corners on thumbnails
 * - Selection highlighting
 * - Tag badges on thumbnails
 * - Filename display
 * - Video/audio type indicators
 */
class GalleryDelegate : public QStyledItemDelegate {
    Q_OBJECT

public:
    explicit GalleryDelegate(ThumbnailCache* cache, QObject* parent = nullptr);
    
    void paint(QPainter* painter, const QStyleOptionViewItem& option,
               const QModelIndex& index) const override;
    
    QSize sizeHint(const QStyleOptionViewItem& option,
                   const QModelIndex& index) const override;
    
    // Configuration
    void setThumbnailSize(int size);
    int thumbnailSize() const;
    
    void setDarkMode(bool dark);
    bool isDarkMode() const;
    
    void setShowTags(bool show);
    bool showTags() const;
    
    void setShowFileName(bool show);
    bool showFileName() const;

private:
    void paintThumbnail(QPainter* painter, const QRect& rect, 
                        const QPixmap& thumbnail, bool isSelected,
                        bool isVideo, bool isAudio) const;
    void paintTags(QPainter* painter, const QRect& rect, 
                   const QStringList& tags) const;
    void paintFileName(QPainter* painter, const QRect& rect,
                       const QString& fileName) const;
    
    QColor getTagColor(const QString& tagName) const;
    QColor getContrastingTextColor(const QColor& bgColor) const;
    
    ThumbnailCache* m_cache;
    int m_thumbnailSize = 320;
    bool m_darkMode = true;
    bool m_showTags = true;
    bool m_showFileName = true;
    
    // Tag color cache
    mutable QHash<QString, QColor> m_tagColors;
};

} // namespace KeyTagger

