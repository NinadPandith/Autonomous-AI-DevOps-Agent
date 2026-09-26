"""LLM providers. Pick one with LLM_PROVIDER in backend/.env (gemini | claude)."""
import os

from .. import config
from .base import AssistantTurn, LLMError, LLMProvider, ToolCall, ToolResult, ToolSpec, Usage

__all__ = ["AssistantTurn", "LLMError", "LLMProvider", "ToolCall", "ToolResult", "ToolSpec", "Usage", "get_provider"]


def get_provider(name: str | None = None) -> LLMProvider:
    name = (name or config.LLM_PROVIDER).lower()
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(os.getenv("GEMINI_API_KEY", "").strip(), config.GEMINI_MODEL,
                              config.GEMINI_FALLBACK_MODELS)
    if name == "claude":
        try:
            from .anthropic_provider import ClaudeProvider
        except ImportError as e:
            raise LLMError("LLM_PROVIDER=claude needs the Anthropic SDK: pip install -r requirements-claude.txt") from e
        return ClaudeProvider(os.getenv("ANTHROPIC_API_KEY", "").strip(), config.CLAUDE_MODEL, config.CLAUDE_EFFORT)
    raise LLMError(f"Unknown LLM_PROVIDER {name!r} — use 'gemini' or 'claude'.")


def describe_provider() -> str:
    if config.LLM_PROVIDER.lower() == "claude":
        return f"claude / {config.CLAUDE_MODEL} (effort {config.CLAUDE_EFFORT})"
    return f"gemini / {config.GEMINI_MODEL} (fallbacks: {', '.join(config.GEMINI_FALLBACK_MODELS) or 'none'})"
