"""Tests for the agent loop, using a scripted stand-in for the LLM provider.

These exercise the controller logic (tool execution, verification, retry,
rollback, status decisions) without network access or an API key.
"""
import itertools

import pytest

from codesentinel.agent import Agent
from codesentinel.config import DEMO_REPO_PATH
from codesentinel.llm import AssistantTurn, ToolCall, Usage
from codesentinel.workspace import Workspace
from eval.bug_manifest import load_bugs, make_variant

BUGS = {b["id"]: b for b in load_bugs()}
_ids = itertools.count(1)


def text(s):
    return s


def tool(name, **inp):
    return ToolCall(f"call_{next(_ids)}", name, inp)


def message(*items):
    texts = [i for i in items if isinstance(i, str)]
    calls = [i for i in items if isinstance(i, ToolCall)]
    return AssistantTurn(texts, calls, "tool_use" if calls else "end")


def reflection(msg="Reflection.", confidence=0.9):
    return {"reflection": msg, "diagnosis_summary": "Summary.", "confidence": confidence, "bug_types": ["off_by_one"]}


class ScriptedConversation:
    def __init__(self, client):
        self.client = client
        self.user_turns = []  # each entry: list of ("text", str) / ("tool_result", ToolResult)
        self.pending = []

    def add_user_text(self, text):
        self.pending.append(("text", text))

    def add_tool_results(self, results):
        self.pending.extend(("tool_result", r) for r in results)

    def step(self):
        self.user_turns.append(self.pending)
        self.pending = []
        return self.client.agent_turns.pop(0)


class ScriptedClient:
    """LLM provider that replays scripted agent turns and reflections."""
    name, model = "scripted", "scripted"

    def __init__(self, agent_turns, reflections):
        self.agent_turns = list(agent_turns)
        self.reflections = list(reflections)
        self.usage = Usage()
        self.convo = None

    def conversation(self, system, tools):
        self.convo = ScriptedConversation(self)
        return self.convo

    def structured(self, system, prompt, schema):
        return dict(self.reflections.pop(0))


class Recorder:
    def __init__(self):
        self.steps, self.attempts, self.updates = [], [], []

    def on_step(self, step):
        self.steps.append(step)

    def on_attempt(self, attempt):
        self.attempts.append(attempt)

    def on_run_update(self, fields):
        self.updates.append(fields)


@pytest.fixture
def b1_workspace(tmp_path):
    source = make_variant(DEMO_REPO_PATH, tmp_path / "src", keep_bug_ids={"B1"})
    return Workspace.create(source, "run_test", base=tmp_path / "ws")


def fix_b1():
    return tool("edit_file", path=BUGS["B1"]["file"], old_str=BUGS["B1"]["buggy"], new_str=BUGS["B1"]["fixed"])


def make_agent(ws, client, recorder):
    return Agent(ws, "run_test", [recorder], max_attempts=3, llm=client)


def test_fixes_bug_on_first_attempt(b1_workspace):
    client = ScriptedClient(
        agent_turns=[
            message(text("I'll read utils.py."), tool("read_file", path="shopcart/utils.py")),
            message(text("The start index is off by one."), fix_b1()),
            message(tool("submit_fix", diagnosis="paginate() treats page as 0-indexed.", confidence=0.95)),
        ],
        reflections=[reflection("The fix worked.")],
    )
    rec = Recorder()
    result = make_agent(b1_workspace, client, rec).run()

    assert result.status == "fixed"
    assert result.attempt_count == 1
    assert result.initial_tests["failed"] == 2 and result.final_tests["failed"] == 0
    assert [a["tests_passed"] for a in rec.attempts] == [True]
    assert "(page - 1) * page_size" in rec.attempts[0]["diff_after"]
    assert "page * page_size" in rec.attempts[0]["diff_before"]
    # Sequence numbers are contiguous and every step has a valid type.
    assert [s["sequence"] for s in rec.steps] == list(range(len(rec.steps)))
    assert {s["step_type"] for s in rec.steps} == {"plan", "tool_call", "result", "reflection"}


def test_retries_after_failed_attempt_and_reverts_regressions(b1_workspace):
    client = ScriptedClient(
        agent_turns=[
            # Attempt 1: a wrong edit that breaks more tests -> must be reverted.
            message(tool("edit_file", path="shopcart/utils.py",
                         old_str='    return f"${amount:,.2f}"\n', new_str='    return f"{amount}"\n')),
            message(tool("submit_fix", diagnosis="Wrong guess.", confidence=0.3)),
            # Attempt 2: the real fix.
            message(fix_b1()),
            message(tool("submit_fix", diagnosis="Off-by-one in paginate().", confidence=0.9)),
        ],
        reflections=[reflection("That made it worse.", 0.2), reflection("Fixed now.", 0.9)],
    )
    rec = Recorder()
    result = make_agent(b1_workspace, client, rec).run()

    assert result.status == "fixed"
    assert result.attempt_count == 2
    assert any(s["tool_name"] == "revert" for s in rec.steps)
    assert '${amount:,.2f}' in b1_workspace.read("shopcart/utils.py")  # wrong edit was rolled back
    # Attempt 2's request carried the submit_fix tool_result plus verification feedback.
    feedback = next(turn for turn in client.convo.user_turns
                    if any(kind == "text" and "Verification after attempt 1" in val for kind, val in turn))
    assert feedback[0][0] == "tool_result" and feedback[0][1].call.name == "submit_fix"


def test_reports_failed_when_attempts_exhausted(b1_workspace):
    no_op = [message(tool("submit_fix", diagnosis="Not sure.", confidence=0.1)) for _ in range(3)]
    client = ScriptedClient(agent_turns=no_op, reflections=[reflection("No luck.", 0.1)] * 3)
    result = make_agent(b1_workspace, client, Recorder()).run()
    assert result.status == "failed"
    assert result.attempt_count == 3


def test_test_files_are_read_only(b1_workspace):
    client = ScriptedClient(
        agent_turns=[
            message(tool("edit_file", path="tests/test_utils.py", old_str="[1, 2, 3, 4]", new_str="[5, 6, 7, 8]")),
            message(fix_b1()),
            message(tool("submit_fix", diagnosis="Off-by-one.", confidence=0.9)),
        ],
        reflections=[reflection()],
    )
    rec = Recorder()
    result = make_agent(b1_workspace, client, rec).run()
    rejected = [s for s in rec.steps if s["step_type"] == "result" and "rejected" in s["content"]]
    assert rejected and "read-only" in rejected[0]["content"]
    assert "[1, 2, 3, 4]" in b1_workspace.read("tests/test_utils.py")
    assert result.status == "fixed"


def test_workspace_blocks_path_escape(b1_workspace):
    from codesentinel.workspace import WorkspaceError
    with pytest.raises(WorkspaceError):
        b1_workspace.resolve("../../outside.txt")
