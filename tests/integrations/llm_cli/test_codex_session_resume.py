"""Tests for resuming one Codex session across the steps of a tool loop."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from config.constants.coding_agent import CODEX_RESUME_ENV
from integrations.llm_cli.base import CLIProbe
from integrations.llm_cli.codex import CodexAdapter, reset_resumable_sessions
from integrations.llm_cli.runner import CLIBackedLLMClient

_SESSION_A = "01a1941f-3e03-7a32-ad31-819af95b9dda"
_SESSION_B = "01a1941f-3e03-7a32-ad31-819af95b9ddb"


@pytest.fixture(autouse=True)
def _fresh_sessions() -> Iterator[None]:
    reset_resumable_sessions()
    yield
    reset_resumable_sessions()


@pytest.fixture
def which() -> Iterator[MagicMock]:
    with patch(
        "integrations.llm_cli.binary_resolver.shutil.which", return_value="/usr/bin/codex"
    ) as mock:
        yield mock


def _answer(adapter: CodexAdapter, prompt: str, session: str) -> None:
    """One step: build the call, then parse a reply whose stderr names its session."""
    adapter.build(prompt=prompt, model=None, workspace="")
    adapter.parse(stdout="ok", stderr=f"OpenAI Codex\nsession id: {session}\n", returncode=0)


def test_without_the_setting_every_call_is_a_new_ephemeral_session(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CODEX_RESUME_ENV, raising=False)
    adapter = CodexAdapter()

    _answer(adapter, "step one", _SESSION_A)
    inv = adapter.build(prompt="step one\nstep two", model=None, workspace="")

    assert inv.argv[1:3] == ("exec", "--ephemeral")
    assert inv.stdin == "step one\nstep two"


def test_a_tool_loop_resumes_its_session_through_the_client(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    calls: list[dict[str, Any]] = []

    def fake_codex(argv: list[str], **kwargs: Any) -> MagicMock:
        if argv[0] != "/usr/bin/codex":
            return MagicMock(returncode=1, stdout="", stderr="not a git repository")
        calls.append({"argv": argv, "stdin": kwargs.get("input")})
        return MagicMock(returncode=0, stdout="ok", stderr=f"session id: {_SESSION_A}\n")

    probe = CLIProbe(
        installed=True, version="0.165.0", logged_in=True, bin_path="/usr/bin/codex", detail="ok"
    )
    with (
        patch("integrations.llm_cli.runner.subprocess.run", side_effect=fake_codex),
        patch.object(CodexAdapter, "detect", return_value=probe),
        patch("infrastructure.safety.guardrails.evaluator.get_guardrail_evaluator") as guardrails,
    ):
        guardrails.return_value.is_active = False
        client = CLIBackedLLMClient(CodexAdapter(), model="gpt-test")
        first = [{"role": "user", "content": "investigate"}]
        client.invoke(first)
        client.invoke([*first, {"role": "assistant", "content": "call a tool"}])

    assert calls[0]["argv"][1] == "exec" and "--ephemeral" not in calls[0]["argv"], (
        "a session that may be resumed is kept on disk"
    )
    assert calls[1]["argv"][1:4] == ["exec", "resume", _SESSION_A]
    assert 'sandbox_mode="read-only"' in calls[1]["argv"]
    assert len(calls) == 2
    assert "call a tool" in calls[1]["stdin"]
    assert "investigate" not in calls[1]["stdin"], "only the new tail is sent"


def test_interleaved_conversations_each_resume_their_own_session(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    _answer(adapter, "conversation a", _SESSION_A)
    _answer(adapter, "conversation b", _SESSION_B)
    _answer(adapter, "conversation a\nstep two", _SESSION_A)
    resumed_a = adapter.build(
        prompt="conversation a\nstep two\nstep three", model=None, workspace=""
    )
    resumed_b = adapter.build(prompt="conversation b\nstep two", model=None, workspace="")
    changed = adapter.build(prompt="conversation a, new tools\nstep two", model=None, workspace="")

    assert (resumed_a.argv[3], resumed_a.stdin) == (_SESSION_A, "\nstep three"), (
        "the longest answered prefix"
    )
    assert (resumed_b.argv[3], resumed_b.stdin) == (_SESSION_B, "\nstep two")
    assert "resume" not in changed.argv, "a prompt whose prefix changed starts a new session"


def test_a_reply_without_a_session_id_is_never_resumed(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    adapter.build(prompt="step one", model=None, workspace="")
    adapter.parse(stdout="ok", stderr="", returncode=0)
    inv = adapter.build(prompt="step one\nstep two", model=None, workspace="")

    assert "resume" not in inv.argv
