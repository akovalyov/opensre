"""Coding-agent environment names shared by its config and the deployment image."""

from __future__ import annotations

#: Which sandbox the coding agent runs its commands in. ``agent`` (the default)
#: keeps the agent's own sandbox; ``host`` hands the agent the whole process
#: environment because the host is already an isolated container that cannot
#: create the namespaces the agent's sandbox needs (Fargate).
CODING_AGENT_SANDBOX_ENV = "CODING_AGENT_SANDBOX"
CODING_AGENT_SANDBOX_AGENT = "agent"
CODING_AGENT_SANDBOX_HOST = "host"

#: Codex reads its config, plugins, MCP servers and skills from this directory
#: (default ``~/.codex``). A hosted-route run points it at a fresh minimal home.
CODEX_HOME_ENV = "CODEX_HOME"
#: Name prefix of the per-run temporary ``CODEX_HOME`` a hosted-route run gets.
CODEX_ISOLATED_HOME_PREFIX = "opensre-codex-home-"
#: ``1`` resumes the Codex session that already answered a prompt's prefix instead of
#: starting a new one per call, so a tool loop keeps its history in the prompt cache.
CODEX_RESUME_ENV = "OPENSRE_CODEX_RESUME"

__all__ = [
    "CODEX_HOME_ENV",
    "CODEX_ISOLATED_HOME_PREFIX",
    "CODEX_RESUME_ENV",
    "CODING_AGENT_SANDBOX_AGENT",
    "CODING_AGENT_SANDBOX_ENV",
    "CODING_AGENT_SANDBOX_HOST",
]
