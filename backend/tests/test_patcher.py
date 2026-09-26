"""Patch tool matching: exact, CRLF files, trailing whitespace, copied line numbers, guardrails."""
import pytest

from codesentinel.tools.patcher import PatchError, edit_file
from codesentinel.workspace import Workspace

SOURCE = "def f(x):\n    if x > 1:\n        return x\n    return 0\n"


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "pkg").mkdir()
    return Workspace(tmp_path)


def write(ws, text, newline="\n"):
    with open(ws.root / "pkg" / "m.py", "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", newline))


def read(ws):
    with open(ws.root / "pkg" / "m.py", encoding="utf-8", newline="") as f:
        return f.read()


def test_exact_match(ws):
    write(ws, SOURCE)
    edit_file(ws, "pkg/m.py", "    if x > 1:\n", "    if x >= 1:\n")
    assert read(ws) == SOURCE.replace("x > 1", "x >= 1")


def test_crlf_file_with_lf_old_str_keeps_crlf(ws):
    write(ws, SOURCE, newline="\r\n")
    info = edit_file(ws, "pkg/m.py", "    if x > 1:\n        return x\n", "    if x >= 1:\n        return x\n")
    assert read(ws) == SOURCE.replace("x > 1", "x >= 1").replace("\n", "\r\n")
    assert info["start_line"] == 2


def test_trailing_whitespace_and_line_numbers_tolerated(ws):
    write(ws, SOURCE)
    edit_file(ws, "pkg/m.py", "2      if x > 1:   \n3          return x", "    if x >= 1:\n        return x")
    assert read(ws) == SOURCE.replace("x > 1", "x >= 1")


def test_not_found_points_to_closest_line(ws):
    write(ws, SOURCE)
    with pytest.raises(PatchError, match="closest line is 2"):
        edit_file(ws, "pkg/m.py", "    if x > 2:\n", "    if x >= 2:\n")


def test_ambiguous_match_rejected(ws):
    write(ws, "a = 1\na = 1\n")
    with pytest.raises(PatchError, match="matches 2 places"):
        edit_file(ws, "pkg/m.py", "a = 1\n", "a = 2\n")


def test_tests_are_read_only(ws):
    with pytest.raises(PatchError, match="read-only"):
        edit_file(ws, "tests/test_m.py", "x", "y")
