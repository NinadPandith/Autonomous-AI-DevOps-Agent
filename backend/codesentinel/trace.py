"""The reasoning trace — one entry per plan / tool_call / result / reflection.

Every step has exactly the shape of a `reasoning_steps` row (Backend Schema
§1.3), so the CLI printer, the database and the WebSocket all consume the
same dicts. Observers receive steps as they happen.
"""
from typing import Any, Protocol

from .db import now_iso

STEP_TYPES = ("plan", "tool_call", "result", "reflection")


class AgentObserver(Protocol):
    def on_step(self, step: dict) -> None: ...
    def on_attempt(self, attempt: dict) -> None: ...
    def on_run_update(self, fields: dict) -> None: ...


class Trace:
    def __init__(self, run_id: str, observers: list[AgentObserver]):
        self.run_id = run_id
        self.observers = observers
        self.sequence = 0
        self.steps: list[dict] = []

    def emit(self, step_type: str, content: str, tool_name: str | None = None,
             tool_input: Any = None, tool_output: Any = None) -> dict:
        if step_type not in STEP_TYPES:
            raise ValueError(f"Unknown step_type {step_type!r}")
        step = {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "step_type": step_type,
            "content": content,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "created_at": now_iso(),
        }
        self.sequence += 1
        self.steps.append(step)
        for obs in self.observers:
            obs.on_step(step)
        return step

    def plan(self, content: str) -> dict:
        return self.emit("plan", content)

    def tool_call(self, tool_name: str, content: str, tool_input: Any = None) -> dict:
        return self.emit("tool_call", content, tool_name=tool_name, tool_input=tool_input)

    def result(self, tool_name: str, content: str, tool_output: Any = None) -> dict:
        return self.emit("result", content, tool_name=tool_name, tool_output=tool_output)

    def reflection(self, content: str) -> dict:
        return self.emit("reflection", content)

    def attempt(self, attempt: dict) -> None:
        for obs in self.observers:
            obs.on_attempt(attempt)

    def run_update(self, **fields) -> None:
        for obs in self.observers:
            obs.on_run_update(fields)
