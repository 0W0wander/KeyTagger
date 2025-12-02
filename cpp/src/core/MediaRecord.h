#pragma once

#include <QString>
#include <QDateTime>
#include <optional>

namespace KeyTagger {

enum class MediaType {
    Image,
    Video,
    Audio,
    Unknown
};

struct MediaRecord {
    qint64 id = 0;
    QString filePath;
    QString rootDir;
    QString fileName;
    QString sha256;
    QString pHash;
    std::optional<int> width;
    std::optional<int> height;
    std::optional<qint64> sizeBytes;
    std::optional<qint64> capturedTimeUtc;
    std::optional<qint64> modifiedTimeUtc;
    MediaType mediaType = MediaType::Unknown;
    QString thumbnailPath;
    QString status = "active";
    QString error;

    bool isValid() const { return id > 0 && !filePath.isEmpty(); }
    bool isImage() const { return mediaType == MediaType::Image; }
    bool isVideo() const { return mediaType == MediaType::Video; }
    bool isAudio() const { return mediaType == MediaType::Audio; }
    
    static MediaType typeFromExtension(const QString& ext);
    static QString mediaTypeToString(MediaType type);
    static MediaType stringToMediaType(const QString& str);
};

} // namespace KeyTagger

