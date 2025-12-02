#include "TagInputWidget.h"
#include "Database.h"
#include <QKeyEvent>
#include <QFocusEvent>
#include <QApplication>
#include <QScrollBar>
#include <QTimer>

namespace KeyTagger {

TagInputWidget::TagInputWidget(Database* db, QWidget* parent)
    : QLineEdit(parent)
    , m_db(db)
{
    setPlaceholderText("Type a tag and press Enter...");
    
    // Create suggestions popup
    m_suggestionsPopup = new QListWidget();
    m_suggestionsPopup->setWindowFlags(Qt::Popup);
    m_suggestionsPopup->setFocusPolicy(Qt::NoFocus);
    m_suggestionsPopup->setMouseTracking(true);
    m_suggestionsPopup->installEventFilter(this);
    
    connect(this, &QLineEdit::textChanged, this, &TagInputWidget::onTextChanged);
    connect(m_suggestionsPopup, &QListWidget::itemClicked, 
            this, &TagInputWidget::onSuggestionClicked);
    
    setDarkMode(true);
}

void TagInputWidget::setDarkMode(bool dark) {
    m_darkMode = dark;
    
    if (dark) {
        setStyleSheet(R"(
            QLineEdit {
                background-color: #1a202c;
                border: 2px solid #1e1533;
                border-radius: 8px;
                padding: 12px;
                color: #f3f4f6;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #2d1b4e;
            }
        )");
        
        m_suggestionsPopup->setStyleSheet(R"(
            QListWidget {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 4px;
                color: #f3f4f6;
            }
            QListWidget::item {
                padding: 8px;
            }
            QListWidget::item:hover {
                background-color: #374151;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
                color: #ffffff;
            }
        )");
    } else {
        setStyleSheet(R"(
            QLineEdit {
                background-color: #ffffff;
                border: 2px solid #d1d5db;
                border-radius: 8px;
                padding: 12px;
                color: #111827;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #4c1d95;
            }
        )");
        
        m_suggestionsPopup->setStyleSheet(R"(
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                color: #111827;
            }
            QListWidget::item:hover {
                background-color: #f3f4f6;
            }
            QListWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
        )");
    }
}

bool TagInputWidget::eventFilter(QObject* obj, QEvent* event) {
    if (obj == m_suggestionsPopup) {
        if (event->type() == QEvent::MouseButtonPress) {
            QMouseEvent* me = static_cast<QMouseEvent*>(event);
            if (!m_suggestionsPopup->rect().contains(me->pos())) {
                hideSuggestions();
            }
        }
    }
    return QLineEdit::eventFilter(obj, event);
}

void TagInputWidget::keyPressEvent(QKeyEvent* event) {
    if (m_suggestionsPopup->isVisible()) {
        switch (event->key()) {
            case Qt::Key_Up:
                moveSuggestionSelection(-1);
                event->accept();
                return;
                
            case Qt::Key_Down:
                moveSuggestionSelection(1);
                event->accept();
                return;
                
            case Qt::Key_Tab:
            case Qt::Key_Return:
            case Qt::Key_Enter:
                if (m_suggestionsPopup->currentItem()) {
                    acceptCurrentSuggestion();
                    event->accept();
                    return;
                }
                break;
                
            case Qt::Key_Escape:
                hideSuggestions();
                event->accept();
                return;
        }
    }
    
    if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
        QString tag = text().trimmed().toLower();
        if (!tag.isEmpty()) {
            emit tagSubmitted(tag);
            clear();
            hideSuggestions();
        }
        event->accept();
        return;
    }
    
    QLineEdit::keyPressEvent(event);
}

void TagInputWidget::focusOutEvent(QFocusEvent* event) {
    // Delay hiding to allow click on popup
    QTimer::singleShot(100, this, [this]() {
        if (!m_suggestionsPopup->underMouse()) {
            hideSuggestions();
        }
    });
    
    QLineEdit::focusOutEvent(event);
}

void TagInputWidget::onTextChanged(const QString& text) {
    QString prefix = text.trimmed().toLower();
    
    if (prefix.isEmpty()) {
        hideSuggestions();
        return;
    }
    
    updateSuggestions(prefix);
}

void TagInputWidget::onSuggestionClicked(QListWidgetItem* item) {
    if (item) {
        setText(item->text());
        hideSuggestions();
        setFocus();
    }
}

void TagInputWidget::showSuggestions() {
    if (m_suggestionsPopup->count() == 0) {
        hideSuggestions();
        return;
    }
    
    // Position below the input
    QPoint pos = mapToGlobal(QPoint(0, height()));
    m_suggestionsPopup->move(pos);
    m_suggestionsPopup->setFixedWidth(width());
    
    int itemHeight = 30;
    int visibleItems = qMin(m_suggestionsPopup->count(), 6);
    m_suggestionsPopup->setFixedHeight(itemHeight * visibleItems + 4);
    
    m_suggestionsPopup->show();
}

void TagInputWidget::hideSuggestions() {
    m_suggestionsPopup->hide();
    m_suggestionsPopup->clear();
}

void TagInputWidget::updateSuggestions(const QString& prefix) {
    m_suggestionsPopup->clear();
    
    QStringList allTags = m_db->allTags();
    
    for (const QString& tag : allTags) {
        if (tag.startsWith(prefix) && tag != prefix) {
            m_suggestionsPopup->addItem(tag);
        }
    }
    
    // Also add partial matches
    for (const QString& tag : allTags) {
        if (tag.contains(prefix) && !tag.startsWith(prefix)) {
            m_suggestionsPopup->addItem(tag);
        }
    }
    
    if (m_suggestionsPopup->count() > 0) {
        showSuggestions();
    } else {
        hideSuggestions();
    }
}

void TagInputWidget::acceptCurrentSuggestion() {
    QListWidgetItem* item = m_suggestionsPopup->currentItem();
    if (item) {
        setText(item->text());
        hideSuggestions();
    }
}

void TagInputWidget::moveSuggestionSelection(int delta) {
    int currentRow = m_suggestionsPopup->currentRow();
    int newRow = currentRow + delta;
    
    if (newRow < 0) {
        newRow = m_suggestionsPopup->count() - 1;
    } else if (newRow >= m_suggestionsPopup->count()) {
        newRow = 0;
    }
    
    m_suggestionsPopup->setCurrentRow(newRow);
}

} // namespace KeyTagger

