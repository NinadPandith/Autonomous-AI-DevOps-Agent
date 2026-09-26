"""Code Reader tool: list, read and search files in the workspace."""
import re

from ..workspace import Workspace, WorkspaceError

TEXT_SUFFIXES = {".py", ".toml", ".cfg", ".ini", ".txt", ".md", ".json", ".yaml", ".yml"}
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", ".venv", "node_modules"}
MAX_FILE_BYTES = 200_000
MAX_SEARCH_MATCHES = 50


def list_files(ws: Workspace) -> list[str]:
    files = []
    for path in ws.root.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES and not SKIP_DIRS & set(path.parts):
            files.append(ws.rel(path))
    return sorted(files)


def read_file(ws: Workspace, path: str) -> str:
    """Return the file with 1-based line numbers, the way an editor shows it."""
    full = ws.resolve(path)
    if not full.is_file():
        raise WorkspaceError(f"No such file: {path}")
    if full.stat().st_size > MAX_FILE_BYTES:
        raise WorkspaceError(f"File too large to read: {path}")
    lines = full.read_text(encoding="utf-8").splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}}  {line}" for i, line in enumerate(lines, start=1))


def search_code(ws: Workspace, pattern: str) -> list[str]:
    """Grep the repo for a regex (falls back to a literal match if the regex is invalid)."""
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(re.escape(pattern))
    matches = []
    for rel in list_files(ws):
        for lineno, line in enumerate(ws.read(rel).splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{rel}:{lineno}: {line.strip()}")
                if len(matches) >= MAX_SEARCH_MATCHES:
                    return matches
    return matches
