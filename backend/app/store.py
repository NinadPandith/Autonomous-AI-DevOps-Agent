"""Thread-safe access to the SQLite database.

Agent runs execute in worker threads while request handlers run on the event
loop, so every db call goes through one connection guarded by a lock.
"""
import threading
from pathlib import Path

from codesentinel import db

DEMO_REPO_ID = "repo_demo001"


class Store:
    def __init__(self, path: Path | str):
        self._conn = db.connect(path)
        self._lock = threading.RLock()
        with self._lock:
            db.init_db(self._conn)

    def _call(self, fn, *args, **kwargs):
        with self._lock:
            return fn(self._conn, *args, **kwargs)

    def ensure_demo_repo(self) -> dict:
        return self.get_repo(DEMO_REPO_ID) or self.create_repo("local://demo-repo", "demo", repo_id=DEMO_REPO_ID)

    def find_repo_by_url(self, url: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM repos WHERE repo_url = ?", (url,)).fetchone()
            return dict(row) if row else None

    def mark_interrupted_runs(self) -> int:
        """Runs left 'running' by a server restart can never finish; mark them failed."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE runs SET status = 'failed', completed_at = ?, "
                "diagnosis_summary = COALESCE(diagnosis_summary, 'The run was interrupted by a server restart.') "
                "WHERE status = 'running'", (db.now_iso(),))
            self._conn.commit()
            return cur.rowcount

    def count_runs_since(self, iso_timestamp: str) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM runs WHERE started_at >= ?", (iso_timestamp,)).fetchone()[0]

    def create_repo(self, *a, **k): return self._call(db.create_repo, *a, **k)
    def get_repo(self, *a, **k): return self._call(db.get_repo, *a, **k)
    def create_run(self, *a, **k): return self._call(db.create_run, *a, **k)
    def update_run(self, *a, **k): return self._call(db.update_run, *a, **k)
    def get_run(self, *a, **k): return self._call(db.get_run, *a, **k)
    def list_runs(self, *a, **k): return self._call(db.list_runs, *a, **k)
    def add_step(self, *a, **k): return self._call(db.add_step, *a, **k)
    def list_steps(self, *a, **k): return self._call(db.list_steps, *a, **k)
    def add_fix_attempt(self, *a, **k): return self._call(db.add_fix_attempt, *a, **k)
    def list_fix_attempts(self, *a, **k): return self._call(db.list_fix_attempts, *a, **k)
