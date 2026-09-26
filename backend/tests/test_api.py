"""API + WebSocket tests with a scripted LLM (no network, no quota used)."""
import pytest
from fastapi.testclient import TestClient

from app.events import RunEventHub
from app.main import create_app
from app.runner import RunManager
from app.store import DEMO_REPO_ID, Store

from .test_agent_loop import BUGS, ScriptedClient, message, reflection, text, tool


def b1_script():
    b1 = BUGS["B1"]
    return ScriptedClient(
        agent_turns=[
            message(text("The start index in paginate() is off by one."),
                    tool("edit_file", path=b1["file"], old_str=b1["buggy"], new_str=b1["fixed"])),
            message(tool("submit_fix", diagnosis="paginate() treats page as 0-indexed.", confidence=0.95)),
        ],
        reflections=[reflection("The fix worked.", 0.95)],
    )


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "FEATURED_RUNS_FILE", tmp_path / "no_featured_runs.json")

    def factory(script_factory=b1_script):
        store = Store(tmp_path / "test.db")
        runner = RunManager(store, RunEventHub(), llm_factory=script_factory, workspaces_dir=tmp_path / "ws")
        return TestClient(create_app(store, runner))
    return factory


def test_demo_repo_and_scenarios(make_client):
    with make_client() as client:
        assert client.get("/api/repos/demo").json()["id"] == DEMO_REPO_ID
        scenarios = client.get("/api/repos/demo/scenarios").json()["scenarios"]
        assert len(scenarios) == 11
        assert all(set(s) == {"id", "title", "difficulty", "bug_type"} for s in scenarios)  # never the fix


def test_full_run_lifecycle(make_client):
    with make_client() as client:
        created = client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B1"]})
        assert created.status_code == 201
        run_id = created.json()["id"]
        assert created.json()["status"] == "running"

        # TestClient runs background tasks before returning, so the run is finished here.
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "fixed"
        assert run["attempt_count"] == 1
        assert run["completed_at"] is not None
        assert run["final_confidence_score"] == 0.95
        assert run["repo_url"] == "local://demo-repo"

        steps = client.get(f"/api/runs/{run_id}/reasoning").json()["steps"]
        assert [s["sequence"] for s in steps] == list(range(len(steps)))
        assert {"plan", "tool_call", "result", "reflection"} <= {s["step_type"] for s in steps}

        fix = client.get(f"/api/runs/{run_id}/fix").json()
        assert fix["tests_passed"] is True
        assert fix["files_changed"] == ["shopcart/utils.py"]
        assert "(page - 1) * page_size" in fix["diff_after"]
        assert "32 passed" in fix["tests_summary"]

        listed = client.get("/api/runs", params={"status": "fixed"}).json()["runs"]
        assert [r["id"] for r in listed] == [run_id]
        assert client.get("/api/runs", params={"status": "failed"}).json()["runs"] == []

        # A finished run's socket replays the whole trace, then the final status, then closes.
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            received = [ws.receive_json() for _ in range(len(steps) + 1)]
        assert [m["data"]["sequence"] for m in received[:-1]] == list(range(len(steps)))
        assert received[-1] == {"type": "status_update", "data": {
            "run_id": run_id, "status": "fixed", "attempt_count": 1, "completed_at": run["completed_at"]}}


