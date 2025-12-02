#pragma once

#include <QLineEdit>
#include <QListWidget>

namespace KeyTagger {

class Database;

/**
 * TagInputWidget - Text input with autocomplete for tags
 * 
 * Features:
 * - Autocomplete dropdown from existing tags
 * - Arrow key navigation
 * - Tab to accept suggestion
 */
class TagInputWidget : public QLineEdit {
    Q_OBJECT

public:
    explicit TagInputWidget(Database* db, QWidget* parent = nullptr);
    
    void setDarkMode(bool dark);

signals:
    void tagSubmitted(const QString& tag);

protected:
    bool eventFilter(QObject* obj, QEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void focusOutEvent(QFocusEvent* event) override;

private slots:
    void onTextChanged(const QString& text);
    void onSuggestionClicked(QListWidgetItem* item);

private:
    void showSuggestions();
    void hideSuggestions();
    void updateSuggestions(const QString& prefix);
    void acceptCurrentSuggestion();
    void moveSuggestionSelection(int delta);
    
    Database* m_db;
    QListWidget* m_suggestionsPopup = nullptr;
    bool m_darkMode = true;
};

} // namespace KeyTagger

