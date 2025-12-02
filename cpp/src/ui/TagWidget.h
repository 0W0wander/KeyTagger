#pragma once

#include <QWidget>
#include <QStringList>

class QHBoxLayout;

namespace KeyTagger {

/**
 * TagWidget - Displays tags as colored badges
 * 
 * Used in tagging mode to show current media's tags
 */
class TagWidget : public QWidget {
    Q_OBJECT

public:
    explicit TagWidget(QWidget* parent = nullptr);
    
    void setTags(const QStringList& tags);
    QStringList tags() const;
    
    void setDarkMode(bool dark);

signals:
    void tagClicked(const QString& tag);
    void tagRemoveClicked(const QString& tag);

private:
    void rebuildTags();
    QColor getTagColor(const QString& tagName) const;
    QColor getContrastingTextColor(const QColor& bgColor) const;
    
    QStringList m_tags;
    QHBoxLayout* m_layout = nullptr;
    bool m_darkMode = true;
};

} // namespace KeyTagger

