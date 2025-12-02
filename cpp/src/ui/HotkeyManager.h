#pragma once

#include <QObject>
#include <QHash>
#include <QSet>

namespace KeyTagger {

/**
 * HotkeyManager - Global hotkey handling
 * 
 * Captures key events and triggers tag assignments
 */
class HotkeyManager : public QObject {
    Q_OBJECT

public:
    explicit HotkeyManager(QObject* parent = nullptr);
    
    void setEnabled(bool enabled);
    bool isEnabled() const;
    
    void setHotkeys(const QHash<QString, QString>& hotkeys);
    bool processKeyEvent(Qt::Key key, Qt::KeyboardModifiers modifiers);
    
    // Navigation keys for tagging mode
    void setTaggingNavKeys(const QString& prevKey, const QString& nextKey);
    bool isPrevKey(Qt::Key key, Qt::KeyboardModifiers modifiers) const;
    bool isNextKey(Qt::Key key, Qt::KeyboardModifiers modifiers) const;

signals:
    void hotkeyPressed(const QString& tag);
    void prevPressed();
    void nextPressed();

private:
    QString keyToString(Qt::Key key, Qt::KeyboardModifiers modifiers) const;
    
    bool m_enabled = true;
    QHash<QString, QString> m_hotkeys;
    QString m_prevKey = "a";
    QString m_nextKey = "d";
};

} // namespace KeyTagger

