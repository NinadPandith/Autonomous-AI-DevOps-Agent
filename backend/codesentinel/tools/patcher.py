"""Patch tool: apply one exact-match string replacement to a source file.

Guardrails: the path must stay inside the workspace, test files are
read-only (the agent must fix the code, not the tests), and `old_str` must
match exactly once so every edit is unambiguous.
"""
from ..workspace import Workspace, WorkspaceError


class PatchError(Exception):
    pass


def edit_file(ws: Workspace, path: str, old_str: str, new_str: str) -> dict:
    if Workspace.is_test_path(path):
        raise PatchError("Test files are read-only. Fix the application code, not the tests.")
    full = ws.resolve(path)
    if not full.is_file():
        raise WorkspaceError(f"No such file: {path}")
    if old_str == new_str:
        raise PatchError("old_str and new_str are identical — nothing to change.")

    text = full.read_text(encoding="utf-8")
    count = text.count(old_str) if old_str else 0
    if count == 0:
        raise PatchError("old_str was not found in the file. Re-read the file and copy the text exactly, including indentation.")
    if count > 1:
        raise PatchError(f"old_str matches {count} places. Include more surrounding lines so it matches exactly once.")

    start_line = text[:text.index(old_str)].count("\n") + 1
    full.write_text(text.replace(old_str, new_str, 1), encoding="utf-8")

    new_lines = new_str.count("\n") + (0 if new_str.endswith("\n") else 1)
    old_lines = old_str.count("\n") + (0 if old_str.endswith("\n") else 1)
    return {
        "path": path,
        "start_line": start_line,
        "old_line_count": old_lines,
        "new_line_count": new_lines,
    }
