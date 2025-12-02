#include "Config.h"
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QDir>
#include <QDebug>

namespace KeyTagger {

Config& Config::instance() {
    static Config instance;
    return instance;
}

Config::Config()
    : m_configPath("keytag_config.json")
{
}

void Config::setConfigPath(const QString& path) {
    m_configPath = path;
}

QString Config::configPath() const {
    return m_configPath;
}

bool Config::load() {
    QFile file(m_configPath);
    if (!file.open(QIODevice::ReadOnly)) {
        qDebug() << "Config file not found, using defaults";
        return false;
    }
    
    QJsonParseError error;
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &error);
    file.close();
    
    if (error.error != QJsonParseError::NoError) {
        qWarning() << "Failed to parse config:" << error.errorString();
        return false;
    }
    
    if (!doc.isObject()) {
        qWarning() << "Config is not a JSON object";
        return false;
    }
    
    m_data = doc.object();
    m_hotkeysCacheDirty = true;
    
    emit configChanged();
    return true;
}

bool Config::save() {
    QJsonDocument doc(m_data);
    
    QFile file(m_configPath);
    if (!file.open(QIODevice::WriteOnly)) {
        qWarning() << "Failed to open config file for writing:" << m_configPath;
        return false;
    }
    
    file.write(doc.toJson());
    file.close();
    
    return true;
}

QString Config::normalizeKey(const QString& key) const {
    return key.trimmed().toLower();
}

QHash<QString, QString> Config::hotkeys() const {
    if (m_hotkeysCacheDirty) {
        m_hotkeysCache.clear();
        
        QJsonObject hk = m_data.value("hotkeys").toObject();
        for (auto it = hk.begin(); it != hk.end(); ++it) {
            QString key = normalizeKey(it.key());
            QString tag = it.value().toString().trimmed().toLower();
            if (!key.isEmpty() && !tag.isEmpty()) {
                m_hotkeysCache[key] = tag;
            }
        }
        
        m_hotkeysCacheDirty = false;
    }
    
    return m_hotkeysCache;
}

void Config::setHotkeys(const QHash<QString, QString>& hotkeys) {
    QJsonObject hk;
    for (auto it = hotkeys.begin(); it != hotkeys.end(); ++it) {
        QString key = normalizeKey(it.key());
        QString tag = it.value().trimmed().toLower();
        if (!key.isEmpty() && !tag.isEmpty()) {
            hk[key] = tag;
        }
    }
    
    m_data["hotkeys"] = hk;
    m_hotkeysCacheDirty = true;
    
    emit hotkeysChanged();
}

void Config::setHotkey(const QString& key, const QString& tag) {
    QString normKey = normalizeKey(key);
    QString normTag = tag.trimmed().toLower();
    
    if (normKey.isEmpty()) return;
    
    QJsonObject hk = m_data.value("hotkeys").toObject();
    
    if (normTag.isEmpty()) {
        hk.remove(normKey);
    } else {
        hk[normKey] = normTag;
    }
    
    m_data["hotkeys"] = hk;
    m_hotkeysCacheDirty = true;
    
    emit hotkeysChanged();
}

void Config::removeHotkey(const QString& key) {
    setHotkey(key, QString());
}

QString Config::tagForHotkey(const QString& key) const {
    return hotkeys().value(normalizeKey(key));
}

bool Config::darkMode() const {
    // Default to true (dark mode)
    return m_data.value("dark_mode").toBool(true);
}

void Config::setDarkMode(bool enabled) {
    bool wasEnabled = darkMode();
    m_data["dark_mode"] = enabled;
    
    if (wasEnabled != enabled) {
        emit themeChanged(enabled);
    }
}

int Config::thumbnailSize() const {
    int size = m_data.value("thumb_size").toInt(320);
    return qBound(120, size, 512);
}

void Config::setThumbnailSize(int size) {
    m_data["thumb_size"] = qBound(120, size, 512);
}

QString Config::lastRootDir() const {
    return m_data.value("last_root_dir").toString();
}

void Config::setLastRootDir(const QString& path) {
    m_data["last_root_dir"] = QDir(path).absolutePath();
}

QString Config::taggingPrevKey() const {
    QString key = m_data.value("tagging_prev_key").toString().trimmed().toLower();
    return key.isEmpty() ? "a" : key;
}

QString Config::taggingNextKey() const {
    QString key = m_data.value("tagging_next_key").toString().trimmed().toLower();
    return key.isEmpty() ? "d" : key;
}

void Config::setTaggingNavKeys(const QString& prevKey, const QString& nextKey) {
    m_data["tagging_prev_key"] = prevKey.trimmed().toLower();
    m_data["tagging_next_key"] = nextKey.trimmed().toLower();
}

QByteArray Config::windowGeometry() const {
    QString base64 = m_data.value("window_geometry").toString();
    return QByteArray::fromBase64(base64.toLatin1());
}

void Config::setWindowGeometry(const QByteArray& geometry) {
    m_data["window_geometry"] = QString::fromLatin1(geometry.toBase64());
}

QByteArray Config::windowState() const {
    QString base64 = m_data.value("window_state").toString();
    return QByteArray::fromBase64(base64.toLatin1());
}

void Config::setWindowState(const QByteArray& state) {
    m_data["window_state"] = QString::fromLatin1(state.toBase64());
}

} // namespace KeyTagger

