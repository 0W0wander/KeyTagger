#include "GalleryView.h"
#include "GalleryModel.h"
#include "GalleryDelegate.h"
#include "ThumbnailCache.h"
#include <QMouseEvent>
#include <QKeyEvent>
#include <QContextMenuEvent>
#include <QScrollBar>
#include <QApplication>
#include <QDebug>

namespace KeyTagger {

GalleryView::GalleryView(QWidget* parent)
    : QListView(parent)
{
    // Configure for efficient grid display
    setViewMode(QListView::IconMode);
    setFlow(QListView::LeftToRight);
    setWrapping(true);
    setResizeMode(QListView::Adjust);
    setMovement(QListView::Static);
    setSelectionMode(QAbstractItemView::ExtendedSelection);
    setSelectionBehavior(QAbstractItemView::SelectItems);
    setUniformItemSizes(true);
    
    // Performance optimizations
    setLayoutMode(QListView::Batched);
    setBatchSize(50);
    
    // Enable mouse tracking for hover effects
    setMouseTracking(true);
    
    // Scrolling
    setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    verticalScrollBar()->setSingleStep(20);
    
    // Spacing
    setSpacing(4);
    
    connect(this, &QListView::clicked, this, &GalleryView::onClicked);
    connect(this, &QListView::doubleClicked, this, &GalleryView::onDoubleClicked);
}

void GalleryView::setModel(GalleryModel* model) {
    m_model = model;
    QListView::setModel(model);
    
    if (m_model) {
        connect(m_model, &GalleryModel::selectionChanged, 
                this, &GalleryView::selectionChanged);
    }
    
    updateGridSize();
}

GalleryModel* GalleryView::galleryModel() const {
    return m_model;
}

void GalleryView::setThumbnailCache(ThumbnailCache* cache) {
    m_cache = cache;
    
    if (!m_delegate) {
        m_delegate = new GalleryDelegate(cache, this);
        setItemDelegate(m_delegate);
    }
}

void GalleryView::setThumbnailSize(int size) {
    m_thumbnailSize = size;
    
    if (m_delegate) {
        m_delegate->setThumbnailSize(size);
    }
    
    if (m_model) {
        m_model->setThumbnailSize(size);
    }
    
    updateGridSize();
}

int GalleryView::thumbnailSize() const {
    return m_thumbnailSize;
}

void GalleryView::setDarkMode(bool dark) {
    if (m_delegate) {
        m_delegate->setDarkMode(dark);
    }
    
    // Update view colors
    QPalette pal = palette();
    if (dark) {
        pal.setColor(QPalette::Base, QColor(15, 23, 42));
        pal.setColor(QPalette::AlternateBase, QColor(15, 23, 42));
    } else {
        pal.setColor(QPalette::Base, QColor(246, 247, 251));
        pal.setColor(QPalette::AlternateBase, QColor(246, 247, 251));
    }
    setPalette(pal);
    
    viewport()->update();
}

QSet<qint64> GalleryView::selectedMediaIds() const {
    if (m_model) {
        return m_model->selectedIds();
    }
    return QSet<qint64>();
}

void GalleryView::selectMediaId(qint64 id) {
    if (m_model) {
        m_model->clearSelection();
        m_model->select(id, true);
        m_anchorId = id;
        
        // Scroll to item
        int row = m_model->rowForMediaId(id);
        if (row >= 0) {
            scrollTo(m_model->index(row));
        }
    }
}

void GalleryView::selectAll() {
    if (m_model) {
        m_model->selectAll();
    }
}

void GalleryView::clearSelection() {
    if (m_model) {
        m_model->clearSelection();
    }
}

void GalleryView::mousePressEvent(QMouseEvent* event) {
    QModelIndex index = indexAt(event->pos());
    
    if (!index.isValid()) {
        // Click on empty space - clear selection
        if (!(event->modifiers() & (Qt::ControlModifier | Qt::ShiftModifier))) {
            if (m_model) {
                m_model->clearSelection();
            }
        }
        QListView::mousePressEvent(event);
        return;
    }
    
    qint64 mediaId = mediaIdAt(index);
    
    if (event->modifiers() & Qt::ControlModifier) {
        // Ctrl+click: toggle selection
        if (m_model) {
            m_model->toggleSelection(mediaId);
            m_anchorId = mediaId;
        }
    } else if (event->modifiers() & Qt::ShiftModifier) {
        // Shift+click: range selection
        if (m_model && m_anchorId > 0) {
            m_model->selectRange(m_anchorId, mediaId);
        }
    } else {
        // Normal click: single selection
        if (m_model) {
            m_model->clearSelection();
            m_model->select(mediaId, true);
            m_anchorId = mediaId;
        }
    }
    
    emit mediaSelected(mediaId);
    
    // Don't call base - we handle selection ourselves
    event->accept();
}

void GalleryView::mouseDoubleClickEvent(QMouseEvent* event) {
    QModelIndex index = indexAt(event->pos());
    if (index.isValid()) {
        qint64 mediaId = mediaIdAt(index);
        emit mediaActivated(mediaId);
    }
    event->accept();
}

void GalleryView::keyPressEvent(QKeyEvent* event) {
    if (!m_model) {
        QListView::keyPressEvent(event);
        return;
    }
    
    // Handle Ctrl+A
    if (event->key() == Qt::Key_A && (event->modifiers() & Qt::ControlModifier)) {
        m_model->selectAll();
        event->accept();
        return;
    }
    
    // Handle Escape - clear selection
    if (event->key() == Qt::Key_Escape) {
        m_model->clearSelection();
        event->accept();
        return;
    }
    
    // Handle Enter/Return - activate selected
    if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
        auto selected = m_model->selectedIds();
        if (!selected.isEmpty()) {
            emit mediaActivated(*selected.begin());
        }
        event->accept();
        return;
    }
    
    // Arrow navigation
    QListView::keyPressEvent(event);
}

void GalleryView::contextMenuEvent(QContextMenuEvent* event) {
    QModelIndex index = indexAt(event->pos());
    if (index.isValid()) {
        qint64 mediaId = mediaIdAt(index);
        emit contextMenuRequested(mediaId, event->globalPos());
    }
    event->accept();
}

void GalleryView::resizeEvent(QResizeEvent* event) {
    QListView::resizeEvent(event);
    updateGridSize();
}

void GalleryView::wheelEvent(QWheelEvent* event) {
    // Cancel pending thumbnail loads when scrolling fast
    if (m_cache && qAbs(event->angleDelta().y()) > 120) {
        m_cache->cancelPendingRequests();
    }
    
    QListView::wheelEvent(event);
}

void GalleryView::onClicked(const QModelIndex& index) {
    if (index.isValid()) {
        qint64 mediaId = mediaIdAt(index);
        emit mediaSelected(mediaId);
    }
}

void GalleryView::onDoubleClicked(const QModelIndex& index) {
    if (index.isValid()) {
        qint64 mediaId = mediaIdAt(index);
        emit mediaActivated(mediaId);
    }
}

void GalleryView::updateGridSize() {
    if (!m_delegate) return;
    
    QSize itemSize = m_delegate->sizeHint(QStyleOptionViewItem(), QModelIndex());
    setGridSize(itemSize);
}

qint64 GalleryView::mediaIdAt(const QModelIndex& index) const {
    if (!index.isValid()) return 0;
    return index.data(GalleryModel::MediaIdRole).toLongLong();
}

} // namespace KeyTagger

