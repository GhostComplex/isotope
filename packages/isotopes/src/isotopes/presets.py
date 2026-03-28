"""Preset configurations for isotopes.

Presets define which tools and system prompt to use for different
agent roles: coding, assistant, minimal, or custom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isotopes_core.tools import Tool

from isotopes.tools.bash import bash
from isotopes.tools.edit import edit_file
from isotopes.tools.glob import glob_tool
from isotopes.tools.grep import grep
from isotopes.tools.read import read_file
from isotopes.tools.web_fetch import web_fetch
from isotopes.tools.web_search import web_search
from isotopes.tools.write import write_file


# =============================================================================
# System prompts
# =============================================================================

_CODING_PROMPT = """\
You are isotope, an expert software engineer assistant. You help users with \
coding tasks including writing, reading, editing, and debugging code.

Your workspace directory is {cwd}.

Available tools:
- read_file: Read file contents.
- write_file: Create new files or fully rewrite existing ones.
- edit_file: Make surgical edits to existing files.
- bash: Run shell commands.
- grep: Search file contents with regex patterns.
- glob_tool: Discover files by glob patterns.
- web_search: Search the web for documentation or solutions.
- web_fetch: Fetch and read content from a specific URL.

Guidelines:
- Read files before editing to understand context.
- When you read or modify files, note the paths — they are tracked for \
context management.
- Use edit_file for surgical changes; use write_file only for new files or \
full rewrites.
- Use grep to search codebases efficiently.
- Use glob to discover file structure.
- Use web_search to find documentation or solutions. Use web_fetch to read \
specific pages.
- If an approach is not working after 2 attempts, try a different strategy \
or ask for clarification.
- Keep responses concise and actionable.
"""

_ASSISTANT_PROMPT = """\
You are isotope, a helpful assistant. You can run shell commands and \
search the web to help answer questions.

Your workspace directory is {cwd}.

Guidelines:
- Be concise and direct. Prefer short answers unless detail is requested.
- Use tools when they'd help answer the question.
- Use web_search to find documentation or solutions. Use web_fetch to read \
specific pages.
- Cite sources when relevant.
"""

_MINIMAL_PROMPT = """\
You are isotope, a minimal assistant.

Your workspace directory is {cwd}.
"""


# =============================================================================
# Preset dataclass
# =============================================================================


@dataclass
class Preset:
    """Agent preset configuration.

    Attributes:
        name: Preset name (coding, assistant, minimal, custom).
        system_prompt: System prompt template (supports {cwd} placeholder).
        tools: List of Tool instances for this preset.
        description: Human-readable description.
    """

    name: str
    system_prompt: str
    tools: list[Tool] = field(default_factory=list)
    description: str = ""

    def format_system_prompt(self, **kwargs: Any) -> str:
        """Format the system prompt with runtime values."""
        return self.system_prompt.format(**kwargs)


# =============================================================================
# Tool sets
# =============================================================================


def _coding_tools() -> list[Tool]:
    """All tools for the coding preset."""
    return [
        read_file,
        write_file,
        edit_file,
        bash,
        grep,
        glob_tool,
        web_search,
        web_fetch,
    ]


def _assistant_tools() -> list[Tool]:
    """Tools for the assistant preset (no file write/edit)."""
    return [read_file, bash, grep, glob_tool, web_search, web_fetch]


def _minimal_tools() -> list[Tool]:
    """Minimal tools."""
    return [bash]


# =============================================================================
# Built-in presets
# =============================================================================


CODING = Preset(
    name="coding",
    system_prompt=_CODING_PROMPT,
    tools=_coding_tools(),
    description="Full coding agent with file read/write/edit, bash, grep, glob, and web tools.",
)

ASSISTANT = Preset(
    name="assistant",
    system_prompt=_ASSISTANT_PROMPT,
    tools=_assistant_tools(),
    description="General assistant with read-only file access, bash, and web tools.",
)

MINIMAL = Preset(
    name="minimal",
    system_prompt=_MINIMAL_PROMPT,
    tools=_minimal_tools(),
    description="Minimal agent with bash only.",
)

# Registry for lookup by name
PRESETS: dict[str, Preset] = {
    "coding": CODING,
    "assistant": ASSISTANT,
    "minimal": MINIMAL,
}


def get_preset(name: str) -> Preset:
    """Get a preset by name.

    Args:
        name: Preset name.

    Returns:
        The preset configuration.

    Raises:
        KeyError: If preset name is not found.
    """
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    return PRESETS[name]
