"""CodeSentinel CLI — run the agent against a repository and watch the trace.

Examples (from backend/):
    .venv\\Scripts\\python run_agent.py                   # demo repo, all 11 bugs
    .venv\\Scripts\\python run_agent.py --bugs B1         # demo repo with only bug B1 planted
    .venv\\Scripts\\python run_agent.py --repo ..\\some-repo
"""
import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path

from codesentinel import config
from codesentinel.agent import Agent, AgentError
from codesentinel.db import new_id
from codesentinel.llm import LLMError, describe_provider, get_provider
from codesentinel.workspace import Workspace

ICONS = {"plan": "🧠 PLAN", "tool_call": "🔧 TOOL", "result": "📄 RESULT", "reflection": "🔁 REFLECT"}
COLORS = {"plan": "\033[36m", "tool_call": "\033[33m", "result": "\033[37m", "reflection": "\033[35m"}
RESET, BOLD = "\033[0m", "\033[1m"


class ConsoleObserver:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def on_step(self, step: dict) -> None:
        color = COLORS[step["step_type"]]
        label = ICONS[step["step_type"]]
        tool = f" [{step['tool_name']}]" if step["tool_name"] else ""
        body = textwrap.fill(step["content"], width=100, subsequent_indent=" " * 6)
        print(f"{color}{step['sequence']:>3}  {label}{tool}{RESET}\n      {body}")
        if self.verbose and step["step_type"] == "tool_call" and step["tool_input"]:
            print(textwrap.indent(json.dumps(step["tool_input"], indent=2)[:1500], " " * 6))

    def on_attempt(self, attempt: dict) -> None:
        verdict = "tests pass" if attempt["tests_passed"] else "tests still failing"
        print(f"{BOLD}      ── attempt {attempt['attempt_number']} recorded: {verdict}{RESET}")

    def on_run_update(self, fields: dict) -> None:
        if "attempt_count" in fields:
            print(f"\n{BOLD}══ Fix attempt {fields['attempt_count']} ══{RESET}")


def prepare_source(args) -> tuple[Path, Path | None]:
    """Return the repo to copy from, plus a temp dir to clean up (for --bugs variants)."""
    if args.bugs is None:
        return Path(args.repo).resolve(), None
    from eval.bug_manifest import make_variant
    tmp = config.WORKSPACES_DIR / f"_variant_{new_id('v')}"
    keep = {b.strip().upper() for b in args.bugs.split(",") if b.strip()}
    return make_variant(Path(args.repo).resolve(), tmp, keep), tmp


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run the CodeSentinel agent from the command line.")
    parser.add_argument("--repo", default=str(config.DEMO_REPO_PATH), help="Repository to fix (default: demo-repo)")
    parser.add_argument("--bugs", help="Demo repo only: comma-separated bug IDs to leave planted, e.g. B1,B4")
    parser.add_argument("--max-attempts", type=int, default=config.MAX_FIX_ATTEMPTS)
    parser.add_argument("--keep-workspace", action="store_true", help="Keep the patched copy for inspection")
    parser.add_argument("--verbose", action="store_true", help="Print raw tool inputs")
    args = parser.parse_args()

    try:
        llm = get_provider()
    except LLMError as e:
        print(e)
        return 2

    source, variant_dir = prepare_source(args)
    run_id = new_id("run")
    ws = Workspace.create(source, run_id)
    print(f"{BOLD}CodeSentinel{RESET} run {run_id}\n  repo:      {source}\n  workspace: {ws.root}\n"
          f"  model:     {describe_provider()}\n")

    try:
        result = Agent(ws, run_id, [ConsoleObserver(args.verbose)], max_attempts=args.max_attempts, llm=llm).run()
    except AgentError as e:
        print(f"\n\033[31mRun stopped: {e}{RESET}")
        return 2
    finally:
        if variant_dir:
            shutil.rmtree(variant_dir, ignore_errors=True)

    labels = {"fixed": "Fixed & Verified", "failed": "Could Not Fix", "needs_review": "Needs Review"}
    print(f"\n{BOLD}══ Result: {labels[result.status]} ══{RESET}")
    print(f"  Diagnosis:  {result.diagnosis_summary}")
    if result.confidence is not None:
        print(f"  Confidence: {result.confidence:.2f}")
    print(f"  Tests:      {result.initial_tests['failed'] + result.initial_tests['errors']} failing before → "
          f"{result.final_tests['failed'] + result.final_tests['errors']} failing after "
          f"({result.final_tests['total']} total)")
    print(f"  Attempts:   {result.attempt_count}    Time: {result.duration_s}s    "
          f"API calls: {result.usage['api_calls']}    Tokens: {result.usage['input_tokens']} in / "
          f"{result.usage['output_tokens']} out")

    if args.keep_workspace:
        print(f"  Workspace kept at {ws.root}")
    else:
        ws.cleanup()
    return 0 if result.status == "fixed" else 1


if __name__ == "__main__":
    sys.exit(main())
