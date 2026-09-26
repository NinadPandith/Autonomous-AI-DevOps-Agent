"""Starts agent runs in the background and records everything they emit.

One run at a time: the free LLM tier has tight quotas, and the demo box is
small. A second POST /runs while one is active gets AGENT_BUSY.
"""
import logging
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from codesentinel import config, repo_setup
from codesentinel.agent import Agent, AgentError, RunTimeout
from codesentinel.db import new_id, now_iso
from codesentinel.llm import LLMError, LLMProvider, get_provider
from codesentinel.repo_setup import SetupError
from codesentinel.workspace import Workspace
from eval.bug_manifest import make_variant

from .events import RunEventHub
from .store import Store

log = logging.getLogger(__name__)

STEP_FIELDS = ("sequence", "step_type", "content", "tool_name", "tool_input", "tool_output", "created_at")


class AgentBusy(Exception):
    pass


def _user_repo_setup(ws: Workspace, url: str):
    """Build the Agent setup hook that clones and installs a user repository, narrating each step."""
    def setup(trace) -> None:
        trace.tool_call("clone_repo", f"Cloning {url}.", {"url": url})
        try:
            summary = repo_setup.clone(url, ws.root)
        except SetupError as e:
            trace.result("clone_repo", f"The clone failed: {e}", {"error": str(e)})
            raise
        trace.result("clone_repo", summary)

        trace.tool_call("install_deps", "Installing the project's dependencies into an isolated environment.")
        try:
            summary, commands = repo_setup.install(ws)
        except SetupError as e:
            trace.result("install_deps", "Dependency installation failed.", {"error": str(e)})
            raise
        trace.result("install_deps", summary, {"commands": commands})
    return setup


def step_message(step: dict) -> dict:
    return {"type": "reasoning_step", "data": {k: step.get(k) for k in STEP_FIELDS}}


def status_message(run: dict) -> dict:
    return {"type": "status_update", "data": {
        "run_id": run["id"], "status": run["status"], "attempt_count": run["attempt_count"],
        "completed_at": run["completed_at"],
    }}


class RunObserver:
    """Persists the agent's trace and pushes it to live subscribers."""

    RUN_FIELDS = {"attempt_count", "diagnosis_summary", "final_confidence_score"}

    def __init__(self, store: Store, hub: RunEventHub, run_id: str):
        self.store, self.hub, self.run_id = store, hub, run_id

    def on_step(self, step: dict) -> None:
        self.store.add_step(step)
        self.hub.publish(self.run_id, step_message(step))

    def on_attempt(self, attempt: dict) -> None:
        self.store.add_fix_attempt(
            self.run_id, attempt["attempt_number"], attempt["diff_before"], attempt["diff_after"],
            attempt["tests_passed"], attempt["test_output"],
        )

    def on_run_update(self, fields: dict) -> None:
        fields = {k: v for k, v in fields.items() if k in self.RUN_FIELDS}
        if not fields:
            return
        run = self.store.update_run(self.run_id, **fields)
        if "attempt_count" in fields:
            self.hub.publish(self.run_id, status_message(run))


class RunManager:
    def __init__(self, store: Store, hub: RunEventHub,
                 llm_factory: Callable[[], LLMProvider] = get_provider,
                 workspaces_dir: Path = config.WORKSPACES_DIR):
        self.store = store
        self.hub = hub
        self.llm_factory = llm_factory
        self.workspaces_dir = workspaces_dir
        self._busy = threading.Lock()
        self.active_run_id: str | None = None

    def start(self, repo: dict, bug_ids: list[str] | None) -> dict:
        """Create the run row and claim the single run slot. The caller schedules execute()."""
        if not self._busy.acquire(blocking=False):
            raise AgentBusy(self.active_run_id)
        try:
            run = self.store.create_run(repo["id"])
        except Exception:
            self._busy.release()
            raise
        self.active_run_id = run["id"]
        return run

    def execute(self, run_id: str, repo: dict, bug_ids: list[str] | None) -> None:
        """Run the agent to completion. Always releases the run slot."""
        variant_dir = ws = None
        setup = None
        try:
            if repo["source_type"] == "demo":
                source = config.DEMO_REPO_PATH
                if bug_ids is not None:
                    variant_dir = self.workspaces_dir / f"_variant_{new_id('v')}"
                    source = make_variant(config.DEMO_REPO_PATH, variant_dir, set(bug_ids))
                ws = Workspace.create(source, run_id, base=self.workspaces_dir)
            else:
                ws = Workspace.empty(run_id, base=self.workspaces_dir)
                setup = _user_repo_setup(ws, repo["repo_url"])

            agent = Agent(ws, run_id, [RunObserver(self.store, self.hub, run_id)],
                          llm=self.llm_factory(), time_limit_s=config.RUN_TIME_LIMIT_S, setup=setup)
            result = agent.run()
            run = self.store.update_run(
                run_id, status=result.status, completed_at=now_iso(), attempt_count=result.attempt_count,
                diagnosis_summary=result.diagnosis_summary or None, final_confidence_score=result.confidence,
            )
        except Exception as e:
            if isinstance(e, (RunTimeout, SetupError)):
                message = str(e)
            elif isinstance(e, (AgentError, LLMError)):
                message = f"The agent stopped: {e}"
            else:
                log.exception("Run %s crashed", run_id)
                message = "The agent hit an unexpected internal error and stopped."
            current = self.store.get_run(run_id)
            run = self.store.update_run(
                run_id, status="failed", completed_at=now_iso(),
                diagnosis_summary=current.get("diagnosis_summary") or message,
            )
            self.hub.publish(run_id, {"type": "error", "data": {"message": message}})
        finally:
            if ws:
                ws.cleanup()
            if variant_dir:
                shutil.rmtree(variant_dir, ignore_errors=True)
            self.active_run_id = None
            self._busy.release()

        self.hub.publish(run_id, status_message(run))
