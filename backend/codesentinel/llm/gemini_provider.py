"""Google Gemini adapter (google-genai SDK). Default provider — free tier.

Free-tier quotas are per model (e.g. 20 requests/day each), so the provider
walks a fallback chain of models: when one model's daily quota runs out or it
is overloaded, the rest of the run continues on the next model.
"""
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from google import genai
from google.genai import errors, types

from .base import AssistantTurn, LLMError, ToolCall, ToolResult, ToolSpec, Usage

MAX_RATE_LIMIT_WAITS = 4
MAX_SERVER_RETRIES = 3
# Placeholder the Gemini API accepts in place of a thought signature produced by a different model.
SKIP_SIGNATURE = b"skip_thought_signature_validator"

# We disable automatic function calling explicitly; the SDK still logs an advisory about it.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
log = logging.getLogger(__name__)


class _SwitchModel(Exception):
    pass


# Models whose daily free-tier quota is used up, shared by every provider in this process so new
# runs skip straight past them. Free-tier daily quotas reset at midnight US Pacific time.
_exhausted_until: dict[str, datetime] = {}


def _next_quota_reset() -> datetime:
    pacific_now = datetime.now(timezone.utc) - timedelta(hours=8)
    next_midnight = (pacific_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return next_midnight + timedelta(hours=8)


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, fallback_models: list[str] | None = None):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set — add it to backend/.env.")
        self.client = genai.Client(api_key=api_key)
        self.models = [model] + [m for m in (fallback_models or []) if m != model]
        self.model_index = 0
        self._skip_exhausted()
        self.usage = Usage()
        self.on_model_switch = None  # optional callback(old, new, reason)

    def _skip_exhausted(self) -> None:
        now = datetime.now(timezone.utc)
        while (self.model_index + 1 < len(self.models)
               and _exhausted_until.get(self.models[self.model_index], now) > now):
            self.model_index += 1

    @property
    def model(self) -> str:
        return self.models[self.model_index]

    def generate(self, contents, config: types.GenerateContentConfig):
        while True:
            try:
                response = self._generate_one_model(contents, config)
                break
            except _SwitchModel as reason:
                if self.model_index + 1 >= len(self.models):
                    raise LLMError(
                        "Every configured Gemini model is out of free-tier quota or unavailable right now. "
                        "Daily quotas reset at midnight Pacific time."
                    ) from None
                old = self.model
                self.model_index += 1
                log.warning("Switching Gemini model %s -> %s (%s)", old, self.model, reason)
                if self.on_model_switch:
                    self.on_model_switch(old, self.model, str(reason))
                if isinstance(contents, list):
                    _neutralize_signatures(contents)

        meta = response.usage_metadata
        if meta:
            self.usage.add(meta.prompt_token_count, (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
                           meta.cached_content_token_count)
        if not response.candidates:
            reason = response.prompt_feedback.block_reason if response.prompt_feedback else "unknown"
            raise LLMError(f"Gemini returned no answer (blocked: {reason}).")
        return response

    def _generate_one_model(self, contents, config):
        waits = server_retries = 0
        while True:
            try:
                return self.client.models.generate_content(model=self.model, contents=contents, config=config)
            except errors.ClientError as e:
                if e.code == 429:
                    if _is_daily_quota(e):
                        _exhausted_until[self.model] = _next_quota_reset()
                        raise _SwitchModel(f"daily quota exhausted for {self.model}") from e
                    if waits < MAX_RATE_LIMIT_WAITS:
                        waits += 1
                        time.sleep(_retry_delay(e, waits))
                        continue
                    raise _SwitchModel(f"rate limited on {self.model}") from e
                if e.code == 404:
                    raise _SwitchModel(f"{self.model} is not available to this key") from e
                if e.code in (401, 403):
                    raise LLMError("Gemini rejected the API key — check GEMINI_API_KEY.") from e
                raise LLMError(f"Gemini API error ({e.code}): {e.message}") from e
            except errors.ServerError as e:
                if server_retries < MAX_SERVER_RETRIES:
                    server_retries += 1
                    time.sleep(3 * server_retries)
                    continue
                raise _SwitchModel(f"{self.model} overloaded ({e.code})") from e
            except errors.APIError as e:
                raise LLMError(f"Gemini API error: {e}") from e
            except Exception as e:  # network-level failures
                raise LLMError(f"Could not reach the Gemini API: {e}") from e

    def conversation(self, system: str, tools: list[ToolSpec]) -> "GeminiConversation":
        return GeminiConversation(self, system, tools)

    def structured(self, system: str, prompt: str, schema: dict) -> dict:
        response = self.generate(prompt, types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
        ))
        try:
            return json.loads(response.text)
        except (TypeError, json.JSONDecodeError) as e:
            raise LLMError("Gemini returned malformed JSON for a structured request.") from e


def _is_daily_quota(err: errors.ClientError) -> bool:
    return "PerDay" in str(err.details) or "per day" in str(err).lower()


def _retry_delay(err: errors.ClientError, attempt: int) -> float:
    match = re.search(r"'retryDelay': '(\d+(?:\.\d+)?)s'|retry in ([\d.]+)s", str(err))
    if match:
        return min(float(match.group(1) or match.group(2)) + 1, 65)
    return min(5 * 2 ** attempt, 60)


def _neutralize_signatures(history: list[types.Content]) -> None:
    """Thought signatures are model-specific; replace them when switching models mid-conversation."""
    for content in history:
        for part in content.parts or []:
            if part.thought_signature:
                part.thought_signature = SKIP_SIGNATURE


class GeminiConversation:
    def __init__(self, provider: GeminiProvider, system: str, tools: list[ToolSpec]):
        self.provider = provider
        self.history: list[types.Content] = []
        self.pending: list[types.Part] = []
        self.config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
                for t in tools
            ])] if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def add_user_text(self, text: str) -> None:
        self.pending.append(types.Part(text=text))

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            payload = {"error": r.content} if r.is_error else {"output": r.content}
            self.pending.append(types.Part(function_response=types.FunctionResponse(
                id=None if r.call.id.startswith("local_") else r.call.id, name=r.call.name, response=payload,
            )))

    def step(self) -> AssistantTurn:
        if self.pending:
            self.history.append(types.Content(role="user", parts=self.pending))
            self.pending = []
        response = self.provider.generate(self.history, self.config)
        candidate = response.candidates[0]
        content = candidate.content or types.Content(role="model", parts=[])
        self.history.append(content)  # keep thought signatures intact

        turn = AssistantTurn()
        text_run = ""  # Gemini can split one sentence across several text parts
        for part in content.parts or []:
            if part.function_call:
                if text_run.strip():
                    turn.texts.append(text_run)
                text_run = ""
                fc = part.function_call
                turn.tool_calls.append(ToolCall(id=fc.id or f"local_{uuid.uuid4().hex[:8]}", name=fc.name,
                                                input=dict(fc.args or {})))
            elif part.text and not part.thought:
                text_run += part.text
        if text_run.strip():
            turn.texts.append(text_run)

        if turn.tool_calls:
            turn.stop = "tool_use"
        elif candidate.finish_reason == types.FinishReason.MAX_TOKENS:
            turn.stop = "max_tokens"
        elif candidate.finish_reason not in (types.FinishReason.STOP, None):
            raise LLMError(f"Gemini stopped unexpectedly ({candidate.finish_reason}).")
        return turn
