import hashlib
import os
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

from PIL import Image, ExifTags
import imagehash

from .db import Database

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"
}

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".wmv", ".3gp"
}

SUPPORTED_AUDIO_EXTENSIONS = {
    ".m4a", ".mp3"
}


@dataclass
class ScanResult:
    scanned: int
    added_or_updated: int
    errors: int


def is_image_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in SUPPORTED_IMAGE_EXTENSIONS


def is_video_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in SUPPORTED_VIDEO_EXTENSIONS


def is_audio_file(path: str) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in SUPPORTED_AUDIO_EXTENSIONS


def sha256_of_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exif_capture_time_utc(img: Image.Image) -> Optional[int]:
    try:
        exif = img.getexif()
        if not exif:
            return None
        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        dt = tags.get("DateTimeOriginal") or tags.get("DateTime")
        if not dt:
            return None
        # dt format: 'YYYY:MM:DD HH:MM:SS'
        try:
            import datetime as _dt

            local = _dt.datetime.strptime(str(dt), "%Y:%m:%d %H:%M:%S")
            epoch = int(local.timestamp())
            return epoch
        except Exception:
            return None
    except Exception:
        return None


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def thumbnail_path_for(file_sha256: str, thumbnails_dir: str) -> str:
    ensure_dir(thumbnails_dir)
    return os.path.join(thumbnails_dir, f"{file_sha256}.jpg")


def save_thumbnail(img: Image.Image, thumb_path: str, max_size: int = 512) -> None:
    img_copy = img.copy()
    img_copy.thumbnail((max_size, max_size))
    img_copy = img_copy.convert("RGB")
    img_copy.save(thumb_path, format="JPEG", quality=85)


def create_video_thumbnail(video_path: str, thumb_path: str, max_size: int = 512) -> Optional[Tuple[int, int]]:
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        # Try middle frame
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count // 2))
        ok, frame = cap.read()
        if not ok:
            cap.release()
            return None
        height, width = frame.shape[:2]
        # Convert BGR to RGB
        frame_rgb = frame[:, :, ::-1]
        img = Image.fromarray(frame_rgb)
        save_thumbnail(img, thumb_path, max_size=max_size)
        cap.release()
        return width, height
    except Exception:
        return None


def list_media_files(root_dir: str) -> List[str]:
    root_dir = os.path.abspath(root_dir)
    files: List[str] = []
    for current_root, _, fnames in os.walk(root_dir):
        for fname in fnames:
            fpath = os.path.join(current_root, fname)
            ext = os.path.splitext(fpath)[1].lower()
            if (
                (ext in SUPPORTED_IMAGE_EXTENSIONS)
                or (ext in SUPPORTED_VIDEO_EXTENSIONS)
                or (ext in SUPPORTED_AUDIO_EXTENSIONS)
            ):
                files.append(fpath)
    return files


