#pragma once

#include <QListView>
#include <QSet>

namespace KeyTagger {

class GalleryModel;
class GalleryDelegate;
class ThumbnailCache;

/**
 * GalleryView - Efficient thumbnail grid view
 * 
 * Key features (inspired by digiKam):
 * - Uses QListView with IconMode for efficient virtual scrolling
 * - Only renders visible items (solves 500+ widget problem)
 * - Async thumbnail loading with placeholder support
 * - Multi-selection with Ctrl/Shift modifiers
 * - Keyboard navigation
 * - Context menu support
 */
class GalleryView : public QListView {
    Q_OBJECT

public:
    explicit GalleryView(QWidget* parent = nullptr);
    
    void setModel(GalleryModel* model);
    GalleryModel* galleryModel() const;
    
    void setThumbnailCache(ThumbnailCache* cache);
    void setThumbnailSize(int size);
    int thumbnailSize() const;
    
    void setDarkMode(bool dark);
    
    // Selection helpers
    QSet<qint64> selectedMediaIds() const;
    void selectMediaId(qint64 id);
    void selectAll();
    void clearSelection();

signals:
    void mediaActivated(qint64 mediaId);
    void mediaSelected(qint64 mediaId);
    void selectionChanged();
    void contextMenuRequested(qint64 mediaId, const QPoint& globalPos);

protected:
    void mousePressEvent(QMouseEvent* event) override;
    void mouseDoubleClickEvent(QMouseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void contextMenuEvent(QContextMenuEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;

private slots:
    void onClicked(const QModelIndex& index);
    void onDoubleClicked(const QModelIndex& index);

private:
    void updateGridSize();
    qint64 mediaIdAt(const QModelIndex& index) const;
    
    GalleryModel* m_model = nullptr;
    GalleryDelegate* m_delegate = nullptr;
    ThumbnailCache* m_cache = nullptr;
    
    int m_thumbnailSize = 320;
    qint64 m_anchorId = 0; // For shift-click range selection
};

} // namespace KeyTagger

