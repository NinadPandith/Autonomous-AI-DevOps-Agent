"""Isolated per-run copies of the target repository.

The agent never touches the original repo: every run gets its own copy under
workspaces/<run_id>/repo, and every path the agent supplies is resolved and
checked so it cannot escape that copy.
"""
import os
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath

from .config import WORKSPACES_DIR

IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "*.pyc", ".venv", "node_modules")


class WorkspaceError(Exception):
    pass


def _force_remove(func, path, _exc):
    # Git marks object files read-only; on Windows rmtree can't delete them until they're writable.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onexc=_force_remove)


class Workspace:
    def __init__(self, root: Path, python: str | None = None):
        self.root = root.resolve()
        # Interpreter used to run the repo's tests: the backend's own for the demo repo,
        # a per-run virtualenv for user repositories (see repo_setup).
        self.python = python or sys.executable
        # Repo-relative folder the tests run from ("" = repo root), e.g. "backend" for monorepos.
        self.project_dir = ""

    @property
    def test_cwd(self) -> Path:
        return self.root / self.project_dir if self.project_dir else self.root

    def to_repo_path(self, path: str) -> str:
        """Convert a path relative to the test folder (as pytest prints it) to a repo-relative path."""
        path = path.replace("\\", "/")
        is_absolute = path.startswith("/") or (len(path) > 1 and path[1] == ":")
        return f"{self.project_dir}/{path}" if self.project_dir and not is_absolute else path

    @classmethod
    def create(cls, source: Path, run_id: str, base: Path = WORKSPACES_DIR) -> "Workspace":
        dest = base / run_id / "repo"
        remove_tree(dest)
        shutil.copytree(source, dest, ignore=IGNORE)
        return cls(dest)

    @classmethod
    def empty(cls, run_id: str, base: Path = WORKSPACES_DIR) -> "Workspace":
        """A not-yet-populated workspace (a repository will be cloned into root)."""
        run_dir = base / run_id
        remove_tree(run_dir)
        run_dir.mkdir(parents=True)
        return cls(run_dir / "repo")

    def resolve(self, rel_path: str) -> Path:
        """Resolve a repo-relative path, refusing anything outside the workspace."""
        if not rel_path or Path(rel_path).is_absolute():
            raise WorkspaceError(f"Path must be relative to the repository root: {rel_path!r}")
        path = (self.root / rel_path).resolve()
        if path != self.root and self.root not in path.parents:
            raise WorkspaceError(f"Path is outside the repository: {rel_path!r}")
        return path

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    @staticmethod
    def is_test_path(rel_path: str) -> bool:
        p = PurePosixPath(rel_path.replace("\\", "/"))
        return ("tests" in p.parts or "test" in p.parts or p.name.startswith("test_")
                or p.name.endswith("_test.py") or p.name == "conftest.py")

    # newline="" keeps each file's own line endings byte-for-byte (no CRLF/LF translation), so
    # snapshots, reverts and diffs are exact on every OS.
    def read(self, rel_path: str) -> str:
        with open(self.resolve(rel_path), encoding="utf-8", newline="") as f:
            return f.read()

    def write(self, rel_path: str, content: str) -> None:
        with open(self.resolve(rel_path), "w", encoding="utf-8", newline="") as f:
            f.write(content)

    def cleanup(self) -> None:
        remove_tree(self.root.parent)
