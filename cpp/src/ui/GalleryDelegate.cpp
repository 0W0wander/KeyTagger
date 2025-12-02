#include "GalleryDelegate.h"
#include "GalleryModel.h"
#include "ThumbnailCache.h"
#include <QPainter>
#include <QPainterPath>
#include <QApplication>
#include <QCryptographicHash>

namespace KeyTagger {

GalleryDelegate::GalleryDelegate(ThumbnailCache* cache, QObject* parent)
    : QStyledItemDelegate(parent)
    , m_cache(cache)
{
}

void GalleryDelegate::paint(QPainter* painter, const QStyleOptionViewItem& option,
                            const QModelIndex& index) const {
    if (!index.isValid()) return;
    
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing);
    
    // Get data
    QPixmap thumbnail = index.data(Qt::DecorationRole).value<QPixmap>();
    QString fileName = index.data(GalleryModel::FileNameRole).toString();
    QStringList tags = index.data(GalleryModel::TagsRole).toStringList();
    bool isSelected = index.data(GalleryModel::IsSelectedRole).toBool();
    int mediaType = index.data(GalleryModel::MediaTypeRole).toInt();
    
    bool isVideo = (mediaType == static_cast<int>(MediaType::Video));
    bool isAudio = (mediaType == static_cast<int>(MediaType::Audio));
    
    // Calculate layout
    QRect itemRect = option.rect;
    int padding = 6;
    int cardPadding = 8;
    
    // Card background
    QRect cardRect = itemRect.adjusted(padding, padding, -padding, -padding);
    
    QColor cardBg = m_darkMode ? QColor(31, 41, 55) : QColor(255, 255, 255);
    QColor cardHoverBg = m_darkMode ? QColor(39, 50, 68) : QColor(243, 244, 246);
    QColor selectedBg = m_darkMode ? QColor(29, 78, 216) : QColor(37, 99, 235);
    
    // Draw card background with rounded corners
    QPainterPath cardPath;
    cardPath.addRoundedRect(cardRect, 12, 12);
    
    if (isSelected) {
        painter->fillPath(cardPath, selectedBg);
    } else if (option.state & QStyle::State_MouseOver) {
        painter->fillPath(cardPath, cardHoverBg);
    } else {
        painter->fillPath(cardPath, cardBg);
    }
    
    // Thumbnail area
    QRect thumbRect = cardRect.adjusted(cardPadding, cardPadding, -cardPadding, -cardPadding);
    
    // Reserve space for filename
    int fileNameHeight = m_showFileName ? 28 : 0;
    thumbRect.setHeight(thumbRect.height() - fileNameHeight);
    
    // Paint thumbnail
    if (!thumbnail.isNull()) {
        paintThumbnail(painter, thumbRect, thumbnail, isSelected, isVideo, isAudio);
    }
    
    // Paint tags on thumbnail
    if (m_showTags && !tags.isEmpty()) {
        paintTags(painter, thumbRect, tags);
    }
    
    // Paint filename
    if (m_showFileName) {
        QRect fileNameRect = cardRect;
        fileNameRect.setTop(thumbRect.bottom() + 4);
        fileNameRect.setHeight(fileNameHeight - 4);
        fileNameRect = fileNameRect.adjusted(cardPadding, 0, -cardPadding, 0);
        paintFileName(painter, fileNameRect, fileName);
    }
    
    painter->restore();
}

void GalleryDelegate::paintThumbnail(QPainter* painter, const QRect& rect,
                                     const QPixmap& thumbnail, bool isSelected,
                                     bool isVideo, bool isAudio) const {
    // Create rounded clip path
    QPainterPath clipPath;
    clipPath.addRoundedRect(rect, 8, 8);
    
    painter->save();
    painter->setClipPath(clipPath);
    
    // Scale and center thumbnail
    QPixmap scaled = thumbnail.scaled(rect.size(), Qt::KeepAspectRatio, Qt::SmoothTransformation);
    int x = rect.x() + (rect.width() - scaled.width()) / 2;
    int y = rect.y() + (rect.height() - scaled.height()) / 2;
    
    painter->drawPixmap(x, y, scaled);
    
    // Draw video overlay
    if (isVideo) {
        QPixmap overlay = ThumbnailCache::createVideoOverlay(qMin(rect.width(), rect.height()) / 3);
        int ox = rect.x() + (rect.width() - overlay.width()) / 2;
        int oy = rect.y() + (rect.height() - overlay.height()) / 2;
        painter->drawPixmap(ox, oy, overlay);
    }
    
    // Selection border
    if (isSelected) {
        painter->setPen(QPen(QColor(59, 130, 246), 3));
        painter->setBrush(Qt::NoBrush);
        painter->drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8);
    }
    
    painter->restore();
}