def scan_directory(
    root_dir: str,
    db: Database,
    thumbnails_dir: Optional[str] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> ScanResult:
    root_dir = os.path.abspath(root_dir)
    if thumbnails_dir is None:
        thumbnails_dir = os.path.join(db.base_dir, "thumbnails")
    ensure_dir(thumbnails_dir)

    files = list_media_files(root_dir)
    try:
        # Mark records for files that no longer exist as deleted
        db.mark_missing_files_deleted(files, root_dir)
    except Exception:
        pass
    total = len(files)

    scanned = 0
    added_or_updated = 0
    errors = 0

    # Load existing map for incremental check
    existing = db.existing_media_map_for_root(root_dir)

    for idx, fpath in enumerate(files, start=1):
        if on_progress is not None:
            try:
                on_progress(idx, total, fpath)
            except Exception:
                pass
        fname = os.path.basename(fpath)
        ext = os.path.splitext(fpath)[1].lower()
        try:
            stat = os.stat(fpath)
            size_bytes = int(stat.st_size)
            modified_time_utc = int(stat.st_mtime)

            # Incremental skip: if existing record matches size and mtime and has thumbnail, skip heavy work.
            prev = existing.get(fpath)
            if prev and prev.get("size_bytes") == size_bytes and prev.get("modified_time_utc") == modified_time_utc:
                thumb_path_existing = prev.get("thumbnail_path")
                sha256_existing = prev.get("sha256")
                if sha256_existing:
                    thumb_path = thumbnail_path_for(sha256_existing, thumbnails_dir)
                    if not os.path.exists(thumb_path):
                        # Create missing thumbnail based on media type
                        if ext in SUPPORTED_IMAGE_EXTENSIONS:
                            try:
                                with Image.open(fpath) as img:
                                    save_thumbnail(img, thumb_path)
                            except Exception:
                                thumb_path = None
                        elif ext in SUPPORTED_VIDEO_EXTENSIONS:
                            dims = create_video_thumbnail(fpath, thumb_path)
                            if dims is None:
                                thumb_path = None
                        else:
                            # Audio: no thumbnail generation
                            thumb_path = None
                    # If we created a new thumbnail, persist it
                    if thumb_path and thumb_path != thumb_path_existing:
                        try:
                            db.update_thumbnail_path(fpath, thumb_path)
                        except Exception:
                            pass
                # Nothing else to do for unchanged files
                scanned += 1
                continue

            # Changed or new file: compute sha and full metadata
            sha256 = sha256_of_file(fpath)

            width: Optional[int] = None
            height: Optional[int] = None
            p_hash_hex: Optional[str] = None
            captured_time = None
            thumb_path = thumbnail_path_for(sha256, thumbnails_dir)
            if ext in SUPPORTED_IMAGE_EXTENSIONS:
                media_type = "image"
            elif ext in SUPPORTED_VIDEO_EXTENSIONS:
                media_type = "video"
            elif ext in SUPPORTED_AUDIO_EXTENSIONS:
                media_type = "audio"
            else:
                media_type = "unknown"

            if ext in SUPPORTED_IMAGE_EXTENSIONS:
                with Image.open(fpath) as img:
                    width, height = img.size
                    try:
                        ph = imagehash.phash(img)
                        p_hash_hex = ph.__str__()
                    except Exception:
                        p_hash_hex = None
                    captured_time = exif_capture_time_utc(img)
                    if not os.path.exists(thumb_path):
                        try:
                            save_thumbnail(img, thumb_path)
                        except Exception:
                            thumb_path = None
            elif ext in SUPPORTED_VIDEO_EXTENSIONS:
                if not os.path.exists(thumb_path):
                    dims = create_video_thumbnail(fpath, thumb_path)
                    if dims is None:
                        thumb_path = None
                    else:
                        width, height = dims
            else:
                # Audio: do not attempt thumbnail; metadata remains minimal
                thumb_path = None

            media_id = db.upsert_media(
                file_path=fpath,
                root_dir=root_dir,
                file_name=fname,
                sha256=sha256,
                p_hash=p_hash_hex,
                width=width,
                height=height,
                size_bytes=size_bytes,
                captured_time_utc=captured_time,
                modified_time_utc=modified_time_utc,
                media_type=media_type,
                thumbnail_path=thumb_path,
            )
            if media_id:
                added_or_updated += 1
        except Exception as e:
            try:
                db.upsert_media(
                    file_path=fpath,
                    root_dir=root_dir,
                    file_name=fname,
                    sha256=None,
                    p_hash=None,
                    width=None,
                    height=None,
                    size_bytes=None,
                    captured_time_utc=None,
                    modified_time_utc=None,
                    media_type=(
                        "video" if is_video_file(fpath) else ("audio" if is_audio_file(fpath) else "image")
                    ),
                    thumbnail_path=None,
                    error=str(e),
                )
            except Exception:
                pass
            errors += 1
        finally:
            scanned += 1

    return ScanResult(scanned=scanned, added_or_updated=added_or_updated, errors=errors)
