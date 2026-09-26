"""Phase 0 check: insert and read back one row from each of the 4 tables.

Usage (from backend/):  .venv\\Scripts\\python scripts\\db_smoke_test.py
Uses an in-memory database so it never touches the real one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codesentinel import db  # noqa: E402


def main() -> None:
    conn = db.connect(":memory:")
    db.init_db(conn)

    repo = db.create_repo(conn, "local://demo-repo", "demo", repo_id="repo_demo001")
    assert db.get_repo(conn, repo["id"])["repo_url"] == "local://demo-repo"
    print("repos           OK ->", db.get_repo(conn, repo["id"]))

    run = db.create_run(conn, repo["id"])
    db.update_run(conn, run["id"], attempt_count=1, diagnosis_summary="Smoke test diagnosis")
    assert db.get_run(conn, run["id"])["attempt_count"] == 1
    print("runs            OK ->", db.get_run(conn, run["id"]))

    db.add_step(conn, {
        "run_id": run["id"], "sequence": 0, "step_type": "tool_call",
        "content": "Running the test suite to check current status.",
        "tool_name": "run_tests", "tool_input": {"path": "."},
    })
    steps = db.list_steps(conn, run["id"])
    assert steps[0]["tool_input"] == {"path": "."}
    print("reasoning_steps OK ->", steps[0])

    db.add_fix_attempt(conn, run["id"], 1, "return a - b", "return a + b", True, "12 passed")
    attempts = db.list_fix_attempts(conn, run["id"])
    assert attempts[0]["tests_passed"] is True
    print("fix_attempts    OK ->", attempts[0])

    print("\nAll 4 tables: insert + read OK")


if __name__ == "__main__":
    main()
