"""Project-folder detection, path mapping and setup-problem handling (no network, no LLM)."""
import shutil

from codesentinel.agent import Agent
from codesentinel.config import DEMO_REPO_PATH
from codesentinel.repo_setup import find_project_dir
from codesentinel.workspace import Workspace
from eval.bug_manifest import make_variant

from .test_agent_loop import BUGS, Recorder, ScriptedClient, message, reflection, tool


def touch(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_detects_root_project(tmp_path):
    touch(tmp_path / "requirements.txt")
    touch(tmp_path / "tests" / "test_x.py")
    assert find_project_dir(tmp_path) == tmp_path


def test_detects_backend_subfolder(tmp_path):
    touch(tmp_path / "README.md")
    touch(tmp_path / "frontend" / "package.json")
    touch(tmp_path / "backend" / "requirements.txt")
    touch(tmp_path / "backend" / "tests" / "test_api.py")
    assert find_project_dir(tmp_path) == tmp_path / "backend"


def test_detects_two_levels_deep(tmp_path):
    touch(tmp_path / "services" / "api" / "pyproject.toml")
    touch(tmp_path / "services" / "api" / "test_service.py")
    assert find_project_dir(tmp_path) == tmp_path / "services" / "api"


def test_prefers_folder_with_tests_and_marker(tmp_path):
    touch(tmp_path / "tests" / "test_smoke.py")  # root has tests but no project marker
    touch(tmp_path / "backend" / "requirements.txt")
    touch(tmp_path / "backend" / "tests" / "test_api.py")
    assert find_project_dir(tmp_path) == tmp_path / "backend"


def test_to_repo_path():
    ws = Workspace(DEMO_REPO_PATH)
    assert ws.to_repo_path("tests\\test_x.py::t") == "tests/test_x.py::t"
    ws.project_dir = "backend"
    assert ws.to_repo_path("app/models.py") == "backend/app/models.py"
    assert ws.to_repo_path("C:/Python/lib/x.py") == "C:/Python/lib/x.py"


def test_fixes_bug_in_monorepo_subfolder(tmp_path):
    """Demo repo nested under backend/: tests run from there, edits use repo-relative paths."""
    repo = tmp_path / "ws" / "run_mono" / "repo"
    make_variant(DEMO_REPO_PATH, repo / "backend", {"B1"})
    touch(repo / "README.md", "# monorepo\n")
    ws = Workspace(repo)
    ws.project_dir = find_project_dir(repo).relative_to(repo).as_posix()
    assert ws.project_dir == "backend"

    b1 = BUGS["B1"]
    client = ScriptedClient(
        agent_turns=[
            message(tool("edit_file", path=f"backend/{b1['file']}", old_str=b1["buggy"], new_str=b1["fixed"])),
            message(tool("submit_fix", diagnosis="Off-by-one in paginate().", confidence=0.9)),
        ],
        reflections=[reflection()],
    )
    rec = Recorder()
    result = Agent(ws, "run_mono", [rec], llm=client).run()
    assert result.status == "fixed"
    assert all(t.startswith("backend/tests/") for t in result.initial_tests["failing_tests"])
    parsed = next(s for s in rec.steps if s["tool_name"] == "parse_failures" and s["step_type"] == "result")
    assert parsed["tool_output"]["suspects"][0]["file"] == "backend/shopcart/utils.py"


def test_missing_module_is_reported_as_setup_problem(tmp_path):
    repo = tmp_path / "src"
    shutil.copytree(DEMO_REPO_PATH, repo)
    touch(repo / "tests" / "test_needs_dep.py", "import some_missing_dependency\n\ndef test_x():\n    pass\n")
    for f in (repo / "tests").glob("test_*.py"):
        if f.name != "test_needs_dep.py":
            f.unlink()
    ws = Workspace.create(repo, "run_dep", base=tmp_path / "ws")

    client = ScriptedClient(agent_turns=[], reflections=[])  # any LLM call would fail the test
    result = Agent(ws, "run_dep", [Recorder()], llm=client).run()
    assert result.status == "needs_review"
    assert result.attempt_count == 0
    assert "some_missing_dependency" in result.diagnosis_summary
    assert result.diagnosis_summary.startswith("Setup problem")
