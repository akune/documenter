"""
Persistent record of processing jobs for the status web interface.
Stored in SQLite so the history survives container restarts.
"""

import json
import logging
import sqlite3
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUSES = (STATUS_QUEUED, STATUS_PROCESSING, STATUS_DONE, STATUS_FAILED)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    size        INTEGER,
    status      TEXT NOT NULL,
    step        TEXT,
    error       TEXT,
    outputs     TEXT NOT NULL DEFAULT '[]',
    queued_at   REAL NOT NULL,
    started_at  REAL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_queued_at ON jobs (queued_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
"""


class JobStore:
    """Thread-safe job history backed by SQLite."""

    def __init__(self, path: str, retention_days: int = 90):
        self.path = path
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
        self._mark_interrupted()
        self.purge_old()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def _mark_interrupted(self) -> None:
        """Jobs that were still open when the service stopped will never finish."""
        cursor = self._execute(
            "UPDATE jobs SET status = ?, error = ?, finished_at = ? WHERE status IN (?, ?)",
            (STATUS_FAILED, "Interrupted by service restart (the file is picked up again if it is "
             "still in the input folder)", time.time(), STATUS_QUEUED, STATUS_PROCESSING),
        )
        if cursor.rowcount:
            logger.info(f"Marked {cursor.rowcount} interrupted job(s) as failed")

    def purge_old(self) -> None:
        """Delete finished jobs older than the retention period."""
        if self.retention_days <= 0:
            return
        cutoff = time.time() - self.retention_days * 86400
        cursor = self._execute(
            "DELETE FROM jobs WHERE finished_at IS NOT NULL AND finished_at < ?", (cutoff,)
        )
        if cursor.rowcount:
            logger.info(f"Purged {cursor.rowcount} job(s) older than {self.retention_days} days")

    def create(self, source: str, size: Optional[int] = None) -> int:
        cursor = self._execute(
            "INSERT INTO jobs (source, size, status, queued_at) VALUES (?, ?, ?, ?)",
            (source, size, STATUS_QUEUED, time.time()),
        )
        return cursor.lastrowid

    def start(self, job_id: int) -> None:
        self._execute(
            "UPDATE jobs SET status = ?, started_at = ?, step = ? WHERE id = ?",
            (STATUS_PROCESSING, time.time(), "Waiting for file to be fully written", job_id),
        )

    def set_step(self, job_id: int, step: str) -> None:
        self._execute("UPDATE jobs SET step = ? WHERE id = ?", (step, job_id))

    def add_output(self, job_id: int, filename: str, targets: List[str]) -> None:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT outputs FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return
            outputs = json.loads(row["outputs"])
            outputs.append({"filename": filename, "targets": targets})
            self._conn.execute(
                "UPDATE jobs SET outputs = ? WHERE id = ?", (json.dumps(outputs), job_id)
            )

    def finish(self, job_id: int, success: bool, error: Optional[str] = None) -> None:
        self._execute(
            "UPDATE jobs SET status = ?, error = ?, step = NULL, finished_at = ? WHERE id = ?",
            (STATUS_DONE if success else STATUS_FAILED, error, time.time(), job_id),
        )

    def list_jobs(self, status: Optional[str] = None, limit: int = 200) -> List[Dict]:
        sql = "SELECT * FROM jobs"
        params: tuple = ()
        if status in STATUSES:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY queued_at DESC, id DESC LIMIT ?"
        params += (limit,)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        jobs = []
        for row in rows:
            job = dict(row)
            job["outputs"] = json.loads(job["outputs"])
            jobs.append(job)
        return jobs

    def counts(self) -> Dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
            ).fetchall()
        result = {status: 0 for status in STATUSES}
        for row in rows:
            result[row["status"]] = row["n"]
        return result

    def close(self) -> None:
        with self._lock:
            self._conn.close()
