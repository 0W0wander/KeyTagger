#include "HotkeyManager.h"
#include <QKeyEvent>

namespace KeyTagger {

HotkeyManager::HotkeyManager(QObject* parent)
    : QObject(parent)
{
}

void HotkeyManager::setEnabled(bool enabled) {
    m_enabled = enabled;
}

bool HotkeyManager::isEnabled() const {
    return m_enabled;
}

void HotkeyManager::setHotkeys(const QHash<QString, QString>& hotkeys) {
    m_hotkeys = hotkeys;
}

bool HotkeyManager::processKeyEvent(Qt::Key key, Qt::KeyboardModifiers modifiers) {
    if (!m_enabled) return false;
    
    QString keyStr = keyToString(key, modifiers);
    
    // Check hotkeys
    if (m_hotkeys.contains(keyStr)) {
        emit hotkeyPressed(m_hotkeys[keyStr]);
        return true;
    }
    
    // Check navigation keys
    if (keyStr == m_prevKey) {
        emit prevPressed();
        return true;
    }
    
    if (keyStr == m_nextKey) {
        emit nextPressed();
        return true;
    }
    
    return false;
}

void HotkeyManager::setTaggingNavKeys(const QString& prevKey, const QString& nextKey) {
    m_prevKey = prevKey.toLower();
    m_nextKey = nextKey.toLower();
}

bool HotkeyManager::isPrevKey(Qt::Key key, Qt::KeyboardModifiers modifiers) const {
    return keyToString(key, modifiers) == m_prevKey;
}

bool HotkeyManager::isNextKey(Qt::Key key, Qt::KeyboardModifiers modifiers) const {
    return keyToString(key, modifiers) == m_nextKey;
}

QString HotkeyManager::keyToString(Qt::Key key, Qt::KeyboardModifiers modifiers) const {
    QStringList parts;
    
    if (modifiers & Qt::ControlModifier) {
        parts << "ctrl";
    }
    if (modifiers & Qt::AltModifier) {
        parts << "alt";
    }
    if (modifiers & Qt::ShiftModifier) {
        parts << "shift";
    }
    
    // Get key name
    QString keyName;
    
    if (key >= Qt::Key_A && key <= Qt::Key_Z) {
        keyName = QChar('a' + (key - Qt::Key_A));
    } else if (key >= Qt::Key_0 && key <= Qt::Key_9) {
        keyName = QChar('0' + (key - Qt::Key_0));
    } else if (key >= Qt::Key_F1 && key <= Qt::Key_F12) {
        keyName = QString("f%1").arg(key - Qt::Key_F1 + 1);
    } else {
        switch (key) {
            case Qt::Key_Space: keyName = "space"; break;
            case Qt::Key_Return:
            case Qt::Key_Enter: keyName = "enter"; break;
            case Qt::Key_Tab: keyName = "tab"; break;
            case Qt::Key_Escape: keyName = "escape"; break;
            case Qt::Key_Backspace: keyName = "backspace"; break;
            case Qt::Key_Delete: keyName = "delete"; break;
            case Qt::Key_Left: keyName = "left"; break;
            case Qt::Key_Right: keyName = "right"; break;
            case Qt::Key_Up: keyName = "up"; break;
            case Qt::Key_Down: keyName = "down"; break;
            default: return QString();
        }
    }
    
    parts << keyName;
    return parts.join("+");
}

} // namespace KeyTagger

