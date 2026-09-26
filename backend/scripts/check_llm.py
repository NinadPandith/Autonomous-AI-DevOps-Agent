r"""Phase 0 check: one successful LLM call, to confirm the API key works.

Usage (from backend/):  .venv\Scripts\python scripts\check_llm.py
Uses LLM_PROVIDER from backend/.env (gemini or claude).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codesentinel.llm import LLMError, describe_provider, get_provider  # noqa: E402


def main() -> int:
    print(f"Provider: {describe_provider()}")
    try:
        llm = get_provider()
        convo = llm.conversation("You are a terse assistant.", [])
        convo.add_user_text("Reply with exactly: CodeSentinel is online.")
        turn = convo.step()
    except LLMError as e:
        print(f"FAILED: {e}")
        return 1
    print(f"Reply:    {' '.join(turn.texts).strip()}")
    print(f"Tokens:   {llm.usage.input_tokens} in / {llm.usage.output_tokens} out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
