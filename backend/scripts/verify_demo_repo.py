"""Phase 1 check: the demo repo fails predictably, and the bug manifest is correct.

1. demo-repo as-is has a known set of failing tests.
2. Applying every fix from eval/bugs.json makes the whole suite pass.
3. Each bug on its own breaks a known set of tests (printed as a table).

Usage (from backend/):  .venv\\Scripts\\python scripts\\verify_demo_repo.py
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from codesentinel.config import DEMO_REPO_PATH  # noqa: E402
from eval.bug_manifest import load_bugs, make_variant  # noqa: E402


def failing_tests(repo_dir: Path) -> tuple[set[str], str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider"],
        cwd=repo_dir, capture_output=True, text=True, timeout=120,
    )
    failed = set(re.findall(r"^FAILED (\S+)", proc.stdout, re.MULTILINE))
    summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "(no output)"
    return failed, summary


def main() -> int:
    bugs = load_bugs()
    all_ids = {b["id"] for b in bugs}
    ok = True

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        failed, summary = failing_tests(make_variant(DEMO_REPO_PATH, tmp / "as_is", keep_bug_ids=all_ids))
        print(f"demo-repo as-is:      {summary}")

        clean_failed, summary = failing_tests(make_variant(DEMO_REPO_PATH, tmp / "clean", keep_bug_ids=set()))
        print(f"all fixes applied:    {summary}")
        if clean_failed:
            ok = False
            print("  !! expected no failures, got:", *sorted(clean_failed), sep="\n     ")

        print("\nPer-bug failing tests (bug present alone):")
        covered = set()
        for bug in bugs:
            bug_failed, _ = failing_tests(make_variant(DEMO_REPO_PATH, tmp / bug["id"], keep_bug_ids={bug["id"]}))
            covered |= bug_failed
            print(f"  {bug['id']} [{bug['difficulty']:<6}] {bug['title']}")
            for t in sorted(bug_failed):
                print(f"       - {t}")
            if not bug_failed:
                ok = False
                print("       !! this bug breaks no tests on its own")

        if covered != failed:
            print("\nNote: failures in the all-bugs repo differ from the union of single-bug failures:")
            print("  only with all bugs:", sorted(failed - covered))
            print("  only in isolation: ", sorted(covered - failed))

    print("\nRESULT:", "OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
