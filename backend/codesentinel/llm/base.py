"""Provider-neutral interface between the agent loop and an LLM.

The agent loop only ever sees these types, so the reasoning loop is the same
whichever model backs it. Each provider adapter translates to its own API and
keeps the native conversation history (so provider-specific data such as
thinking blocks or thought signatures round-trips untouched).
"""
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(Exception):
    """The provider failed in a way the agent cannot recover from."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema for the tool input


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    call: ToolCall
    content: str
    is_error: bool = False


@dataclass
class AssistantTurn:
    texts: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop: str = "end"  # end | tool_use | max_tokens


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    api_calls: int = 0

    def add(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> None:
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0
        self.cached_tokens += cached_tokens or 0
        self.api_calls += 1

    def to_dict(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cached_tokens": self.cached_tokens, "api_calls": self.api_calls}


class Conversation(Protocol):
    """A multi-turn tool-using conversation.

    add_tool_results / add_user_text buffer content for the next user turn;
    step() sends it and returns the model's reply.
    """

    def add_user_text(self, text: str) -> None: ...
    def add_tool_results(self, results: list[ToolResult]) -> None: ...
    def step(self) -> AssistantTurn: ...


class LLMProvider(Protocol):
    name: str
    model: str
    usage: Usage

    def conversation(self, system: str, tools: list[ToolSpec]) -> Conversation: ...
    def structured(self, system: str, prompt: str, schema: dict) -> dict[str, Any]: ...
