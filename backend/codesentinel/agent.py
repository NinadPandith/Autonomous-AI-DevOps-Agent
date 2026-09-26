"""The agent loop: Plan -> Act -> Observe -> Reflect -> Retry.

The controller (this file) owns the outer loop, so self-verification is
guaranteed rather than left to the model:

    1. Run the tests and localize failures            (Observe)
    2. The LLM investigates and edits via tools       (Plan + Act)
    3. Run the full suite again                       (Observe / verify)
    4. The LLM evaluates the outcome                  (Reflect)
    5. If tests still fail and attempts remain, feed the failures back and retry.
       An attempt that makes things worse is rolled back first.

Every step is emitted to the Trace in the `reasoning_steps` shape.
"""
import time
from dataclasses import dataclass, field

from . import config
from .llm import LLMError, LLMProvider, ToolCall, ToolResult, get_provider
from .prompts import REFLECT_SYSTEM, REFLECTION_SCHEMA, SYSTEM_PROMPT, TOOLS
from .tools import code_reader, failure_parser, patcher, test_runner
from .tools.test_runner import TestRunResult
from .trace import AgentObserver, Trace
from .workspace import Workspace, WorkspaceError

MAX_TURNS_PER_ATTEMPT = 15
MAX_OUTPUT_IN_PROMPT = 12_000
MAX_PREFETCH_CHARS = 30_000
MAX_LISTED_FILES = 250


class AgentError(Exception):
    """The agent could not continue (API failure, refusal, sandbox problem)."""


class RunTimeout(AgentError):
    """The run exceeded its wall-clock time limit."""


@dataclass
class RunResult:
    run_id: str
    status: str  # fixed | failed | needs_review
    attempt_count: int
    diagnosis_summary: str
    confidence: float | None
    bug_types: list[str]
    initial_tests: dict
    final_tests: dict
    duration_s: float
    usage: dict = field(default_factory=dict)


def _truncate(text: str, limit: int = MAX_OUTPUT_IN_PROMPT) -> str:
    return text if len(text) <= limit else "... (truncated) ...\n" + text[-limit:]


def _concat_files(files: dict[str, str]) -> str:
    return "".join(f"# ===== {path} =====\n{content}{'' if content.endswith(chr(10)) else chr(10)}"
                   for path, content in sorted(files.items()))


