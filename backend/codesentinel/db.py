"""SQLite persistence for repos, runs, reasoning steps and fix attempts.

Four tables: repos, runs, reasoning_steps, fix_attempts. Types are kept
portable (TEXT/INTEGER/REAL, JSON stored as TEXT) so the same DDL works on
PostgreSQL later.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id              TEXT PRIMARY KEY,
    source_type     TEXT NOT NULL CHECK (source_type IN ('demo', 'user_provided')),
    repo_url        TEXT NOT NULL,
    default_branch  TEXT NOT NULL DEFAULT 'main',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id                      TEXT PRIMARY KEY,
    repo_id                 TEXT NOT NULL REFERENCES repos(id),
    status                  TEXT NOT NULL CHECK (status IN ('running', 'fixed', 'failed', 'needs_review')),
    started_at              TEXT NOT NULL,
    completed_at            TEXT,
    attempt_count           INTEGER NOT NULL DEFAULT 0,
    diagnosis_summary       TEXT,
    final_confidence_score  REAL
);

CREATE TABLE IF NOT EXISTS reasoning_steps (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs(id),
    sequence     INTEGER NOT NULL,
    step_type    TEXT NOT NULL CHECK (step_type IN ('plan', 'tool_call', 'result', 'reflection')),
    content      TEXT NOT NULL,
    tool_name    TEXT,
    tool_input   TEXT,
    tool_output  TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS fix_attempts (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs(id),
    attempt_number  INTEGER NOT NULL,
    diff_before     TEXT NOT NULL,
    diff_after      TEXT NOT NULL,
    tests_passed    INTEGER NOT NULL,
    test_output     TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_steps_run ON reasoning_steps(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_attempts_run ON fix_attempts(run_id, attempt_number);
"""

JSON_COLUMNS = ("tool_input", "tool_output")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect(path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for col in JSON_COLUMNS:
        if col in d and d[col] is not None:
            d[col] = json.loads(d[col])
    if "tests_passed" in d:
        d["tests_passed"] = bool(d["tests_passed"])
    return d


# ---------- repos ----------

def create_repo(conn, repo_url: str, source_type: str, repo_id: str | None = None,
                default_branch: str = "main") -> dict:
    repo = {
        "id": repo_id or new_id("repo"),
        "source_type": source_type,
        "repo_url": repo_url,
        "default_branch": default_branch,
        "created_at": now_iso(),
    }
    conn.execute(
        "INSERT INTO repos (id, source_type, repo_url, default_branch, created_at) "
        "VALUES (:id, :source_type, :repo_url, :default_branch, :created_at)",
        repo,
    )
    conn.commit()
    return repo


def get_repo(conn, repo_id: str) -> dict | None:
    return _row_to_dict(conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone())


# ---------- runs ----------

def create_run(conn, repo_id: str) -> dict:
    run = {"id": new_id("run"), "repo_id": repo_id, "status": "running", "started_at": now_iso()}
    conn.execute(
        "INSERT INTO runs (id, repo_id, status, started_at) VALUES (:id, :repo_id, :status, :started_at)",
        run,
    )
    conn.commit()
    return get_run(conn, run["id"])


def update_run(conn, run_id: str, **fields) -> dict:
    allowed = {"status", "completed_at", "attempt_count", "diagnosis_summary", "final_confidence_score"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unknown run fields: {unknown}")
    if fields:
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        conn.execute(f"UPDATE runs SET {assignments} WHERE id = :id", {**fields, "id": run_id})
        conn.commit()
    return get_run(conn, run_id)


def get_run(conn, run_id: str) -> dict | None:
    return _row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())


def list_runs(conn, status: str | None = None) -> list[dict]:
    if status:
        rows = conn.execute("SELECT * FROM runs WHERE status = ? ORDER BY started_at DESC", (status,))
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC")
    return [_row_to_dict(r) for r in rows.fetchall()]


# ---------- reasoning steps ----------

def add_step(conn, step: dict) -> dict:
    """Persist a reasoning step. `step` must carry run_id, sequence, step_type, content."""
    row = {
        "id": new_id("step"),
        "tool_name": None,
        "tool_input": None,
        "tool_output": None,
        "created_at": now_iso(),
        **step,
    }
    params = {**row, **{c: json.dumps(row[c]) if row[c] is not None else None for c in JSON_COLUMNS}}
    conn.execute(
        "INSERT INTO reasoning_steps (id, run_id, sequence, step_type, content, tool_name, tool_input, tool_output, created_at) "
        "VALUES (:id, :run_id, :sequence, :step_type, :content, :tool_name, :tool_input, :tool_output, :created_at)",
        params,
    )
    conn.commit()
    return row


def list_steps(conn, run_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM reasoning_steps WHERE run_id = ? ORDER BY sequence", (run_id,))
    return [_row_to_dict(r) for r in rows.fetchall()]


# ---------- fix attempts ----------

def add_fix_attempt(conn, run_id: str, attempt_number: int, diff_before: str, diff_after: str,
                    tests_passed: bool, test_output: str) -> dict:
    row = {
        "id": new_id("fix"),
        "run_id": run_id,
        "attempt_number": attempt_number,
        "diff_before": diff_before,
        "diff_after": diff_after,
        "tests_passed": int(tests_passed),
        "test_output": test_output,
        "created_at": now_iso(),
    }
    conn.execute(
        "INSERT INTO fix_attempts (id, run_id, attempt_number, diff_before, diff_after, tests_passed, test_output, created_at) "
        "VALUES (:id, :run_id, :attempt_number, :diff_before, :diff_after, :tests_passed, :test_output, :created_at)",
        row,
    )
    conn.commit()
    return {**row, "tests_passed": tests_passed}


def list_fix_attempts(conn, run_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM fix_attempts WHERE run_id = ? ORDER BY attempt_number", (run_id,))
    return [_row_to_dict(r) for r in rows.fetchall()]
