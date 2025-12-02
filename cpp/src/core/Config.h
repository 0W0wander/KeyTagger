#pragma once

#include <QObject>
#include <QString>
#include <QHash>
#include <QVariant>
#include <QJsonObject>

namespace KeyTagger {

/**
 * Config - Application configuration management
 * 
 * Handles persistent storage of:
 * - Hotkey mappings (key -> tag)
 * - UI preferences (dark mode, thumbnail size, etc.)
 * - Last used directories
 * - Tagging navigation keys
 */
class Config : public QObject {
    Q_OBJECT

public:
    static Config& instance();
    
    // File path
    void setConfigPath(const QString& path);
    QString configPath() const;
    
    // Load/Save
    bool load();
    bool save();
    
    // Hotkeys
    QHash<QString, QString> hotkeys() const;
    void setHotkeys(const QHash<QString, QString>& hotkeys);
    void setHotkey(const QString& key, const QString& tag);
    void removeHotkey(const QString& key);
    QString tagForHotkey(const QString& key) const;
    
    // UI Settings
    bool darkMode() const;
    void setDarkMode(bool enabled);
    
    int thumbnailSize() const;
    void setThumbnailSize(int size);
    
    // Navigation
    QString lastRootDir() const;
    void setLastRootDir(const QString& path);
    
    QString taggingPrevKey() const;
    QString taggingNextKey() const;
    void setTaggingNavKeys(const QString& prevKey, const QString& nextKey);
    
    // Window geometry
    QByteArray windowGeometry() const;
    void setWindowGeometry(const QByteArray& geometry);
    
    QByteArray windowState() const;
    void setWindowState(const QByteArray& state);

signals:
    void configChanged();
    void hotkeysChanged();
    void themeChanged(bool darkMode);

private:
    Config();
    ~Config() = default;
    Config(const Config&) = delete;
    Config& operator=(const Config&) = delete;
    
    QString normalizeKey(const QString& key) const;
    
    QString m_configPath;
    QJsonObject m_data;
    
    // Cached values
    mutable QHash<QString, QString> m_hotkeysCache;
    mutable bool m_hotkeysCacheDirty = true;
};

} // namespace KeyTagger

