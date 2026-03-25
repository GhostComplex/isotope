"""Preset definitions for isotope-agents.

Presets define the agent's role: system prompt, enabled tools, and behavior.
Users can choose a built-in preset or create their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Preset:
    """A preset configuration that defines an agent's role.

    Attributes:
        name: Unique identifier for the preset.
        system_prompt: System prompt that defines the agent's behavior.
        tools: List of canonical tool names to enable by default.
        description: Human-readable description of what this preset does.
    """

    name: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    description: str = ""


CODING_PRESET = Preset(
    name="coding",
    system_prompt=(
        "You are an expert software engineer and coding assistant. "
        "You help users write, debug, refactor, and understand code.\n\n"
        "Guidelines:\n"
        "- Read files before editing them to understand the existing code.\n"
        "- Use grep and glob to search the codebase before making assumptions.\n"
        "- Make minimal, targeted changes — don't rewrite entire files unless asked.\n"
        "- Explain your reasoning when making non-obvious decisions.\n"
        "- Use the bash tool for running tests, builds, and other commands.\n"
        "- When editing files, use exact text matching with the edit tool.\n"
        "- Prefer editing existing files over creating new ones unless explicitly required.\n"
        "- Always use type hints in Python code.\n"
        "- Write clean, idiomatic code that follows the project's existing conventions."
    ),
    tools=["bash", "read", "write", "edit", "grep", "glob"],
    description="Software development with file and shell tools",
)

ASSISTANT_PRESET = Preset(
    name="assistant",
    system_prompt=(
        "You are a helpful personal assistant. "
        "You help users with a wide range of tasks including research, "
        "writing, analysis, file management, and running commands.\n\n"
        "Guidelines:\n"
        "- Be concise and direct in your responses.\n"
        "- Ask clarifying questions when the task is ambiguous.\n"
        "- Use tools proactively when they would help answer the question.\n"
        "- Read files when asked about their contents.\n"
        "- Use bash for system tasks, file operations, and information gathering."
    ),
    tools=["bash", "read", "write"],
    description="General tasks with basic file and shell tools",
)

MINIMAL_PRESET = Preset(
    name="minimal",
    system_prompt="",
    tools=[],
    description="Bare LLM — add your own tools",
)

PRESETS: dict[str, Preset] = {
    "coding": CODING_PRESET,
    "assistant": ASSISTANT_PRESET,
    "minimal": MINIMAL_PRESET,
}
