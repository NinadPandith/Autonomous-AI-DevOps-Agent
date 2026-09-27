"""FastAPI app: REST endpoints + live WebSocket trace.

Run locally (from backend/):
    .venv\\Scripts\\uvicorn app.main:app --reload
Interactive API docs: http://localhost:8010/docs
"""
import asyncio
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from codesentinel import config
from eval.bug_manifest import load_bugs

from .events import RunEventHub
from .runner import AgentBusy, RunManager, status_message, step_message
from .store import DEMO_REPO_ID, Store

GITHUB_URL_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(?:\.git)?/?$")
RUN_STATUSES = ("running", "fixed", "failed", "needs_review")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class CreateRepo(BaseModel):
    repo_url: str


class CreateRun(BaseModel):
    repo_id: str
    bug_ids: list[str] | None = Field(
        default=None,
        description="Demo repo only: which planted bugs to leave in (e.g. ['B1']). Omit to keep all of them.",
    )


def create_app(store: Store | None = None, runner: RunManager | None = None) -> FastAPI:
    store = store or Store(config.DATABASE_PATH)
    hub = runner.hub if runner else RunEventHub()
    runner = runner or RunManager(store, hub)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.bind_loop(asyncio.get_running_loop())
        store.ensure_demo_repo()
        store.mark_interrupted_runs()
        for bundle in _featured_bundles():
            store.import_run(bundle)
        yield

    app = FastAPI(title="CodeSentinel API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=config.FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"],
    )
    app.state.store, app.state.runner = store, runner

    # ---------------------------------------------------------- errors

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR", "message": f"Invalid request: {where} {first.get('msg', '')}".strip(),
        }})

    api = APIRouter(prefix="/api")

    def get_run_or_404(run_id: str) -> dict:
        run = store.get_run(run_id)
        if not run:
            raise ApiError(404, "RUN_NOT_FOUND", "No run found with that ID.")
        return run

    # ----------------------------------------------------------- repos

    @api.get("/health")
    def health():
        return {"status": "ok", "llm_provider": config.LLM_PROVIDER, "agent_busy": runner.active_run_id is not None,
                "max_runs_per_day": config.MAX_RUNS_PER_DAY or None, "allow_user_repos": config.ALLOW_USER_REPOS}

    @api.get("/repos/demo")
    def get_demo_repo():
        return store.ensure_demo_repo()

    @api.get("/repos/demo/scenarios")
    def list_demo_scenarios():
        """Planted bugs a run can target individually. Titles and difficulty only — never the fixes."""
        return {"scenarios": [
            {"id": b["id"], "title": b["title"], "difficulty": b["difficulty"], "bug_type": b["bug_type"]}
            for b in load_bugs()
        ]}

    @api.post("/repos", status_code=201)
    def create_repo(body: CreateRepo):
        url = body.repo_url.strip().removesuffix("/")
        if not GITHUB_URL_RE.match(url):
            raise ApiError(422, "INVALID_REPO_URL",
                           "That doesn't look like a GitHub repository URL, e.g. https://github.com/user/repo.")
        url = url.removesuffix(".git")
        if existing := store.find_repo_by_url(url):
            return existing
        info = _github_repo_info(url)
        if info is False or (info is None and not _is_public_git_repo(url)):
            raise ApiError(422, "REPO_NOT_ACCESSIBLE",
                           "That repository couldn't be accessed. Make sure the URL is correct and the repo is public.")
        if info and info.get("size_kb", 0) > config.USER_REPO_MAX_MB * 1000:
            raise ApiError(422, "REPO_TOO_LARGE",
                           f"That repository is about {info['size_kb'] // 1000} MB; this server accepts up to "
                           f"{config.USER_REPO_MAX_MB} MB.")
        return store.create_repo(url, "user_provided", default_branch=(info or {}).get("default_branch", "main"))

    # ------------------------------------------------------------ runs

    @api.post("/runs", status_code=201)
    def create_run(body: CreateRun, background: BackgroundTasks):
        repo = store.get_repo(body.repo_id)
        if not repo:
            raise ApiError(404, "REPO_NOT_FOUND", "No repository found with that ID.")
        if repo["source_type"] != "demo" and not config.ALLOW_USER_REPOS:
            raise ApiError(403, "USER_REPOS_DISABLED",
                           "Running the agent on your own repositories isn't enabled on this server yet. "
                           "Use the demo repository.")
        bug_ids = None
        if body.bug_ids is not None:
            known = {b["id"] for b in load_bugs()}
            bug_ids = sorted({b.strip().upper() for b in body.bug_ids})
            if not bug_ids or not set(bug_ids) <= known:
                raise ApiError(422, "UNKNOWN_BUG_ID", f"bug_ids must be a non-empty subset of {sorted(known)}.")
        if config.MAX_RUNS_PER_DAY:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
            featured_ids = {b["run"]["id"] for b in _featured_bundles()}
            if store.count_runs_since(today, featured_ids) >= config.MAX_RUNS_PER_DAY:
                raise ApiError(429, "DAILY_LIMIT_REACHED",
                               "This demo has reached its run limit for today. Past runs are still available "
                               "under History, and new runs open again tomorrow (UTC).")
        try:
            run = runner.start(repo, bug_ids)
        except AgentBusy as busy:
            raise ApiError(409, "AGENT_BUSY",
                           f"The agent is already working on run {busy.args[0]}. Please try again when it finishes.")
        background.add_task(runner.execute, run["id"], repo, bug_ids)
        return {"id": run["id"], "status": run["status"], "started_at": run["started_at"]}

    @api.get("/runs")
    def list_runs(status: Literal["running", "fixed", "failed", "needs_review"] | None = None):
        repo_urls = {}
        runs = []
        for run in store.list_runs(status):
            if run["repo_id"] not in repo_urls:
                repo_urls[run["repo_id"]] = (store.get_repo(run["repo_id"]) or {}).get("repo_url")
            runs.append({**run, "repo_url": repo_urls[run["repo_id"]]})
        return {"runs": runs}

    @api.get("/runs/featured")
    def featured_runs():
        """Recorded real runs shipped with the app, for the public demo's replay mode."""
        featured = []
        for bundle in _featured_bundles():
            run = store.get_run(bundle["run"]["id"])
            if run:
                featured.append({**run, "repo_url": bundle["repo"]["repo_url"]})
        return {"runs": featured}

    @api.get("/runs/{run_id}")
    def get_run(run_id: str):
        run = get_run_or_404(run_id)
        repo = store.get_repo(run["repo_id"]) or {}
        return {**run, "repo_url": repo.get("repo_url"), "repo_source_type": repo.get("source_type"),
                "max_attempts": config.MAX_FIX_ATTEMPTS}

    @api.get("/runs/{run_id}/reasoning")
    def get_reasoning(run_id: str):
        get_run_or_404(run_id)
        steps = [{k: v for k, v in s.items() if k not in ("id", "run_id")} for s in store.list_steps(run_id)]
        return {"run_id": run_id, "steps": steps}

    @api.get("/runs/{run_id}/fix")
    def get_fix(run_id: str):
        get_run_or_404(run_id)
        attempts = store.list_fix_attempts(run_id)
        if not attempts:
            raise ApiError(404, "NO_FIX_YET", "This run hasn't produced a fix attempt yet.")
        best = next((a for a in reversed(attempts) if a["tests_passed"]), attempts[-1])
        return {
            "run_id": run_id,
            "attempt_number": best["attempt_number"],
            "total_attempts": len(attempts),
            "diff_before": best["diff_before"],
            "diff_after": best["diff_after"],
            "files_changed": re.findall(r"^# ===== (.+?) =====$", best["diff_after"], re.MULTILINE),
            "tests_passed": best["tests_passed"],
            "tests_summary": _pytest_summary(best["test_output"]),
        }

    app.include_router(api)

    # ------------------------------------------------------- websocket

    @app.websocket("/ws/runs/{run_id}")
    async def run_socket(ws: WebSocket, run_id: str):
        await ws.accept()
        run = store.get_run(run_id)
        if not run:
            await ws.send_json({"type": "error", "data": {"message": "No run found with that ID."}})
            await ws.close(code=4404)
            return

        # Subscribe before replaying history so nothing emitted in between is lost.
        queue = hub.subscribe(run_id)
        try:
            last_seq = -1
            for step in store.list_steps(run_id):
                await ws.send_json(step_message(step))
                last_seq = step["sequence"]
            run = store.get_run(run_id)
            await ws.send_json(status_message(run))
            if run["status"] != "running":
                await ws.close()
                return

            while True:
                message = await queue.get()
                if message["type"] == "reasoning_step":
                    if message["data"]["sequence"] <= last_seq:
                        continue
                    last_seq = message["data"]["sequence"]
                await ws.send_json(message)
                if message["type"] == "status_update" and message["data"]["status"] != "running":
                    await ws.close()
                    return
        except WebSocketDisconnect:
            pass
        finally:
            hub.unsubscribe(run_id, queue)

    return app


FEATURED_RUNS_FILE = config.BACKEND_DIR / "fixtures" / "featured_runs.json"


def _featured_bundles() -> list[dict]:
    try:
        return json.loads(FEATURED_RUNS_FILE.read_text(encoding="utf-8"))["runs"]
    except (FileNotFoundError, ValueError, KeyError):
        return []


def _github_repo_info(url: str) -> dict | None | bool:
    """Ask the GitHub API about a repo. dict = public repo info, False = missing/private, None = couldn't tell."""
    owner_repo = url.removeprefix("https://github.com/")
    req = urllib.request.Request(f"https://api.github.com/repos/{owner_repo}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "CodeSentinel"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None  # 403 = API rate limit: fall back to git ls-remote
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    if data.get("private"):
        return False
    return {"size_kb": data.get("size", 0), "default_branch": data.get("default_branch", "main"),
            "language": data.get("language")}


def _is_public_git_repo(url: str) -> bool:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        proc = subprocess.run(["git", "ls-remote", "--heads", url], capture_output=True, text=True,
                              timeout=20, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _pytest_summary(output: str) -> str:
    lines = [ln.strip(" =") for ln in output.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


app = create_app()
