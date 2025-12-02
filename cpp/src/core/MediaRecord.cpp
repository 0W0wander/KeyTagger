#include "MediaRecord.h"
#include <QSet>

namespace KeyTagger {

static const QSet<QString> IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"
};

static const QSet<QString> VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".3gp"
};

static const QSet<QString> AUDIO_EXTENSIONS = {
    ".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac"
};

MediaType MediaRecord::typeFromExtension(const QString& ext) {
    QString lower = ext.toLower();
    if (IMAGE_EXTENSIONS.contains(lower)) {
        return MediaType::Image;
    }
    if (VIDEO_EXTENSIONS.contains(lower)) {
        return MediaType::Video;
    }
    if (AUDIO_EXTENSIONS.contains(lower)) {
        return MediaType::Audio;
    }
    return MediaType::Unknown;
}

QString MediaRecord::mediaTypeToString(MediaType type) {
    switch (type) {
        case MediaType::Image: return "image";
        case MediaType::Video: return "video";
        case MediaType::Audio: return "audio";
        default: return "unknown";
    }
}

MediaType MediaRecord::stringToMediaType(const QString& str) {
    QString lower = str.toLower();
    if (lower == "image") return MediaType::Image;
    if (lower == "video") return MediaType::Video;
    if (lower == "audio") return MediaType::Audio;
    return MediaType::Unknown;
}

} // namespace KeyTagger

