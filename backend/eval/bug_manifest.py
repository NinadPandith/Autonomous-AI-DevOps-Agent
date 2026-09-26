"""Load the seeded-bug manifest and build demo-repo variants from it.

A variant is a copy of demo-repo with a chosen subset of bugs left in place
and every other bug replaced by its fix. The evaluation harness uses
single-bug variants to measure per-bug fix rates.
"""
import json
import shutil
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parent / "bugs.json"


def load_bugs() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["bugs"]


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{path.name}: expected snippet exactly once, found {count}:\n{old}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def fix_bug(repo_dir: Path, bug: dict) -> None:
    _replace_once(repo_dir / bug["file"], bug["buggy"], bug["fixed"])
    if extra := bug.get("extra_fix"):
        _replace_once(repo_dir / bug["file"], extra["buggy"], extra["fixed"])


def make_variant(source_repo: Path, dest: Path, keep_bug_ids: set[str]) -> Path:
    """Copy `source_repo` to `dest`, fixing every bug not in `keep_bug_ids`."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source_repo, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    for bug in load_bugs():
        if bug["id"] not in keep_bug_ids:
            fix_bug(dest, bug)
    return dest
