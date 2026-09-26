"""Prepare a user-provided GitHub repository: clone it, then install it into its own virtualenv.

Isolation (process level — the Docker sandbox is future work):
- shallow clone only: no submodules, no Git LFS downloads, no credential prompts
- a fresh virtualenv per run, outside the repo, deleted with the workspace
- hard timeouts on clone and install
- secrets scrubbed from every subprocess environment
The repo's own code does run (install scripts, tests), which is why this feature
is opt-in and the UI asks the user to confirm they trust the repository.
"""
import os
import subprocess
import sys
from pathlib import Path

from . import config
from .tools.test_runner import scrubbed_env
from .workspace import Workspace

REQUIREMENT_FILES = [
    "requirements.txt", "requirements-dev.txt", "requirements-test.txt", "requirements_dev.txt",
    "requirements_test.txt", "dev-requirements.txt", "test-requirements.txt",
    "requirements/dev.txt", "requirements/test.txt", "requirements/tests.txt",
]
TAIL = 3000  # characters of command output kept for the trace


class SetupError(Exception):
    """The repository could not be prepared. The message is shown to the user."""


def _run(cmd: list[str], cwd: Path, timeout: int, env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              env=env or scrubbed_env(), encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        raise SetupError(f"`{' '.join(cmd[:3])} …` took longer than {timeout}s and was stopped.") from e
    except OSError as e:
        raise SetupError(f"Could not run `{cmd[0]}`: {e}") from e


def clone(url: str, dest: Path) -> str:
    env = {**scrubbed_env(), "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_LFS_SKIP_SMUDGE": "1"}
    proc = _run(["git", "-c", "core.autocrlf=false", "clone", "--depth", "1", "--single-branch", "--no-tags",
                 url, str(dest)],
                cwd=dest.parent, timeout=config.CLONE_TIMEOUT_S, env=env)
    if proc.returncode != 0:
        raise SetupError("The repository couldn't be cloned. Make sure the URL is correct and the repo is public.")
    size_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / 1_000_000
    if size_mb > config.USER_REPO_MAX_MB:
        raise SetupError(f"The repository is {size_mb:.0f} MB; the limit is {config.USER_REPO_MAX_MB} MB.")
    if not any(dest.rglob("*.py")):
        raise SetupError("No Python files were found. CodeSentinel currently supports Python projects with pytest tests.")
    return f"Cloned {url} ({size_mb:.1f} MB)."


def venv_python(venv_dir: Path) -> str:
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return str(venv_dir / sub)


PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pytest.ini", "tox.ini",
                   "conftest.py")
SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "env", "docs", "site-packages", "__pycache__"}


def _has_tests(d: Path) -> bool:
    return ((d / "tests").is_dir() or (d / "test").is_dir()
            or any(d.glob("test_*.py")) or any(d.glob("*_test.py")))


def _has_marker(d: Path) -> bool:
    return any((d / m).is_file() for m in PROJECT_MARKERS) or any(d.glob("requirements*.txt"))


def find_project_dir(repo: Path) -> Path:
    """Where the Python project lives: the repo root, or a subfolder such as backend/ or src/app/.

    Searches the root and up to two folders deep, shallowest first. Prefers a folder that has both
    tests and a project marker (requirements, pyproject, pytest.ini, …); falls back to any folder
    with tests; else the root.
    """
    levels = [[repo]]
    for _ in range(2):
        levels.append(sorted(
            child for parent in levels[-1] for child in parent.iterdir()
            if child.is_dir() and child.name not in SKIP_DIRS and not child.name.startswith(".")
        ))
    candidates = [d for level in levels for d in level]
    for predicate in (lambda d: _has_tests(d) and _has_marker(d), _has_tests):
        for d in candidates:
            if predicate(d):
                return d
    return repo


def install(ws: Workspace) -> tuple[str, list[str]]:
    """Create a virtualenv next to the repo and install the project + pytest into it.

    Detects the project folder (ws.project_dir) first. Returns (summary, commands run) and sets
    ws.python to the new interpreter.
    """
    repo = ws.root
    project = find_project_dir(repo)
    ws.project_dir = "" if project == repo else project.relative_to(repo).as_posix()

    venv_dir = repo.parent / "venv"
    proc = _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=repo.parent, timeout=120)
    if proc.returncode != 0:
        raise SetupError("Couldn't create a Python environment for this repository.")
    python = venv_python(venv_dir)

    pip = [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-q"]
    steps: list[list[str]] = []
    reqs = []
    for folder in dict.fromkeys([repo, project]):  # root first, then the project folder
        for r in REQUIREMENT_FILES:
            if (folder / r).is_file():
                reqs.append((folder / r).relative_to(repo).as_posix())
    for r in reqs:
        steps.append(pip + ["-r", r])
    for folder in dict.fromkeys([project, repo]):
        if (folder / "pyproject.toml").is_file() or (folder / "setup.py").is_file():
            # Editable, so the agent's edits are what the tests import. Unknown extras only warn.
            rel = folder.relative_to(repo).as_posix()
            steps.append(pip + ["-e", f"{'.' if rel == '.' else './' + rel}[test,tests,testing,dev]"])
            break
    steps.append(pip + ["pytest"])

    ran = []
    for cmd in steps:
        proc = _run(cmd, cwd=repo, timeout=config.INSTALL_TIMEOUT_S)
        ran.append(" ".join(cmd[cmd.index("install") :]))
        if proc.returncode != 0:
            output = (proc.stdout + proc.stderr)[-TAIL:]
            raise SetupError(f"Installing dependencies failed on `{ran[-1]}`:\n{output}")
    ws.python = python
    what = ", ".join(reqs) + (" + the project itself" if any("-e" in c for c in steps) else "")
    where = f" Tests will run from {ws.project_dir}/." if ws.project_dir else ""
    return (f"Installed dependencies ({what or 'pytest only'}) into an isolated environment.{where}", ran)