class Agent:
    def __init__(self, workspace: Workspace, run_id: str, observers: list[AgentObserver] | None = None,
                 max_attempts: int = config.MAX_FIX_ATTEMPTS, llm: LLMProvider | None = None,
                 time_limit_s: float | None = None, setup=None):
        self.ws = workspace
        self.run_id = run_id
        self.trace = Trace(run_id, observers or [])
        self.max_attempts = max_attempts
        self.time_limit_s = time_limit_s
        self.setup = setup  # optional callable(trace) that prepares the workspace (clone + install)
        self.deadline: float | None = None
        try:
            self.llm = llm or get_provider()
        except LLMError as e:
            raise AgentError(str(e)) from e
        if hasattr(self.llm, "on_model_switch"):
            self.llm.on_model_switch = lambda old, new, reason: self.trace.result(
                "llm", f"Switched the language model from {old} to {new} ({reason}).",
                {"from": old, "to": new, "reason": reason})
        self.convo = None
        self.pending_tool_results: list[ToolResult] = []
        self.pending_submit: ToolCall | None = None
        self.original_files: dict[str, str] = {}  # contents before the run's first edit
        self.attempt_snapshot: dict[str, str] = {}  # contents before the current attempt's first edit

    # ------------------------------------------------------------------ run

    def run(self) -> RunResult:
        start = time.monotonic()
        self.deadline = start + self.time_limit_s if self.time_limit_s else None
        t = self.trace

        if self.setup:
            t.plan("I'll clone the repository and install its dependencies in an isolated environment first.")
            self.setup(t)
            self._check_deadline()

        t.plan("I'll start by running the test suite to see what is currently failing.")
        initial = self._run_tests("Running the test suite to check current status.")
        if initial.all_passed:
            t.reflection("Every test already passes, so there is nothing for me to fix in this repository.")
            return self._finish("needs_review", 0, "No failing tests were found.", None, [], initial, initial, start)
        if initial.exit_code == 5:  # pytest: no tests collected
            t.reflection("pytest found no tests in this repository, so I have nothing to verify a fix against.")
            return self._finish("needs_review", 0, "No pytest tests were found in this repository.", None, [],
                                initial, initial, start)
        if initial.total == 0 and not initial.timed_out:
            t.reflection("pytest could not collect the tests, so I'll treat this as an import or syntax problem first.")

        suspects = self._localize(initial)
        self.convo = self.llm.conversation(SYSTEM_PROMPT, TOOLS)
        self.convo.add_user_text(self._initial_prompt(initial, suspects))

        current = initial
        diagnosis, confidence, bug_types = "", None, []
        attempt = 0
        for attempt in range(1, self.max_attempts + 1):
            t.run_update(attempt_count=attempt)
            self.attempt_snapshot = {}
            submitted = self._attempt(attempt)
            if submitted.get("diagnosis"):
                diagnosis = submitted["diagnosis"]

            if not self.attempt_snapshot:
                verify = current
                t.result("run_tests", "No files were changed in this attempt, so the test results are unchanged.")
            else:
                verify = self._run_tests(f"Running the full test suite to verify fix attempt {attempt}.")

            diff_before, diff_after = self._cumulative_diff()
            t.attempt({
                "run_id": self.run_id, "attempt_number": attempt,
                "diff_before": diff_before, "diff_after": diff_after,
                "tests_passed": verify.all_passed, "test_output": verify.output,
            })

            reverted = False
            if not verify.all_passed and self.attempt_snapshot and verify.not_passing >= current.not_passing:
                self._revert_attempt()
                reverted = True

            refl = self._reflect(attempt, submitted, current, verify, reverted)
            t.reflection(refl["reflection"])
            diagnosis = refl.get("diagnosis_summary") or diagnosis
            confidence = refl.get("confidence", submitted.get("confidence"))
            bug_types = refl.get("bug_types", [])
            t.run_update(diagnosis_summary=diagnosis, final_confidence_score=confidence)

            if verify.all_passed:
                current = verify
                break
            if not reverted:
                current = verify
            if attempt < self.max_attempts:
                self._queue_feedback(attempt, verify, refl["reflection"], reverted)

        if current.all_passed:
            status = "fixed" if (confidence is None or confidence >= 0.5) else "needs_review"
        elif current.not_passing < initial.not_passing:
            status = "needs_review"
        else:
            status = "failed"
        return self._finish(status, attempt, diagnosis, confidence, bug_types, initial, current, start)

    def _finish(self, status, attempts, diagnosis, confidence, bug_types, initial, final, start) -> RunResult:
        return RunResult(
            run_id=self.run_id, status=status, attempt_count=attempts,
            diagnosis_summary=diagnosis, confidence=confidence, bug_types=bug_types,
            initial_tests=initial.to_dict(max_output=4000), final_tests=final.to_dict(max_output=4000),
            duration_s=round(time.monotonic() - start, 1),
            usage={**self.llm.usage.to_dict(), "provider": self.llm.name, "model": self.llm.model},
        )

    # ------------------------------------------------------------- observe

    def _run_tests(self, description: str) -> TestRunResult:
        self.trace.tool_call("run_tests", description, {"command": "python -m pytest -q --tb=short"})
        result = test_runner.run_tests(self.ws)
        content = result.summary()
        if result.failing_tests and not result.all_passed:
            names = ", ".join(t.split("::")[-1] for t in result.failing_tests[:4])
            more = f" and {len(result.failing_tests) - 4} more" if len(result.failing_tests) > 4 else ""
            content += f" Failing: {names}{more}."
        self.trace.result("run_tests", content, result.to_dict())
        return result

    def _localize(self, tests: TestRunResult) -> list[failure_parser.Suspect]:
        self.trace.tool_call("parse_failures", "Parsing the failure output to locate the likely faulty code.")
        failures = failure_parser.parse_failures(tests.output)
        suspects = failure_parser.locate_suspects(self.ws, failures)
        if suspects:
            where = "; ".join(f"{s.function}() in {s.file}" for s in suspects[:4])
            content = f"Parsed {len(failures)} failures. Likely locations: {where}."
        else:
            content = f"Parsed {len(failures)} failures but could not pin them to specific functions."
        self.trace.result("parse_failures", content, {
            "failures": failure_parser.to_dicts(failures), "suspects": failure_parser.to_dicts(suspects),
        })
        return suspects

    # ---------------------------------------------------------- plan + act

    def _initial_prompt(self, tests: TestRunResult, suspects) -> str:
        suspect_lines = "\n".join(
            f"- {s.file} — {s.function}() ({s.reason}; {len(s.tests)} failing test{'s' if len(s.tests) != 1 else ''})"
            for s in suspects
        ) or "- (none identified)"
        all_files = code_reader.list_files(self.ws)
        files = "\n".join(f"- {f}" for f in all_files[:MAX_LISTED_FILES])
        if len(all_files) > MAX_LISTED_FILES:
            files += f"\n- … and {len(all_files) - MAX_LISTED_FILES} more (use search_code or list_files)"

        # Include source up front — suspect files first, then any other non-test source that fits the
        # budget. Each file included saves a read_file round-trip, i.e. one API request.
        all_source = [f for f in code_reader.list_files(self.ws)
                      if f.endswith(".py") and not Workspace.is_test_path(f)]
        sources, budget = [], MAX_PREFETCH_CHARS
        for path in dict.fromkeys([s.file for s in suspects] + all_source):
            try:
                numbered = code_reader.read_file(self.ws, path)
            except WorkspaceError:
                continue
            if len(numbered) > budget:
                continue
            budget -= len(numbered)
            sources.append(f"### {path}\n```python\n{numbered}\n```")
        prefetched = ("## Source files (line-numbered, as read_file shows it; likely files first)\n"
                      + "\n\n".join(sources) + "\n\n") if sources else ""

        return (
            f"The test suite is failing. {tests.summary()}\n\n"
            f"## pytest output\n```\n{_truncate(tests.output)}\n```\n\n"
            f"## Likely locations (from a heuristic — a starting point, not proof)\n{suspect_lines}\n\n"
            f"{prefetched}"
            f"## Repository files\n{files}\n\n"
            f"This is fix attempt 1 of {self.max_attempts}. Investigate, fix the root causes in the source code, then call submit_fix."
        )

    def _queue_feedback(self, attempt: int, verify: TestRunResult, reflection: str, reverted: bool) -> None:
        revert_note = (
            f" Your attempt {attempt} changes did not reduce the failures, so they were reverted — "
            f"the files are back to how they were before attempt {attempt}." if reverted else ""
        )
        feedback = (
            f"Verification after attempt {attempt}: {verify.summary()}{revert_note}\n\n"
            f"## pytest output\n```\n{_truncate(verify.output)}\n```\n\n"
            f"## Your reflection\n{reflection}\n\n"
            f"This is fix attempt {attempt + 1} of {self.max_attempts}. Re-read any file you changed before editing it again, "
            f"then call submit_fix."
        )
        results = list(self.pending_tool_results)
        if self.pending_submit:
            results.append(ToolResult(self.pending_submit, f"Fix submitted. {verify.summary()}"))
        self.convo.add_tool_results(results)
        self.convo.add_user_text(feedback)
        self.pending_tool_results, self.pending_submit = [], None

    def _attempt(self, attempt: int) -> dict:
        """Let the LLM investigate and edit until it calls submit_fix. Returns the submit_fix input."""
        for _ in range(MAX_TURNS_PER_ATTEMPT):
            self._check_deadline()
            try:
                turn = self.convo.step()
            except LLMError as e:
                raise AgentError(str(e)) from e

            for text in turn.texts:
                if text.strip():
                    self.trace.plan(text.strip())

            if not turn.tool_calls:
                self.convo.add_user_text(
                    "Your response was cut off. Continue." if turn.stop == "max_tokens"
                    else "Continue investigating with the tools, or call submit_fix if your edits are complete.")
                continue

            results, submitted = [], None
            for call in turn.tool_calls:
                if call.name == "submit_fix":
                    submitted = call
                    continue
                results.append(self._execute_tool(call))

            if submitted:
                self.pending_tool_results = results
                self.pending_submit = submitted
                self.trace.tool_call("submit_fix", "Submitting the fix for verification.", submitted.input)
                return submitted.input
            self.convo.add_tool_results(results)

        self.trace.reflection(
            f"I reached the limit of {MAX_TURNS_PER_ATTEMPT} steps in attempt {attempt} without finishing, "
            "so I'll verify whatever changes I have made so far."
        )
        return {}

    def _check_deadline(self) -> None:
        if self.deadline and time.monotonic() > self.deadline:
            raise RunTimeout("This run took too long and was stopped for safety.")

    def _execute_tool(self, call: ToolCall) -> ToolResult:
        name, inp = call.name, call.input
        t = self.trace
        try:
            if name == "list_files":
                t.tool_call(name, "Listing the files in the repository.", inp)
                files = code_reader.list_files(self.ws)
                t.result(name, f"Found {len(files)} files.", {"files": files})
                output = "\n".join(files)

            elif name == "read_file":
                t.tool_call(name, f"Reading {inp['path']}.", inp)
                output = code_reader.read_file(self.ws, inp["path"])
                t.result(name, f"Read {inp['path']} ({output.count(chr(10)) + 1} lines).",
                         {"path": inp["path"], "content": self.ws.read(inp["path"])})

            elif name == "search_code":
                t.tool_call(name, f"Searching the code for `{inp['pattern']}`.", inp)
                matches = code_reader.search_code(self.ws, inp["pattern"])
                t.result(name, f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} for `{inp['pattern']}`.",
                         {"matches": matches})
                output = "\n".join(matches) or "No matches."

            elif name == "edit_file":
                path = inp["path"]
                t.tool_call(name, f"Editing {path}.", inp)
                before = self.ws.read(path) if not Workspace.is_test_path(path) else None
                info = patcher.edit_file(self.ws, path, inp["old_str"], inp["new_str"])
                self.original_files.setdefault(path, before)
                self.attempt_snapshot.setdefault(path, before)
                span = f"line {info['start_line']}" if info["old_line_count"] == 1 else \
                    f"lines {info['start_line']}–{info['start_line'] + info['old_line_count'] - 1}"
                t.result(name, f"Replaced {info['old_line_count']} line{'s' if info['old_line_count'] != 1 else ''} "
                               f"with {info['new_line_count']} in {path} ({span}).", info)
                output = f"Edit applied to {path} at line {info['start_line']}."

            else:
                raise AgentError(f"Unknown tool {name!r}")

            return ToolResult(call, output)

        except (WorkspaceError, patcher.PatchError, KeyError, UnicodeDecodeError) as e:
            message = str(e).strip("'\"")
            t.result(name, f"The {name} call was rejected: {message}", {"error": message})
            return ToolResult(call, f"Error: {message}", is_error=True)

    # ------------------------------------------------------------- reflect

    def _reflect(self, attempt: int, submitted: dict, before: TestRunResult, after: TestRunResult,
                 reverted: bool) -> dict:
        _, diff_after = self._cumulative_diff()
        outcome = "All tests now pass." if after.all_passed else (
            f"{after.summary()} (before this attempt: {before.summary()})"
            + (" The changes did not reduce the failures and were reverted." if reverted else "")
        )
        prompt = (
            f"Fix attempt {attempt} of {self.max_attempts}.\n\n"
            f"## What I submitted\nDiagnosis: {submitted.get('diagnosis') or '(no diagnosis — attempt did not finish)'}\n"
            f"Self-reported confidence: {submitted.get('confidence', 'n/a')}\n\n"
            f"## Changed files, current content\n```\n{_truncate(diff_after, 8000) or '(no changes)'}\n```\n\n"
            f"## Verification result\n{outcome}\n\n"
            + ("" if after.all_passed else f"## pytest output\n```\n{_truncate(after.output, 6000)}\n```\n\n")
            + ("Attempts remain after this one." if attempt < self.max_attempts else "This was the final attempt.")
        )
        try:
            data = self.llm.structured(REFLECT_SYSTEM, prompt, REFLECTION_SCHEMA)
            data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
            return data
        except (LLMError, KeyError, TypeError, ValueError) as e:
            fallback = ("All tests pass after this attempt." if after.all_passed
                        else "This attempt did not resolve every failure; I'll use the new test output to try a different fix.")
            return {"reflection": f"{fallback} (Reflection step unavailable: {e})",
                    "diagnosis_summary": submitted.get("diagnosis", ""),
                    "confidence": submitted.get("confidence"), "bug_types": []}

    # ----------------------------------------------------------- snapshots

    def _cumulative_diff(self) -> tuple[str, str]:
        """(original, current) contents of every file changed during the run."""
        changed = {p: o for p, o in self.original_files.items() if self.ws.read(p) != o}
        return _concat_files(changed), _concat_files({p: self.ws.read(p) for p in changed})

    def _revert_attempt(self) -> None:
        for path, content in self.attempt_snapshot.items():
            self.ws.write(path, content)
        paths = ", ".join(sorted(self.attempt_snapshot))
        self.trace.tool_call("revert", f"Reverting this attempt's changes to {paths}.",
                             {"paths": sorted(self.attempt_snapshot)})
        self.trace.result("revert", f"Restored {len(self.attempt_snapshot)} file(s) to their state before the attempt.")