void GalleryDelegate::paintTags(QPainter* painter, const QRect& rect,
                                const QStringList& tags) const {
    if (tags.isEmpty()) return;
    
    painter->save();
    
    QFont tagFont = painter->font();
    tagFont.setPixelSize(10);
    tagFont.setBold(true);
    painter->setFont(tagFont);
    
    int x = rect.left() + 4;
    int y = rect.bottom() - 4;
    int tagHeight = 18;
    int tagPadding = 6;
    int maxTags = 3; // Show at most 3 tags
    
    QFontMetrics fm(tagFont);
    
    for (int i = 0; i < qMin(tags.size(), maxTags); ++i) {
        const QString& tag = tags[i];
        QColor bgColor = getTagColor(tag);
        QColor textColor = getContrastingTextColor(bgColor);
        
        int textWidth = fm.horizontalAdvance(tag);
        int tagWidth = textWidth + tagPadding * 2;
        
        // Check if tag fits
        if (x + tagWidth > rect.right() - 4) {
            // Show "+N" indicator
            if (i < tags.size()) {
                QString more = QString("+%1").arg(tags.size() - i);
                int moreWidth = fm.horizontalAdvance(more) + tagPadding * 2;
                
                QRect moreRect(x, y - tagHeight, moreWidth, tagHeight);
                painter->fillRect(moreRect, QColor(100, 100, 100, 200));
                painter->setPen(Qt::white);
                painter->drawText(moreRect, Qt::AlignCenter, more);
            }
            break;
        }
        
        QRect tagRect(x, y - tagHeight, tagWidth, tagHeight);
        
        // Draw tag background with slight transparency
        QColor bgWithAlpha = bgColor;
        bgWithAlpha.setAlpha(230);
        
        QPainterPath tagPath;
        tagPath.addRoundedRect(tagRect, 4, 4);
        painter->fillPath(tagPath, bgWithAlpha);
        
        // Draw tag text
        painter->setPen(textColor);
        painter->drawText(tagRect, Qt::AlignCenter, tag);
        
        x += tagWidth + 4;
    }
    
    painter->restore();
}

void GalleryDelegate::paintFileName(QPainter* painter, const QRect& rect,
                                    const QString& fileName) const {
    painter->save();
    
    QFont nameFont = painter->font();
    nameFont.setPixelSize(11);
    painter->setFont(nameFont);
    
    QColor textColor = m_darkMode ? QColor(243, 244, 246) : QColor(17, 24, 39);
    painter->setPen(textColor);
    
    QFontMetrics fm(nameFont);
    QString elidedText = fm.elidedText(fileName, Qt::ElideMiddle, rect.width());
    
    painter->drawText(rect, Qt::AlignCenter, elidedText);
    
    painter->restore();
}

QSize GalleryDelegate::sizeHint(const QStyleOptionViewItem& option,
                                const QModelIndex& index) const {
    Q_UNUSED(option);
    Q_UNUSED(index);
    
    int fileNameHeight = m_showFileName ? 28 : 0;
    int cardPadding = 8;
    int itemPadding = 6;
    
    int size = m_thumbnailSize + (cardPadding * 2) + (itemPadding * 2) + fileNameHeight;
    return QSize(size, size);
}

void GalleryDelegate::setThumbnailSize(int size) {
    m_thumbnailSize = size;
}

int GalleryDelegate::thumbnailSize() const {
    return m_thumbnailSize;
}

void GalleryDelegate::setDarkMode(bool dark) {
    m_darkMode = dark;
}

bool GalleryDelegate::isDarkMode() const {
    return m_darkMode;
}

void GalleryDelegate::setShowTags(bool show) {
    m_showTags = show;
}

bool GalleryDelegate::showTags() const {
    return m_showTags;
}

void GalleryDelegate::setShowFileName(bool show) {
    m_showFileName = show;
}

bool GalleryDelegate::showFileName() const {
    return m_showFileName;
}

QColor GalleryDelegate::getTagColor(const QString& tagName) const {
    if (m_tagColors.contains(tagName)) {
        return m_tagColors[tagName];
    }
    
    // Generate consistent color from tag name hash
    QByteArray hash = QCryptographicHash::hash(tagName.toUtf8(), QCryptographicHash::Md5);
    quint32 hashInt = qFromBigEndian<quint32>(reinterpret_cast<const uchar*>(hash.constData()));
    
    int r = 100 + (hashInt % 156);
    int g = 100 + ((hashInt >> 8) % 156);
    int b = 100 + ((hashInt >> 16) % 156);
    
    QColor color(r, g, b);
    m_tagColors[tagName] = color;
    return color;
}

QColor GalleryDelegate::getContrastingTextColor(const QColor& bgColor) const {
    // Calculate relative luminance
    double luminance = 0.299 * bgColor.red() + 0.587 * bgColor.green() + 0.114 * bgColor.blue();
    return luminance > 186 ? Qt::black : Qt::white;
}

} // namespace KeyTagger

