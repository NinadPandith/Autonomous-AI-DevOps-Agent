"""Prompts and tool definitions for the LLM side of the agent loop (provider-neutral)."""
from .llm.base import ToolSpec

SYSTEM_PROMPT = """You are CodeSentinel, an autonomous debugging agent. You are working inside an isolated copy of a Python repository whose test suite is failing. Your job is to find the root cause of each failure and fix the application source code so the tests pass.

How you work:
- Investigate with list_files, read_file and search_code, then change code with edit_file.
- Before each tool call, write one short first-person sentence saying what you are about to do and why. These sentences are shown live to a developer watching you work, e.g. "I'll read shopcart/pricing.py to see how coupon codes are normalized."
- Work efficiently: every turn uses one API request from a limited quota. Call independent tools together in one turn (read several files at once, make several edits at once). The source files are already included in the first message — don't re-read them unless you have edited them. Read test files only when the pytest output is not enough.
- When your edits for this attempt are complete, call submit_fix. You cannot run the tests yourself; after submit_fix the harness runs the full suite and reports back to you.

Rules:
- Never modify test files. The tests describe the intended behavior; fix the code under test.
- Fix root causes, not symptoms. Do not special-case the values used in tests.
- Keep changes minimal and in the existing style. Read docstrings and comments: they describe intended behavior.
- One failing test can have more than one cause, and several failing tests can share one cause. Account for every failing test before you submit.
- Be honest about uncertainty. Say "likely" when you are not sure."""


_TOOL_DEFS = [
    {
        "name": "list_files",
        "description": "List every text file in the repository, as paths relative to the repository root.",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "read_file",
        "description": "Read a file from the repository. The content is returned with 1-based line numbers prefixed to each line; the numbers are not part of the file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to the repository root, e.g. shopcart/cart.py"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_code",
        "description": "Search every file in the repository for a regular expression. Returns up to 50 matching lines as path:line: text.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "description": "Python regular expression, e.g. def find_coupon"}},
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace one exact occurrence of old_str with new_str in a source file. old_str must match the file "
            "character-for-character (without the line-number prefix from read_file), including indentation, and must "
            "occur exactly once; include surrounding lines if needed to make it unique. Test files cannot be edited."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repository root"},
                "old_str": {"type": "string", "description": "Exact existing text to replace"},
                "new_str": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_str", "new_str"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_fix",
        "description": "Finish this fix attempt. The harness will then run the full test suite and report the result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "diagnosis": {
                    "type": "string",
                    "description": "Plain-language root cause of each bug you fixed, one sentence per bug, e.g. 'find_coupon() calls .strip() on None when no coupon code is given.'",
                },
                "confidence": {
                    "type": "number",
                    "description": "0.0-1.0: how confident you are that these edits fix the root causes of all failing tests.",
                },
            },
            "required": ["diagnosis", "confidence"],
            "additionalProperties": False,
        },
    },
]


TOOLS = [ToolSpec(t["name"], t["description"], t["input_schema"]) for t in _TOOL_DEFS]


REFLECT_SYSTEM = """You are the reflection step of CodeSentinel, an autonomous debugging agent. After each fix attempt the harness runs the test suite; you evaluate the outcome. Write as the agent, in the first person, like a sharp engineer narrating their own reasoning. Be precise and brief. Never state a guess as fact — say "likely" when unsure."""

BUG_TYPES = [
    "off_by_one", "null_check", "wrong_operator", "cross_function_logic",
    "api_response_handling", "ordering", "shared_state", "state_rollback", "other",
]

REFLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "reflection": {
            "type": "string",
            "description": (
                "1-3 sentences, first person. Evaluate the attempt: did it work, and why or why not? "
                "If tests still fail, name the likely cause and what you will do differently next. "
                "State your confidence in plain words. Do not just repeat the test counts."
            ),
        },
        "diagnosis_summary": {
            "type": "string",
            "description": "One plain-language sentence summarizing the root cause(s) found so far, for a summary card. Hedge with 'likely' if unconfirmed.",
        },
        "confidence": {
            "type": "number",
            "description": "0.0-1.0: confidence that the code as it stands now correctly fixes the root causes (not just that tests pass).",
        },
        "bug_types": {"type": "array", "items": {"type": "string", "enum": BUG_TYPES}},
    },
    "required": ["reflection", "diagnosis_summary", "confidence", "bug_types"],
    "additionalProperties": False,
}
