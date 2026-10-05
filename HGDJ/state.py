# 仅供个人学习研究，不得用于商业用途
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


class StateDB:
    def __init__(self, db_path: str):
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA foreign_keys=ON')
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        self._conn.executescript('''
            CREATE TABLE IF NOT EXISTS series (
                series_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                cover_url TEXT DEFAULT '',
                category TEXT DEFAULT '',
                intro TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                episode_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'discovered',
                directory TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS episodes (
                series_id TEXT NOT NULL,
                episode_num INTEGER NOT NULL,
                vid TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                downloaded_at TEXT,
                PRIMARY KEY (series_id, episode_num),
                FOREIGN KEY (series_id) REFERENCES series(series_id)
            );
            CREATE TABLE IF NOT EXISTS download_queue (
                series_id TEXT PRIMARY KEY,
                priority INTEGER DEFAULT 0,
                added_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (series_id) REFERENCES series(series_id)
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);
            CREATE INDEX IF NOT EXISTS idx_series_status ON series(status);
        ''')
        self._conn.commit()

    # ── 剧集管理 ──

    def upsert_series(self, series_id: str, name: str = '', cover_url: str = '',
                      category: str = '', intro: str = '', tags: str = '',
                      episode_count: int = 0) -> None:
        self._conn.execute('''
            INSERT INTO series (series_id, name, cover_url, category, intro, tags, episode_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(series_id) DO UPDATE SET
                name=CASE WHEN excluded.name != '' THEN excluded.name ELSE series.name END,
                cover_url=CASE WHEN excluded.cover_url != '' THEN excluded.cover_url ELSE series.cover_url END,
                category=CASE WHEN excluded.category != '' THEN excluded.category ELSE series.category END,
                intro=CASE WHEN excluded.intro != '' THEN excluded.intro ELSE series.intro END,
                tags=CASE WHEN excluded.tags != '' THEN excluded.tags ELSE series.tags END,
                episode_count=CASE WHEN excluded.episode_count > 0 THEN excluded.episode_count ELSE series.episode_count END,
                updated_at=datetime('now')
        ''', (series_id, name, cover_url, category, intro, tags, episode_count))
        self._conn.commit()

    def get_series(self, series_id: str) -> dict | None:
        row = self._conn.execute('SELECT * FROM series WHERE series_id=?', (series_id,)).fetchone()
        return dict(row) if row else None

    def list_series(self, status: str | None = None, search: str | None = None,
                    category: str | None = None) -> list[dict]:
        sql = 'SELECT * FROM series WHERE 1=1'
        params: list = []
        if status:
            sql += ' AND status=?'
            params.append(status)
        if category:
            sql += ' AND category=?'
            params.append(category)
        if search:
            sql += ' AND name LIKE ?'
            params.append(f'%{search}%')
        sql += ' ORDER BY updated_at DESC'
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def set_series_status(self, series_id: str, status: str) -> None:
        self._conn.execute(
            'UPDATE series SET status=?, updated_at=datetime("now") WHERE series_id=?',
            (status, series_id))
        self._conn.commit()

    def set_series_directory(self, series_id: str, directory: str) -> None:
        self._conn.execute(
            'UPDATE series SET directory=?, updated_at=datetime("now") WHERE series_id=?',
            (directory, series_id))
        self._conn.commit()

    # ── 分集管理 ──

    def upsert_episode(self, series_id: str, episode_num: int, vid: str = '') -> None:
        self._conn.execute('''
            INSERT INTO episodes (series_id, episode_num, vid)
            VALUES (?, ?, ?)
            ON CONFLICT(series_id, episode_num) DO UPDATE SET
                vid=CASE WHEN excluded.vid != '' THEN excluded.vid ELSE episodes.vid END
        ''', (series_id, episode_num, vid))
        self._conn.commit()

    def set_episode_status(self, series_id: str, episode_num: int, status: str,
                           file_path: str = '', file_size: int = 0) -> None:
        if status == 'done':
            self._conn.execute('''
                UPDATE episodes SET status=?, file_path=?, file_size=?, downloaded_at=datetime('now')
                WHERE series_id=? AND episode_num=?
            ''', (status, file_path, file_size, series_id, episode_num))
        else:
            self._conn.execute(
                'UPDATE episodes SET status=? WHERE series_id=? AND episode_num=?',
                (status, series_id, episode_num))
        self._conn.commit()

    def get_episodes(self, series_id: str) -> list[dict]:
        rows = self._conn.execute(
            'SELECT * FROM episodes WHERE series_id=? ORDER BY episode_num',
            (series_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_episode(self, series_id: str, episode_num: int) -> dict | None:
        row = self._conn.execute(
            'SELECT * FROM episodes WHERE series_id=? AND episode_num=?',
            (series_id, episode_num)).fetchone()
        return dict(row) if row else None

    def get_pending_episodes(self, series_id: str) -> list[dict]:
        rows = self._conn.execute(
            'SELECT * FROM episodes WHERE series_id=? AND status IN ("pending","failed") ORDER BY episode_num',
            (series_id,)).fetchall()
        return [dict(r) for r in rows]

    # ── 下载队列 ──

    def add_to_queue(self, series_id: str, priority: int = 0) -> None:
        self._conn.execute('''
            INSERT OR REPLACE INTO download_queue (series_id, priority, added_at)
            VALUES (?, ?, datetime('now'))
        ''', (series_id, priority))
        self._conn.commit()

    def remove_from_queue(self, series_id: str) -> None:
        self._conn.execute('DELETE FROM download_queue WHERE series_id=?', (series_id,))
        self._conn.commit()

    def get_queue(self) -> list[dict]:
        rows = self._conn.execute('''
            SELECT dq.*, s.name, s.episode_count,
                   (SELECT COUNT(*) FROM episodes e WHERE e.series_id=dq.series_id AND e.status='done') as done_count,
                   (SELECT COUNT(*) FROM episodes e WHERE e.series_id=dq.series_id AND e.status='downloading') as downloading_count,
                   (SELECT COUNT(*) FROM episodes e WHERE e.series_id=dq.series_id AND e.status='failed') as failed_count
            FROM download_queue dq
            JOIN series s ON dq.series_id=s.series_id
            ORDER BY dq.priority DESC, dq.added_at ASC
        ''').fetchall()
        return [dict(r) for r in rows]

    def is_in_queue(self, series_id: str) -> bool:
        row = self._conn.execute(
            'SELECT 1 FROM download_queue WHERE series_id=?', (series_id,)).fetchone()
        return row is not None

    # ── 统计 ──

    def dashboard_stats(self) -> dict:
        total_series = self._conn.execute('SELECT COUNT(*) FROM series').fetchone()[0]
        queued = self._conn.execute('SELECT COUNT(*) FROM download_queue').fetchone()[0]
        total_eps = self._conn.execute('SELECT COUNT(*) FROM episodes').fetchone()[0]
        done_eps = self._conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE status='done'").fetchone()[0]
        failed_eps = self._conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE status='failed'").fetchone()[0]
        downloading_eps = self._conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE status='downloading'").fetchone()[0]
        total_size = self._conn.execute(
            "SELECT COALESCE(SUM(file_size),0) FROM episodes WHERE status='done'").fetchone()[0]
        return {
            'total_series': total_series,
            'queued_series': queued,
            'total_episodes': total_eps,
            'done_episodes': done_eps,
            'failed_episodes': failed_eps,
            'downloading_episodes': downloading_eps,
            'total_size_mb': round(total_size / 1048576, 1),
        }

    def episode_stats(self, series_id: str) -> dict:
        total = self._conn.execute(
            'SELECT COUNT(*) FROM episodes WHERE series_id=?', (series_id,)).fetchone()[0]
        done = self._conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE series_id=? AND status='done'",
            (series_id,)).fetchone()[0]
        failed = self._conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE series_id=? AND status='failed'",
            (series_id,)).fetchone()[0]
        size = self._conn.execute(
            "SELECT COALESCE(SUM(file_size),0) FROM episodes WHERE series_id=? AND status='done'",
            (series_id,)).fetchone()[0]
        return {
            'total_episodes': total, 'done_episodes': done,
            'failed_episodes': failed, 'total_size_mb': round(size / 1048576, 1),
        }
