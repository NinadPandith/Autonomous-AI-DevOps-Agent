"""Test Runner tool: run the workspace's pytest suite in a subprocess.

Isolation (process level): the process runs with the workspace
as its working directory, a hard timeout, and an environment scrubbed of
secrets so test code cannot read the LLM API key from its environment. A
Docker sandbox is future work.
"""
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field

from ..workspace import Workspace

DEFAULT_TIMEOUT = 90
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


@dataclass
class TestRunResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    exit_code: int = 0
    timed_out: bool = False
    duration_s: float = 0.0
    failing_tests: list[str] = field(default_factory=list)
    output: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def not_passing(self) -> int:
        return self.failed + self.errors

    @property
    def all_passed(self) -> bool:
        return self.exit_code == 0 and self.not_passing == 0 and not self.timed_out

    def summary(self) -> str:
        if self.timed_out:
            return f"The test suite timed out after {self.duration_s:.0f}s."
        if self.total == 0:
            return "No tests ran — pytest could not collect the test suite."
        if self.all_passed:
            return f"All {self.total} tests passed."
        parts = [f"{self.failed} of {self.total} tests failed"]
        if self.errors:
            parts.append(f"{self.errors} errored")
        return ", ".join(parts) + "."

    def to_dict(self, max_output: int = 20_000) -> dict:
        d = asdict(self)
        d["output"] = self.output[-max_output:]
        d["total"] = self.total
        d["all_passed"] = self.all_passed
        return d


def scrubbed_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in SECRET_MARKERS)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _count(pattern: str, text: str) -> int:
    m = re.search(rf"(\d+) {pattern}\b", text)
    return int(m.group(1)) if m else 0


def run_tests(ws: Workspace, timeout: int = DEFAULT_TIMEOUT) -> TestRunResult:
    cmd = [ws.python, "-m", "pytest", "-q", "--tb=short", "-rfE", "-p", "no:cacheprovider"]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=ws.test_cwd, env=scrubbed_env(), capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return TestRunResult(exit_code=-1, timed_out=True, duration_s=time.monotonic() - start, output=out)

    output = proc.stdout + (("\n" + proc.stderr) if proc.stderr.strip() else "")
    summary_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return TestRunResult(
        passed=_count("passed", summary_line),
        failed=_count("failed", summary_line),
        errors=_count("errors?", summary_line),
        exit_code=proc.returncode,
        duration_s=round(time.monotonic() - start, 2),
        failing_tests=[ws.to_repo_path(t) for t in re.findall(r"^(?:FAILED|ERROR) (\S+)", proc.stdout, re.MULTILINE)],
        output=output,
    )
