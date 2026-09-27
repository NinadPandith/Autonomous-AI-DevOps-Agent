r"""Evaluation harness — produces the PRD §10 metrics for the report.

For each planted bug, runs the agent on a copy of the demo repo with only that
bug present, and records: fixed (full suite passes), root cause localized
(the agent changed the buggy code in the right file), bug type classified,
attempts, time and API usage. Optionally runs a single-shot baseline (one LLM
call, no loop, no verification/retry) on the same bugs for comparison.

Usage (from backend/):
    .venv\Scripts\python scripts\evaluate.py                    # all 11 bugs, agent only
    .venv\Scripts\python scripts\evaluate.py --baseline         # agent + single-shot baseline
    .venv\Scripts\python scripts\evaluate.py --bugs B1,B7
    .venv\Scripts\python scripts\evaluate.py --resume eval\results\eval_XXXX.json

Free-tier note: each agent run uses roughly 3–8 requests. Results are saved
after every bug, so a run stopped by the daily quota can be resumed tomorrow.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codesentinel import config  # noqa: E402
from codesentinel.agent import Agent, AgentError  # noqa: E402
from codesentinel.db import new_id  # noqa: E402
from codesentinel.llm import LLMError, describe_provider, get_provider  # noqa: E402
from codesentinel.tools import code_reader, patcher, test_runner  # noqa: E402
from codesentinel.workspace import Workspace, WorkspaceError  # noqa: E402
from eval.bug_manifest import load_bugs, make_variant  # noqa: E402

RESULTS_DIR = config.BACKEND_DIR / "eval" / "results"

BASELINE_SYSTEM = "You fix bugs in Python code. Reply only with the JSON requested."
BASELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string", "description": "Exact existing text, copied verbatim"},
                    "new_str": {"type": "string"},
                },
                "required": ["path", "old_str", "new_str"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["diagnosis", "edits"],
    "additionalProperties": False,
}


class Collector:
    def __init__(self):
        self.steps = []

    def on_step(self, step):
        self.steps.append(step)
        if step["step_type"] in ("plan", "reflection"):
            print(f"      {step['step_type']:<10} {step['content'][:110]}")

    def on_attempt(self, attempt):
        pass

    def on_run_update(self, fields):
        pass


def localized(ws: Workspace, bug: dict, changed_files: set[str]) -> bool:
    """Root cause localized: the fix changed the file that contains the planted bug.

    (Checking that the buggy line disappeared is wrong for fixes that add a guard *before* an
    otherwise-correct line, e.g. B5, so the file-level check is used.)
    """
    return bug["file"] in changed_files


def run_agent_on(bug: dict, tmp: Path) -> dict:
    source = make_variant(config.DEMO_REPO_PATH, tmp / f"src_{bug['id']}", {bug["id"]})
    run_id = new_id("eval")
    ws = Workspace.create(source, run_id, base=tmp)
    collector = Collector()
    llm = get_provider()
    started = time.monotonic()
    try:
        agent = Agent(ws, run_id, [collector], llm=llm, time_limit_s=config.RUN_TIME_LIMIT_S)
        result = agent.run()
        changed = set(agent.original_files)
        return {
            "status": result.status,
            "fixed": result.final_tests["all_passed"],
            "localized": localized(ws, bug, changed),
            "type_classified": bug["bug_type"] in result.bug_types,
            "attempts": result.attempt_count,
            "duration_s": result.duration_s,
            "diagnosis": result.diagnosis_summary,
            "predicted_bug_types": result.bug_types,
            "files_changed": sorted(changed),
            "usage": result.usage,
        }
    except AgentError as e:
        return {"status": "error", "fixed": False, "localized": False, "type_classified": False,
                "attempts": None, "duration_s": round(time.monotonic() - started, 1), "error": str(e),
                "usage": {**llm.usage.to_dict(), "model": llm.model}}
    finally:
        ws.cleanup()


def run_baseline_on(bug: dict, tmp: Path) -> dict:
    """Single-shot: one LLM call with the failures + all source, no tools, no verification loop."""
    source = make_variant(config.DEMO_REPO_PATH, tmp / f"bsrc_{bug['id']}", {bug["id"]})
    ws = Workspace.create(source, new_id("base"), base=tmp)
    started = time.monotonic()
    llm = get_provider()
    try:
        before = test_runner.run_tests(ws)
        files = [f for f in code_reader.list_files(ws) if f.endswith(".py") and not Workspace.is_test_path(f)]
        sources = "\n\n".join(f"### {f}\n```python\n{ws.read(f)}\n```" for f in files)
        prompt = (f"These tests fail:\n```\n{before.output[-8000:]}\n```\n\nSource files:\n{sources}\n\n"
                  "Fix the bug in the source code (never the tests). Return edits whose old_str is copied "
                  "exactly from the files above.")
        answer = llm.structured(BASELINE_SYSTEM, prompt, BASELINE_SCHEMA)
        changed, rejected = set(), 0
        for edit in answer.get("edits", []):
            try:
                patcher.edit_file(ws, edit["path"], edit["old_str"], edit["new_str"])
                changed.add(edit["path"])
            except (patcher.PatchError, WorkspaceError):
                rejected += 1
        after = test_runner.run_tests(ws)
        return {"fixed": after.all_passed, "localized": localized(ws, bug, changed), "edits_rejected": rejected,
                "duration_s": round(time.monotonic() - started, 1), "diagnosis": answer.get("diagnosis", ""),
                "usage": {**llm.usage.to_dict(), "model": llm.model}}
    except LLMError as e:
        return {"fixed": False, "localized": False, "error": str(e),
                "duration_s": round(time.monotonic() - started, 1)}
    finally:
        ws.cleanup()


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "—"


def summarize(results: dict, bugs: list[dict]) -> str:
    rows = [r for r in (results["bugs"].get(b["id"]) for b in bugs) if r and "agent" in r]
    agent = [r["agent"] for r in rows]
    done = [a for a in agent if a["status"] != "error"]
    lines = [
        f"# CodeSentinel evaluation — {results['started_at']}",
        "",
        f"Model: {results['model']}. One run per planted bug; each run starts from the demo repo with only that bug present.",
        "",
        "| Metric | Agent (plan-act-reflect loop) |" + (" Single-shot baseline |" if results["baseline"] else ""),
        "|---|---|" + ("---|" if results["baseline"] else ""),
    ]
    base = [r["baseline"] for r in rows if "baseline" in r]
    def row(label, a, b=None):
        lines.append(f"| {label} | {a} |" + (f" {b} |" if results["baseline"] else ""))
    row("Bugs fixed (all tests pass)", pct(sum(a["fixed"] for a in agent), len(agent)),
        pct(sum(b["fixed"] for b in base), len(base)))
    row("Root cause localized", pct(sum(a["localized"] for a in agent), len(agent)),
        pct(sum(b["localized"] for b in base), len(base)))
    row("Bug type classified", pct(sum(a["type_classified"] for a in agent), len(agent)), "—")
    fixed = [a for a in done if a["fixed"]]
    row("Avg. attempts (fixed bugs)", f"{sum(a['attempts'] for a in fixed) / len(fixed):.2f}" if fixed else "—", "1 (by design)")
    row("Avg. time per run", f"{sum(a['duration_s'] for a in agent) / len(agent):.0f}s" if agent else "—",
        f"{sum(b['duration_s'] for b in base) / len(base):.0f}s" if base else "—")
    row("Avg. API requests per run",
        f"{sum(a['usage'].get('api_calls', 0) for a in agent) / len(agent):.1f}" if agent else "—",
        f"{sum(b.get('usage', {}).get('api_calls', 0) for b in base) / len(base):.1f}" if base else "—")

    lines += ["", "## Per bug", "",
              "| Bug | Difficulty | Type | Agent | Attempts | Time | Localized | Model |" + (" Baseline |" if results["baseline"] else ""),
              "|---|---|---|---|---|---|---|---|" + ("---|" if results["baseline"] else "")]
    for b in bugs:
        r = results["bugs"].get(b["id"])
        if not r or "agent" not in r:
            continue
        a = r["agent"]
        verdict = "✅ fixed" if a["fixed"] else ("⚠️ error" if a["status"] == "error" else "❌ not fixed")
        cells = [f"{b['id']} {b['title']}", b["difficulty"], b["bug_type"], verdict, str(a["attempts"] or "—"),
                 f"{a['duration_s']:.0f}s", "yes" if a["localized"] else "no",
                 a.get("usage", {}).get("model", "—")]
        if results["baseline"]:
            cells.append("✅" if r.get("baseline", {}).get("fixed") else "❌")
        lines.append("| " + " | ".join(cells) + " |")
    errors = [(bid, r["agent"]["error"]) for bid, r in results["bugs"].items() if r.get("agent", {}).get("error")]
    if errors:
        lines += ["", "Runs that stopped with an error (not counted as agent failures in a fair comparison):"]
        lines += [f"- {bid}: {msg}" for bid, msg in errors]
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bugs", help="Comma-separated bug IDs (default: all)")
    parser.add_argument("--baseline", action="store_true", help="Also run the single-shot baseline")
    parser.add_argument("--resume", help="Results JSON from an earlier (partial) evaluation")
    parser.add_argument("--report", help="Only rebuild the Markdown report from a results JSON (no API calls)")
    args = parser.parse_args()

    if args.report:
        path = Path(args.report)
        results = json.loads(path.read_text(encoding="utf-8"))
        by_id = {b["id"]: b for b in load_bugs()}
        for bid, entry in results["bugs"].items():
            if "agent" in entry and "files_changed" in entry["agent"]:
                entry["agent"]["localized"] = by_id[bid]["file"] in entry["agent"]["files_changed"]
        path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        summary = summarize(results, load_bugs())
        path.with_suffix(".md").write_text(summary, encoding="utf-8")
        print(summary)
        return 0

    bugs = load_bugs()
    if args.bugs:
        wanted = {b.strip().upper() for b in args.bugs.split(",")}
        bugs = [b for b in bugs if b["id"] in wanted]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if args.resume:
        out_path = Path(args.resume)
        results = json.loads(out_path.read_text(encoding="utf-8"))
        results["baseline"] = results["baseline"] or args.baseline
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"eval_{stamp}.json"
        results = {"started_at": datetime.now().isoformat(timespec="seconds"), "model": describe_provider(),
                   "baseline": args.baseline, "bugs": {}}

    tmp = config.WORKSPACES_DIR / "_eval"
    tmp.mkdir(parents=True, exist_ok=True)
    print(f"Evaluating {len(bugs)} bug(s) with {describe_provider()}\nResults: {out_path}\n")

    stop = False
    for bug in bugs:
        entry = results["bugs"].setdefault(bug["id"], {})
        if "agent" not in entry or entry["agent"]["status"] == "error":
            print(f"▶ {bug['id']} [{bug['difficulty']}] {bug['title']} — agent")
            entry["agent"] = run_agent_on(bug, tmp)
            a = entry["agent"]
            print(f"  → {a['status']}, fixed={a['fixed']}, localized={a['localized']}, {a['duration_s']}s"
                  + (f"  ERROR: {a['error']}" if a.get("error") else ""))
            out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
            stop = "out of free-tier quota" in a.get("error", "")
        if args.baseline and not stop and ("baseline" not in entry or entry["baseline"].get("error")):
            print(f"▶ {bug['id']} — single-shot baseline")
            entry["baseline"] = run_baseline_on(bug, tmp)
            print(f"  → fixed={entry['baseline']['fixed']}" + (f"  ERROR: {entry['baseline']['error']}" if entry['baseline'].get('error') else ""))
            out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
            stop = "out of free-tier quota" in entry["baseline"].get("error", "")
        if stop:
            print("\nStopping: every model is out of free-tier quota. Resume tomorrow with --resume.")
            break

    summary = summarize(results, load_bugs())
    out_path.with_suffix(".md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Saved {out_path} and {out_path.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
