import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple, Dict

_DB_FILENAME = "keytag.sqlite"


@dataclass
class MediaRecord:
    id: int
    file_path: str
    root_dir: str
    file_name: str
    sha256: Optional[str]
    p_hash: Optional[str]
    width: Optional[int]
    height: Optional[int]
    size_bytes: Optional[int]
    captured_time_utc: Optional[int]
    modified_time_utc: Optional[int]
    media_type: str
    thumbnail_path: Optional[str]


class Database:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)
        self.db_path = os.path.join(self.base_dir, _DB_FILENAME)
        os.makedirs(self.base_dir, exist_ok=True)
        self._initialize_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY,
                    file_path TEXT NOT NULL UNIQUE,
                    root_dir TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    sha256 TEXT,
                    p_hash TEXT,
                    width INTEGER,
                    height INTEGER,
                    size_bytes INTEGER,
                    captured_time_utc INTEGER,
                    modified_time_utc INTEGER,
                    media_type TEXT NOT NULL,
                    thumbnail_path TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_media_sha256 ON media(sha256);
                CREATE INDEX IF NOT EXISTS idx_media_phash ON media(p_hash);
                CREATE INDEX IF NOT EXISTS idx_media_file_path ON media(file_path);
                CREATE INDEX IF NOT EXISTS idx_media_modified ON media(modified_time_utc);

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS media_tags (
                    media_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY (media_id, tag_id),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_media_tags_media_id ON media_tags(media_id);
                CREATE INDEX IF NOT EXISTS idx_media_tags_tag_id ON media_tags(tag_id);
                """
            )
            conn.commit()

    def upsert_media(
        self,
        *,
        file_path: str,
        root_dir: str,
        file_name: str,
        sha256: Optional[str],
        p_hash: Optional[str],
        width: Optional[int],
        height: Optional[int],
        size_bytes: Optional[int],
        captured_time_utc: Optional[int],
        modified_time_utc: Optional[int],
        media_type: str,
        thumbnail_path: Optional[str],
        error: Optional[str] = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO media (
                    file_path, root_dir, file_name, sha256, p_hash, width, height,
                    size_bytes, captured_time_utc, modified_time_utc, media_type, thumbnail_path, status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    sha256=excluded.sha256,
                    p_hash=excluded.p_hash,
                    width=excluded.width,
                    height=excluded.height,
                    size_bytes=excluded.size_bytes,
                    captured_time_utc=excluded.captured_time_utc,
                    modified_time_utc=excluded.modified_time_utc,
                    media_type=excluded.media_type,
                    thumbnail_path=excluded.thumbnail_path,
                    status='active',
                    error=excluded.error
                """,
                (
                    file_path,
                    root_dir,
                    file_name,
                    sha256,
                    p_hash,
                    width,
                    height,
                    size_bytes,
                    captured_time_utc,
                    modified_time_utc,
                    media_type,
                    thumbnail_path,
                    error,
                ),
            )
            conn.commit()
            media_id = cur.execute(
                "SELECT id FROM media WHERE file_path=?",
                (file_path,),
            ).fetchone()[0]
            return media_id

    def upsert_tags(self, tag_names: Sequence[str]) -> List[int]:
        if not tag_names:
            return []
        tag_ids: List[int] = []
        with self.connect() as conn:
            cur = conn.cursor()
            for name in tag_names:
                name_norm = name.strip().lower()
                if not name_norm:
                    continue
                cur.execute(
                    "INSERT INTO tags(name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                    (name_norm,),
                )
                row = cur.execute("SELECT id FROM tags WHERE name=?", (name_norm,)).fetchone()
                if row:
                    tag_ids.append(int(row[0]))
            conn.commit()
        return tag_ids

    def set_media_tags(self, media_id: int, tag_names: Sequence[str]) -> None:
        tag_ids = self.upsert_tags(tag_names)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM media_tags WHERE media_id=?", (media_id,))
            cur.executemany(
                "INSERT OR IGNORE INTO media_tags(media_id, tag_id) VALUES (?, ?)",
                [(media_id, tag_id) for tag_id in tag_ids],
            )
            conn.commit()

    def add_media_tags(self, media_id: int, tag_names: Sequence[str]) -> None:
        tag_ids = self.upsert_tags(tag_names)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.executemany(
                "INSERT OR IGNORE INTO media_tags(media_id, tag_id) VALUES (?, ?)",
                [(media_id, tag_id) for tag_id in tag_ids],
            )
            conn.commit()

    def remove_media_tags(self, media_id: int, tag_names: Sequence[str]) -> None:
        if not tag_names:
            return
        names_norm = [t.strip().lower() for t in tag_names if t and t.strip()]
        if not names_norm:
            return
        with self.connect() as conn:
            cur = conn.cursor()
            placeholders = ",".join(["?"] * len(names_norm))
            rows = cur.execute(
                f"SELECT id FROM tags WHERE name IN ({placeholders})",
                names_norm,
            ).fetchall()
            tag_ids = [int(r[0]) for r in rows]
            if not tag_ids:
                return
            cur.executemany(
                "DELETE FROM media_tags WHERE media_id = ? AND tag_id = ?",
                [(media_id, tag_id) for tag_id in tag_ids],
            )
            conn.commit()

    def remove_tag_globally(self, tag_name: str) -> int:
        """Remove a tag by name from all media and delete the tag if unused.

        Returns the number of media_tag rows deleted.
        """
        name_norm = (tag_name or "").strip().lower()
        if not name_norm:
            return 0
        with self.connect() as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT id FROM tags WHERE name=?", (name_norm,)).fetchone()
            if not row:
                return 0
            tag_id = int(row[0])
            cur.execute("DELETE FROM media_tags WHERE tag_id=?", (tag_id,))
            affected = cur.rowcount or 0
            # Remove the tag itself if no more references remain
            cur.execute(
                "DELETE FROM tags WHERE id=? AND NOT EXISTS (SELECT 1 FROM media_tags WHERE tag_id=?)",
                (tag_id, tag_id),
            )
            conn.commit()
            return affected

    def query_media(
        self,
        *,
        required_tags: Optional[Sequence[str]] = None,
        search_text: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        order_by: str = "modified_time_utc DESC, id DESC",
        root_dir: Optional[str] = None,
        tags_match_all: bool = True,
    ) -> Tuple[List[MediaRecord], int]:
        with self.connect() as conn:
            cur = conn.cursor()

            where_clauses: List[str] = ["status='active'"]
            params: List[object] = []

            if search_text:
                where_clauses.append("file_name LIKE ?")
                params.append(f"%{search_text}%")

            if required_tags:
                placeholders = ",".join(["?"] * len(required_tags))
                tag_params = [t.strip().lower() for t in required_tags]
                if tags_match_all:
                    where_clauses.append(
                        f"id IN (SELECT media_id FROM media_tags WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({placeholders})) GROUP BY media_id HAVING COUNT(DISTINCT tag_id) = {len(required_tags)})"
                    )
                else:
                    where_clauses.append(
                        f"id IN (SELECT DISTINCT media_id FROM media_tags WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({placeholders})))"
                    )
                params.extend(tag_params)

            if root_dir:
                where_clauses.append("root_dir = ?")
                params.append(os.path.abspath(root_dir))

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            total = cur.execute(
                f"SELECT COUNT(*) FROM media WHERE {where_sql}",
                params,
            ).fetchone()[0]

            rows = cur.execute(
                f"SELECT * FROM media WHERE {where_sql} ORDER BY {order_by} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()

            records = [
                MediaRecord(
                    id=row["id"],
                    file_path=row["file_path"],
                    root_dir=row["root_dir"],
                    file_name=row["file_name"],
                    sha256=row["sha256"],
                    p_hash=row["p_hash"],
                    width=row["width"],
                    height=row["height"],
                    size_bytes=row["size_bytes"],
                    captured_time_utc=row["captured_time_utc"],
                    modified_time_utc=row["modified_time_utc"],
                    media_type=row["media_type"],
                    thumbnail_path=row["thumbnail_path"],
                )
                for row in rows
            ]
            return records, int(total)

    def existing_media_map_for_root(self, root_dir: str) -> Dict[str, Dict[str, Optional[object]]]:
        """Return a map of file_path -> minimal fields used for incremental scanning.

        Includes size_bytes, modified_time_utc, thumbnail_path, sha256, media_type.
        """
        root_dir_abs = os.path.abspath(root_dir)
        with self.connect() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT file_path, size_bytes, modified_time_utc, thumbnail_path, sha256, media_type
                FROM media
                WHERE root_dir = ? AND status = 'active'
                """,
                (root_dir_abs,),
            ).fetchall()
            out: Dict[str, Dict[str, Optional[object]]] = {}
            for row in rows:
                out[str(row["file_path"])] = {
                    "size_bytes": int(row["size_bytes"]) if row["size_bytes"] is not None else None,
                    "modified_time_utc": int(row["modified_time_utc"]) if row["modified_time_utc"] is not None else None,
                    "thumbnail_path": str(row["thumbnail_path"]) if row["thumbnail_path"] else None,
                    "sha256": str(row["sha256"]) if row["sha256"] else None,
                    "media_type": str(row["media_type"]) if row["media_type"] else None,
                }
            return out

    def update_thumbnail_path(self, file_path: str, thumbnail_path: Optional[str]) -> None:
        """Update only the thumbnail_path for a given file, if it exists in DB."""
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE media SET thumbnail_path = ? WHERE file_path = ?",
                (thumbnail_path, file_path),
            )
            conn.commit()

    def mark_missing_files_deleted(self, existing_paths: Sequence[str], root_dir: str) -> int:
        """Mark files as deleted when present in DB for root but not in existing_paths.

        Returns the number of rows marked deleted.
        """
        root_dir_abs = os.path.abspath(root_dir)
        with self.connect() as conn:
            cur = conn.cursor()
            placeholders = ",".join(["?"] * len(existing_paths)) if existing_paths else None
            if placeholders:
                params = [root_dir_abs, *existing_paths]
                sql = f"UPDATE media SET status='deleted' WHERE root_dir = ? AND status='active' AND file_path NOT IN ({placeholders})"
            else:
                params = [root_dir_abs]
                sql = "UPDATE media SET status='deleted' WHERE root_dir = ? AND status='active'"
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount or 0

    def all_tags(self) -> List[str]:
        with self.connect() as conn:
            cur = conn.cursor()
            rows = cur.execute("SELECT name FROM tags ORDER BY name ASC").fetchall()
            return [r[0] for r in rows]

    def get_media_tags(self, media_id: int) -> List[str]:
        with self.connect() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT t.name
                FROM tags t
                JOIN media_tags mt ON mt.tag_id = t.id
                WHERE mt.media_id = ?
                ORDER BY t.name ASC
                """,
                (media_id,),
            ).fetchall()
            return [r[0] for r in rows]
