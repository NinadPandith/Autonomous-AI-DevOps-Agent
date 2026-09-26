"""Patch tool: apply one string replacement to a source file.

Guardrails: the path must stay inside the workspace, test files are
read-only (the agent must fix the code, not the tests), and `old_str` must
match exactly once so every edit is unambiguous.

Matching is exact first. If that fails, a line-based match that ignores line
endings (CRLF vs LF) and trailing whitespace is tried, and line-number
prefixes copied from read_file output are stripped — the common reasons a
model's copy of the code doesn't match byte-for-byte. The file's own line
endings are preserved either way.
"""
import difflib
import re

from ..workspace import Workspace, WorkspaceError

# read_file shows lines as "  12  code"; models sometimes copy that prefix into old_str.
LINE_NUMBER_PREFIX = re.compile(r"^\s*\d+  ")


class PatchError(Exception):
    pass


def _strip_line_numbers(s: str) -> str:
    lines = s.split("\n")
    content = [ln for ln in lines if ln.strip()]
    if content and all(LINE_NUMBER_PREFIX.match(ln) for ln in content):
        return "\n".join(LINE_NUMBER_PREFIX.sub("", ln, count=1) for ln in lines)
    return s


def _line_match(text: str, old: str) -> list[int]:
    """Start indexes (in text.splitlines(True)) where old matches line-by-line, ignoring EOL/trailing space."""
    lines = text.splitlines(keepends=True)
    want = [ln.rstrip() for ln in old.rstrip("\r\n").split("\n")]
    have = [ln.rstrip() for ln in lines]
    return [i for i in range(len(have) - len(want) + 1) if have[i:i + len(want)] == want]


def _closest_line(text: str, old: str) -> str:
    first = next((ln.strip() for ln in old.split("\n") if ln.strip()), "")
    lines = [ln.strip() for ln in text.splitlines()]
    match = difflib.get_close_matches(first, lines, n=1, cutoff=0.5)
    if not match:
        return ""
    lineno = lines.index(match[0]) + 1
    return f" The closest line is {lineno}: `{match[0]}`."


def edit_file(ws: Workspace, path: str, old_str: str, new_str: str) -> dict:
    if Workspace.is_test_path(path):
        raise PatchError("Test files are read-only. Fix the application code, not the tests.")
    full = ws.resolve(path)
    if not full.is_file():
        raise WorkspaceError(f"No such file: {path}")
    if old_str == new_str:
        raise PatchError("old_str and new_str are identical — nothing to change.")
    if not old_str.strip():
        raise PatchError("old_str is empty. Copy the exact existing lines you want to replace.")

    with open(full, encoding="utf-8", newline="") as f:  # keep the file's own line endings
        text = f.read()
    eol = "\r\n" if "\r\n" in text else "\n"

    if text.count(old_str) == 1:
        start_line = text[:text.index(old_str)].count("\n") + 1
        new_text = text.replace(old_str, new_str, 1)
    else:
        if text.count(old_str) > 1:
            raise PatchError(f"old_str matches {text.count(old_str)} places. Include more surrounding lines "
                             "so it matches exactly once.")
        old_clean = _strip_line_numbers(old_str.replace("\r\n", "\n"))
        new_clean = _strip_line_numbers(new_str.replace("\r\n", "\n"))
        starts = _line_match(text, old_clean)
        if len(starts) > 1:
            raise PatchError(f"old_str matches {len(starts)} places. Include more surrounding lines "
                             "so it matches exactly once.")
        if not starts:
            raise PatchError("old_str was not found in the file. Re-read the file and copy the lines exactly, "
                             "without the line-number prefix." + _closest_line(text, old_clean))
        lines = text.splitlines(keepends=True)
        n_old = len(old_clean.rstrip("\n").split("\n"))
        i = starts[0]
        last_had_eol = lines[i + n_old - 1].endswith(("\n", "\r"))
        replacement = new_clean.rstrip("\n").replace("\n", eol) + (eol if last_had_eol else "")
        if not new_clean.strip():
            replacement = ""
        new_text = "".join(lines[:i]) + replacement + "".join(lines[i + n_old:])
        start_line = i + 1
        old_str, new_str = old_clean, new_clean

    with open(full, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)

    new_lines = new_str.count("\n") + (0 if new_str.endswith("\n") else 1)
    old_lines = old_str.count("\n") + (0 if old_str.endswith("\n") else 1)
    return {
        "path": path,
        "start_line": start_line,
        "old_line_count": old_lines,
        "new_line_count": new_lines,
    }
