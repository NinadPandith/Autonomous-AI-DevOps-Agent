"""Claude adapter (Anthropic SDK). Used when LLM_PROVIDER=claude."""
import json

import anthropic

from .base import AssistantTurn, LLMError, ToolCall, ToolResult, ToolSpec, Usage


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, model: str, effort: str = "high"):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set — add it to backend/.env.")
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self.model = model
        self.effort = effort
        self.usage = Usage()

    def create(self, **kwargs) -> anthropic.types.Message:
        try:
            response = self.client.messages.create(model=self.model, **kwargs)
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude API authentication failed — check ANTHROPIC_API_KEY.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Claude API.") from e
        u = response.usage
        self.usage.add(u.input_tokens, u.output_tokens, u.cache_read_input_tokens)
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to continue this request.")
        return response

    def conversation(self, system: str, tools: list[ToolSpec]) -> "ClaudeConversation":
        return ClaudeConversation(self, system, tools)

    def structured(self, system: str, prompt: str, schema: dict) -> dict:
        response = self.create(
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError("Claude returned malformed JSON for a structured request.") from e


class ClaudeConversation:
    def __init__(self, provider: ClaudeProvider, system: str, tools: list[ToolSpec]):
        self.provider = provider
        self.system = system
        self.tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters, "strict": True}
            for t in tools
        ]
        self.messages: list[dict] = []
        self.pending: list[dict] = []

    def add_user_text(self, text: str) -> None:
        self.pending.append({"type": "text", "text": text})

    def add_tool_results(self, results: list[ToolResult]) -> None:
        # tool_result blocks must lead the user turn, ahead of any text.
        blocks = [{"type": "tool_result", "tool_use_id": r.call.id, "content": r.content,
                   **({"is_error": True} if r.is_error else {})} for r in results]
        texts = [b for b in self.pending if b["type"] == "text"]
        self.pending = [b for b in self.pending if b["type"] != "text"] + blocks + texts

    def step(self) -> AssistantTurn:
        if self.pending:
            self.messages.append({"role": "user", "content": self.pending})
            self.pending = []
        response = self.provider.create(
            max_tokens=16000,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            output_config={"effort": self.provider.effort},
            cache_control={"type": "ephemeral"},
        )
        self.messages.append({"role": "assistant", "content": response.content})

        turn = AssistantTurn()
        for block in response.content:
            if block.type == "text" and block.text.strip():
                turn.texts.append(block.text)
            elif block.type == "tool_use":
                turn.tool_calls.append(ToolCall(block.id, block.name, dict(block.input)))
        if turn.tool_calls:
            turn.stop = "tool_use"
        elif response.stop_reason == "max_tokens":
            turn.stop = "max_tokens"
        return turn
