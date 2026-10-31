"""Tests for resuming one Codex session across the steps of a tool loop."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from integrations.llm_cli.codex import CODEX_RESUME_ENV, CodexAdapter, reset_resumable_sessions

_SESSION = "01a1941f-3e03-7a32-ad31-819af95b9ddd"
_OTHER = "01a1941f-0000-7a32-ad31-819af95b9ddd"


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
    """One step: build the call, then parse a reply whose stderr names the session."""
    adapter.build(prompt=prompt, model=None, workspace="")
    adapter.parse(stdout="ok", stderr=f"OpenAI Codex\nsession id: {session}\n", returncode=0)


def test_without_the_setting_every_call_is_a_new_ephemeral_session(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CODEX_RESUME_ENV, raising=False)
    adapter = CodexAdapter()

    _answer(adapter, "step one", _SESSION)
    inv = adapter.build(prompt="step one\nstep two", model=None, workspace="")

    assert inv.argv[1:3] == ("exec", "--ephemeral")
    assert inv.stdin == "step one\nstep two"


def test_a_prompt_that_extends_an_answered_one_resumes_its_session(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    first = adapter.build(prompt="step one", model="gpt-test", workspace="")
    adapter.parse(stdout="ok", stderr=f"session id: {_SESSION}\n", returncode=0)
    second = adapter.build(prompt="step one\nstep two", model="gpt-test", workspace="")

    assert "--ephemeral" not in first.argv, "a session that may be resumed is kept on disk"
    assert second.argv[1:4] == ("exec", "resume", _SESSION)
    assert 'sandbox_mode="read-only"' in second.argv
    assert "-m" in second.argv and "gpt-test" in second.argv
    assert second.argv[-1] == "-"
    assert second.stdin == "\nstep two", "only the new tail is sent"


def test_a_prompt_that_changes_its_prefix_starts_a_new_session(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    _answer(adapter, "tools: a\nstep one", _SESSION)
    inv = adapter.build(prompt="tools: a, b\nstep one\nstep two", model=None, workspace="")

    assert "resume" not in inv.argv
    assert inv.stdin == "tools: a, b\nstep one\nstep two"


def test_the_longest_answered_prefix_wins(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    _answer(adapter, "base", _OTHER)
    _answer(adapter, "base\nstep one", _SESSION)
    inv = adapter.build(prompt="base\nstep one\nstep two", model=None, workspace="")

    assert inv.argv[3] == _SESSION
    assert inv.stdin == "\nstep two"


def test_a_reply_without_a_session_id_is_not_remembered(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    adapter.build(prompt="step one", model=None, workspace="")
    adapter.parse(stdout="ok", stderr="", returncode=0)
    inv = adapter.build(prompt="step one\nstep two", model=None, workspace="")

    assert "resume" not in inv.argv


def test_an_identical_prompt_is_not_resumed(
    which: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CODEX_RESUME_ENV, "1")
    adapter = CodexAdapter()

    _answer(adapter, "step one", _SESSION)
    inv = adapter.build(prompt="step one", model=None, workspace="")

    assert "resume" not in inv.argv, "resuming with an empty tail would send nothing to answer"
