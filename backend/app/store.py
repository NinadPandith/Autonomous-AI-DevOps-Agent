"""Thread-safe access to the SQLite database.

Agent runs execute in worker threads while request handlers run on the event
loop, so every db call goes through one connection guarded by a lock.
"""
import json
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

    # ---- featured (recorded) runs: shipped as a fixtures file so a fresh deploy has examples ----

    def export_run(self, run_id: str) -> dict:
        run = self.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        return {
            "repo": self.get_repo(run["repo_id"]),
            "run": run,
            "steps": self.list_steps(run_id),
            "fix_attempts": self.list_fix_attempts(run_id),
        }

    def import_run(self, bundle: dict) -> bool:
        """Insert a recorded run (and its repo) unless it already exists. Returns True if inserted."""
        run = bundle["run"]
        with self._lock:
            if self._conn.execute("SELECT 1 FROM runs WHERE id = ?", (run["id"],)).fetchone():
                return False
            repo = bundle["repo"]
            self._conn.execute(
                "INSERT OR IGNORE INTO repos (id, source_type, repo_url, default_branch, created_at) "
                "VALUES (:id, :source_type, :repo_url, :default_branch, :created_at)", repo)
            self._conn.execute(
                "INSERT INTO runs (id, repo_id, status, started_at, completed_at, attempt_count, diagnosis_summary, "
                "final_confidence_score) VALUES (:id, :repo_id, :status, :started_at, :completed_at, :attempt_count, "
                ":diagnosis_summary, :final_confidence_score)", run)
            for s in bundle["steps"]:
                self._conn.execute(
                    "INSERT INTO reasoning_steps (id, run_id, sequence, step_type, content, tool_name, tool_input, "
                    "tool_output, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (s["id"], s["run_id"], s["sequence"], s["step_type"], s["content"], s["tool_name"],
                     json.dumps(s["tool_input"]) if s["tool_input"] is not None else None,
                     json.dumps(s["tool_output"]) if s["tool_output"] is not None else None, s["created_at"]))
            for a in bundle["fix_attempts"]:
                self._conn.execute(
                    "INSERT INTO fix_attempts (id, run_id, attempt_number, diff_before, diff_after, tests_passed, "
                    "test_output, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (a["id"], a["run_id"], a["attempt_number"], a["diff_before"], a["diff_after"],
                     int(a["tests_passed"]), a["test_output"], a["created_at"]))
            self._conn.commit()
        return True

    def count_runs_since(self, iso_timestamp: str, exclude_ids: set[str] = frozenset()) -> int:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM runs WHERE started_at >= ?", (iso_timestamp,)).fetchall()
        return sum(1 for (run_id,) in rows if run_id not in exclude_ids)

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
