r"""Save real runs as featured (recorded) runs that ship with the app.

The public demo replays these, so visitors can watch a real run without spending API quota.
Every server start loads them from fixtures/featured_runs.json into the database (idempotent).

Usage (from backend/):
    .venv\Scripts\python scripts\export_featured.py run_abc123 run_def456
    .venv\Scripts\python scripts\export_featured.py --list      # show finished runs to pick from
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store import Store  # noqa: E402
from codesentinel import config  # noqa: E402

FIXTURES = config.BACKEND_DIR / "fixtures" / "featured_runs.json"


def scrub_paths(text: str) -> str:
    """Replace local absolute paths (which include the OS username) with neutral placeholders."""
    replacements = {str(config.PROJECT_ROOT): "<project>", str(Path.home()): "<home>"}
    for local, placeholder in replacements.items():
        for variant in {local, local.replace("\\", "/"), json.dumps(local)[1:-1]}:
            text = text.replace(variant, placeholder)
    return text


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("run_ids", nargs="*")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    store = Store(config.DATABASE_PATH)

    if args.list or not args.run_ids:
        for r in store.list_runs():
            if r["status"] != "running":
                print(f"{r['id']}  {r['status']:<13} attempts={r['attempt_count']}  {(r['diagnosis_summary'] or '')[:70]}")
        return 0

    existing = json.loads(FIXTURES.read_text(encoding="utf-8"))["runs"] if FIXTURES.exists() else []
    by_id = {b["run"]["id"]: b for b in existing}
    for run_id in args.run_ids:
        bundle = store.export_run(run_id)
        if bundle["run"]["status"] == "running":
            print(f"Skipping {run_id}: still running")
            continue
        by_id[run_id] = bundle
        print(f"Saved {run_id} ({bundle['run']['status']}, {len(bundle['steps'])} steps)")
    FIXTURES.parent.mkdir(exist_ok=True)
    FIXTURES.write_text(scrub_paths(json.dumps({"runs": list(by_id.values())}, indent=1, ensure_ascii=False)),
                        encoding="utf-8")
    print(f"Wrote {FIXTURES} — commit it so deployments include these runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
