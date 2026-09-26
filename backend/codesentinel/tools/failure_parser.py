"""Error / stack-trace parser: turn raw pytest output into likely fault locations.

Two heuristics, in priority order:
1. Traceback frames in non-test files — the exception was raised in that function.
2. For plain assertion failures (no source frames), the functions the failing
   test calls, resolved via the AST to where they are defined.
"""
import ast
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from ..workspace import Workspace
from .code_reader import list_files

SECTION_RE = re.compile(r"^_{3,} (.+?) _{3,}$", re.MULTILINE)
FRAME_RE = re.compile(r"^(\S+\.py):(\d+): in (\S+)$", re.MULTILINE)
ERROR_LINE_RE = re.compile(r"^E\s+(.*)$", re.MULTILINE)
SUMMARY_RE = re.compile(r"^(?:FAILED|ERROR) (\S+?)(?: - (.*))?$", re.MULTILINE)
EXC_TYPE_RE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))\b")


@dataclass
class Frame:
    file: str
    line: int
    function: str


@dataclass
class TestFailure:
    test_id: str
    error_type: str
    message: str
    frames: list[Frame] = field(default_factory=list)


@dataclass
class Suspect:
    file: str
    function: str
    reason: str
    tests: list[str] = field(default_factory=list)


def parse_failures(output: str) -> list[TestFailure]:
    ids_by_name = {}
    for test_id, _ in SUMMARY_RE.findall(output):
        ids_by_name[test_id.split("::")[-1]] = test_id
        ids_by_name[test_id.split("::", 1)[-1].replace("::", ".")] = test_id

    failures = []
    matches = list(SECTION_RE.finditer(output))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        if title.startswith(("short test summary", "warnings summary")) or " passed" in title or " failed" in title:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(output)
        body = output[m.end():end]
        body = body.split("=== short test summary")[0]

        frames = [Frame(f.replace("\\", "/"), int(ln), fn) for f, ln, fn in FRAME_RE.findall(body)]
        error_lines = ERROR_LINE_RE.findall(body)
        message = error_lines[0].strip() if error_lines else ""
        if exc := EXC_TYPE_RE.match(message):
            error_type = exc.group(1).split(".")[-1]
        elif message.startswith("assert") or "AssertionError" in body:
            error_type = "AssertionError"
        else:
            error_type = "Error"

        test_id = ids_by_name.get(title, title.removeprefix("ERROR collecting ").strip())
        failures.append(TestFailure(test_id, error_type, message, frames))
    return failures


def _definitions_index(ws: Workspace) -> tuple[dict[str, list[str]], set[str]]:
    """Map function/class/method name -> source files (non-test) defining it.

    Also returns the set of names that are classes.
    """
    index = defaultdict(list)
    classes = set()
    for rel in list_files(ws):
        if not rel.endswith(".py") or Workspace.is_test_path(rel):
            continue
        try:
            tree = ast.parse(ws.read(rel))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                index[node.name].append(rel)
                if isinstance(node, ast.ClassDef):
                    classes.add(node.name)
    return index, classes


def _test_call_map(ws: Workspace) -> dict[str, set[str]]:
    """Map test id -> names of everything that test function calls."""
    calls: dict[str, set[str]] = {}
    for rel in list_files(ws):
        if not (rel.endswith(".py") and Workspace.is_test_path(rel)):
            continue
        try:
            tree = ast.parse(ws.read(rel))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                names = set()
                for call in ast.walk(node):
                    if isinstance(call, ast.Call):
                        f = call.func
                        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                        if name:
                            names.add(name)
                calls[f"{rel}::{node.name}"] = names
    return calls


def locate_suspects(ws: Workspace, failures: list[TestFailure], limit: int = 6) -> list[Suspect]:
    """Rank likely fault locations.

    Functions that raised inside a traceback come first. Remaining failures
    are localized with spectrum-based scoring over each test's calls: a
    function's score is the share of the tests calling it that fail, so shared
    setup helpers (called by passing tests too) sink below the threshold.
    """
    suspects: dict[tuple[str, str], Suspect] = {}
    index, classes = _definitions_index(ws)

    def add(file: str, function: str, reason: str, test_id: str) -> Suspect:
        s = suspects.setdefault((file, function), Suspect(file, function, reason))
        if test_id not in s.tests:
            s.tests.append(test_id)
        return s

    unexplained = []
    for f in failures:
        source_frames = [fr for fr in f.frames if not Workspace.is_test_path(fr.file)]
        if source_frames:
            deepest = source_frames[-1]
            add(deepest.file, deepest.function, f"raised {f.error_type}", f.test_id)
        else:
            unexplained.append(f.test_id)

    raised = list(suspects.values())

    call_map = _test_call_map(ws)
    failing_ids = {f.test_id for f in failures}
    scored: dict[tuple[str, str], float] = {}
    for test_id in unexplained:
        for name in call_map.get(test_id, ()):
            for file in index.get(name, []):
                key = (file, name)
                if key in scored or any((s.file, s.function) == key for s in raised):
                    continue
                callers = [t for t, names in call_map.items() if name in names]
                n_fail = sum(t in failing_ids for t in callers)
                n_pass = len(callers) - n_fail
                scored[key] = n_fail / (n_fail + n_pass) if callers else 0.0
                for t in callers:
                    if t in failing_ids and t in unexplained:
                        add(file, name, "called by failing tests", t)

    ranked_calls = sorted(
        (s for s in suspects.values() if s not in raised and s.function not in classes),
        key=lambda s: (-scored.get((s.file, s.function), 0.0), -len(s.tests)),
    )
    ranked_calls = [s for s in ranked_calls if scored.get((s.file, s.function), 0) >= 0.6]
    for s in ranked_calls:
        s.reason = f"called by failing tests ({scored[(s.file, s.function)]:.0%} of its callers fail)"
    return (sorted(raised, key=lambda s: -len(s.tests)) + ranked_calls)[:limit]


def to_dicts(items) -> list[dict]:
    return [asdict(i) for i in items]