def test_error_shapes(make_client):
    with make_client() as client:
        r = client.get("/api/runs/run_missing")
        assert r.status_code == 404
        assert r.json() == {"error": {"code": "RUN_NOT_FOUND", "message": "No run found with that ID."}}

        r = client.post("/api/runs", json={"repo_id": "repo_nope"})
        assert r.status_code == 404 and r.json()["error"]["code"] == "REPO_NOT_FOUND"

        r = client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B99"]})
        assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_BUG_ID"

        r = client.post("/api/runs", json={})
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"

        r = client.post("/api/repos", json={"repo_url": "not a url"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REPO_URL"


def test_agent_errors_mark_run_failed(make_client):
    def broken_llm():
        from codesentinel.llm import LLMError

        class Broken(ScriptedClient):
            def conversation(self, system, tools):
                raise LLMError("Gemini free-tier rate limit reached.")
        return Broken([], [])

    with make_client(broken_llm) as client:
        run_id = client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B1"]}).json()["id"]
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "failed"
        assert "rate limit" in run["diagnosis_summary"]
        # The run slot was released, so another run can start.
        assert client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B1"]}).status_code == 201


def test_second_run_rejected_while_busy(make_client):
    with make_client() as client:
        runner = client.app.state.runner
        runner.start(client.app.state.store.get_repo(DEMO_REPO_ID), None)  # hold the slot without executing
        r = client.post("/api/runs", json={"repo_id": DEMO_REPO_ID})
        assert r.status_code == 409 and r.json()["error"]["code"] == "AGENT_BUSY"


def test_daily_run_limit(make_client, monkeypatch):
    from codesentinel import config
    monkeypatch.setattr(config, "MAX_RUNS_PER_DAY", 1)
    with make_client() as client:
        assert client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B1"]}).status_code == 201
        r = client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B1"]})
        assert r.status_code == 429 and r.json()["error"]["code"] == "DAILY_LIMIT_REACHED"


def _user_repo(client):
    return client.app.state.store.create_repo("https://github.com/example/shop", "user_provided")


def test_user_repos_blocked_when_disabled(make_client, monkeypatch):
    from codesentinel import config
    monkeypatch.setattr(config, "ALLOW_USER_REPOS", False)
    with make_client() as client:
        assert client.get("/api/health").json()["allow_user_repos"] is False
        r = client.post("/api/runs", json={"repo_id": _user_repo(client)["id"]})
        assert r.status_code == 403 and r.json()["error"]["code"] == "USER_REPOS_DISABLED"


def test_user_repo_run_clones_installs_then_fixes(make_client, monkeypatch, tmp_path):
    """Clone/install are stubbed (no network, no third-party code): the stub drops in the B1 demo variant."""
    from codesentinel import config, repo_setup
    from eval.bug_manifest import make_variant
    monkeypatch.setattr(config, "ALLOW_USER_REPOS", True)
    calls = []

    def fake_clone(url, dest):
        calls.append(("clone", url))
        make_variant(config.DEMO_REPO_PATH, dest, {"B1"})
        return f"Cloned {url} (0.1 MB)."

    def fake_install(ws):
        calls.append(("install", ws.root.name))
        return "Installed dependencies (pytest only) into an isolated environment.", ["install pytest"]

    monkeypatch.setattr(repo_setup, "clone", fake_clone)
    monkeypatch.setattr(repo_setup, "install", fake_install)
    with make_client() as client:
        run_id = client.post("/api/runs", json={"repo_id": _user_repo(client)["id"]}).json()["id"]
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "fixed", run
        assert run["repo_url"] == "https://github.com/example/shop"
        tools = [s["tool_name"] for s in client.get(f"/api/runs/{run_id}/reasoning").json()["steps"] if s["tool_name"]]
        assert tools[:4] == ["clone_repo", "clone_repo", "install_deps", "install_deps"]
    assert calls == [("clone", "https://github.com/example/shop"), ("install", "repo")]


def test_user_repo_setup_failure_is_reported(make_client, monkeypatch):
    from codesentinel import config, repo_setup
    monkeypatch.setattr(config, "ALLOW_USER_REPOS", True)

    def failing_clone(url, dest):
        raise repo_setup.SetupError("The repository couldn't be cloned. Make sure the URL is correct and the repo is public.")

    monkeypatch.setattr(repo_setup, "clone", failing_clone)
    with make_client() as client:
        run_id = client.post("/api/runs", json={"repo_id": _user_repo(client)["id"]}).json()["id"]
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["status"] == "failed"
        assert "couldn't be cloned" in run["diagnosis_summary"]


def test_featured_runs_are_loaded_on_startup(tmp_path, monkeypatch):
    """A recorded run exported from one database appears, complete, in a fresh one."""
    import json

    import app.main as main_mod
    source = Store(tmp_path / "source.db")
    runner = RunManager(source, RunEventHub(), llm_factory=b1_script, workspaces_dir=tmp_path / "ws")
    with TestClient(create_app(source, runner)) as client:
        run_id = client.post("/api/runs", json={"repo_id": DEMO_REPO_ID, "bug_ids": ["B1"]}).json()["id"]
    fixtures = tmp_path / "featured_runs.json"
    fixtures.write_text(json.dumps({"runs": [source.export_run(run_id)]}), encoding="utf-8")
    monkeypatch.setattr(main_mod, "FEATURED_RUNS_FILE", fixtures)

    fresh = Store(tmp_path / "fresh.db")
    runner = RunManager(fresh, RunEventHub(), llm_factory=b1_script, workspaces_dir=tmp_path / "ws2")
    with TestClient(create_app(fresh, runner)) as client:
        featured = client.get("/api/runs/featured").json()["runs"]
        assert [r["id"] for r in featured] == [run_id]
        assert featured[0]["status"] == "fixed"
        assert client.get(f"/api/runs/{run_id}/reasoning").json()["steps"] == \
            TestClient(create_app(source, runner)).get(f"/api/runs/{run_id}/reasoning").json()["steps"]
        assert client.get(f"/api/runs/{run_id}/fix").json()["tests_passed"] is True
    # Loading twice is harmless.
    assert fresh.import_run(source.export_run(run_id)) is False
