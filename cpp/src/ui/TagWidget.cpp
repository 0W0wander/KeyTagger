#include "TagWidget.h"
#include <QHBoxLayout>
#include <QPushButton>
#include <QCryptographicHash>
#include <QtEndian>

namespace KeyTagger {

TagWidget::TagWidget(QWidget* parent)
    : QWidget(parent)
{
    m_layout = new QHBoxLayout(this);
    m_layout->setContentsMargins(0, 0, 0, 0);
    m_layout->setSpacing(8);
    m_layout->addStretch();
}

void TagWidget::setTags(const QStringList& tags) {
    m_tags = tags;
    rebuildTags();
}

QStringList TagWidget::tags() const {
    return m_tags;
}

void TagWidget::setDarkMode(bool dark) {
    m_darkMode = dark;
    rebuildTags();
}

void TagWidget::rebuildTags() {
    // Clear existing tag widgets
    QLayoutItem* item;
    while ((item = m_layout->takeAt(0)) != nullptr) {
        if (item->widget()) {
            delete item->widget();
        }
        delete item;
    }
    
    for (const QString& tag : m_tags) {
        QPushButton* badge = new QPushButton(tag, this);
        badge->setCursor(Qt::PointingHandCursor);
        badge->setFlat(true);
        
        QColor bgColor = getTagColor(tag);
        QColor textColor = getContrastingTextColor(bgColor);
        QColor darkerBg = bgColor.darker(120);
        
        badge->setStyleSheet(QString(
            "QPushButton {"
            "  background-color: %1;"
            "  color: %2;"
            "  border: none;"
            "  border-radius: 8px;"
            "  padding: 8px 16px;"
            "  font-size: 13px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: %3;"
            "}"
        ).arg(bgColor.name())
         .arg(textColor.name())
         .arg(darkerBg.name()));
        
        connect(badge, &QPushButton::clicked, this, [this, tag]() {
            emit tagClicked(tag);
        });
        
        m_layout->insertWidget(m_layout->count(), badge);
    }
    
    m_layout->addStretch();
}

QColor TagWidget::getTagColor(const QString& tagName) const {
    QByteArray hash = QCryptographicHash::hash(tagName.toUtf8(), QCryptographicHash::Md5);
    quint32 hashInt = qFromBigEndian<quint32>(reinterpret_cast<const uchar*>(hash.constData()));
    
    int r = 100 + (hashInt % 156);
    int g = 100 + ((hashInt >> 8) % 156);
    int b = 100 + ((hashInt >> 16) % 156);
    
    return QColor(r, g, b);
}

QColor TagWidget::getContrastingTextColor(const QColor& bgColor) const {
    double luminance = 0.299 * bgColor.red() + 0.587 * bgColor.green() + 0.114 * bgColor.blue();
    return luminance > 186 ? Qt::black : Qt::white;
}

} // namespace KeyTagger

