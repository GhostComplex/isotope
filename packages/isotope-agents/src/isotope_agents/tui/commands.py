"""Slash command handling for the isotope-agents TUI.

This module extracts command parsing and state management from the TUI class
into standalone, I/O-independent components that are easy to test without
prompt-toolkit or Rich.

Main components:
- CommandResult: Return value for every command handler.
- TUIState: Mutable state shared between the TUI shell and CommandHandler.
- CommandHandler: Dispatch slash commands and return structured results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """Result of executing a TUI command.

    Attributes:
        should_quit: Whether the TUI should exit after this command.
        message: Human-readable status text (may be empty).
        style: Semantic style hint for the renderer
               ("info", "error", "success", "warn", "tool", "model", "dim").
        action: Optional follow-up action the TUI should perform, e.g.
                ``"rebuild_agent"``, ``"rebuild_agent_clear"``, ``"compact"``.
    """

    should_quit: bool = False
    message: str = ""
    style: str = "info"
    action: str | None = None


@dataclass
class TUIState:
    """Mutable TUI state, extracted from the ``TUI`` class.

    Attributes:
        model: The currently selected LLM model identifier.
        preset: The active agent preset (e.g. ``CODING``).
        tools_enabled: Whether tool calling is turned on.
        debug: Whether debug mode is active.
        custom_system_prompt: User-supplied system prompt override.
        total_input_tokens: Running total of input tokens consumed.
        total_output_tokens: Running total of output tokens consumed.
    """

    model: str = ""
    preset: Any = None
    tools_enabled: bool = True
    debug: bool = False
    custom_system_prompt: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0


# ---------------------------------------------------------------------------
# Known commands (for help text)
# ---------------------------------------------------------------------------

BETWEEN_MESSAGE_COMMANDS = (
    "/tools          Toggle tools",
    "/model <name>   Switch model",
    "/system <text>  Change system prompt",
    "/clear          Clear conversation",
    "/compact        Compact conversation history",
    "/history        Show usage stats",
    "/sessions       List sessions",
    "/debug          Toggle debug mode",
    "/help           Show available commands",
    "/quit           Exit",
)

DURING_STREAMING_COMMANDS = (
    "Any text       Steering — cancels stream, queues your message",
    "/follow <msg>  Queue follow-up for after completion",
    "/abort         Abort current response",
)


# ---------------------------------------------------------------------------
# CommandHandler
# ---------------------------------------------------------------------------


class CommandHandler:
    """Handles slash commands independent of terminal I/O.

    Every public ``handle_*`` method returns a :class:`CommandResult`; the
    TUI is responsible for rendering the message and executing any
    ``action``.
    """

    def __init__(self, state: TUIState) -> None:
        self.state = state

    # -- public entry point --------------------------------------------------

    async def handle(self, line: str) -> CommandResult:
        """Parse and execute a slash command.

        Parameters:
            line: The raw input line (must start with ``/``).

        Returns:
            A :class:`CommandResult` describing what happened.
        """
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        dispatch = {
            "/quit": self._handle_quit,
            "/tools": self._handle_tools,
            "/model": self._handle_model,
            "/system": self._handle_system,
            "/clear": self._handle_clear,
            "/compact": self._handle_compact,
            "/history": self._handle_history,
            "/sessions": self._handle_sessions,
            "/debug": self._handle_debug,
            "/help": self._handle_help,
        }

        handler = dispatch.get(cmd)
        if handler is not None:
            return await handler(arg)

        return self._handle_unknown(cmd)

    # -- individual handlers -------------------------------------------------

    async def _handle_quit(self, arg: str) -> CommandResult:
        return CommandResult(should_quit=True, message="Bye!", style="info")

    async def _handle_tools(self, arg: str) -> CommandResult:
        self.state.tools_enabled = not self.state.tools_enabled
        if self.state.tools_enabled:
            # The TUI layer can enrich this with actual tool names.
            names = ""
            if self.state.preset is not None:
                try:
                    names = ", ".join(t.name for t in self.state.preset.tools)
                except (AttributeError, TypeError):
                    pass
            message = f"Tools enabled: {names}" if names else "Tools enabled"
            return CommandResult(message=message, style="tool", action="rebuild_agent")
        return CommandResult(
            message="Tools disabled", style="tool", action="rebuild_agent"
        )

    async def _handle_model(self, arg: str) -> CommandResult:
        if arg:
            self.state.model = arg
            return CommandResult(
                message=f"Model switched to: {self.state.model}",
                style="model",
                action="rebuild_agent",
            )
        return CommandResult(message="Usage: /model <name>", style="warn")

    async def _handle_system(self, arg: str) -> CommandResult:
        if arg == "clear":
            self.state.custom_system_prompt = None
            return CommandResult(
                message="System prompt cleared.",
                style="info",
                action="rebuild_agent",
            )
        if arg:
            self.state.custom_system_prompt = arg
            return CommandResult(
                message="System prompt updated.",
                style="info",
                action="rebuild_agent",
            )
        return CommandResult(message="Usage: /system <prompt>", style="warn")

    async def _handle_clear(self, arg: str) -> CommandResult:
        self.state.total_input_tokens = 0
        self.state.total_output_tokens = 0
        return CommandResult(
            message="Conversation cleared.",
            style="info",
            action="rebuild_agent_clear",
        )

    async def _handle_compact(self, arg: str) -> CommandResult:
        # The actual compaction is async and requires the agent instance,
        # so the TUI must execute this action.
        return CommandResult(action="compact")

    async def _handle_history(self, arg: str) -> CommandResult:
        lines: list[str] = []
        lines.append(
            f"Total tokens: in={self.state.total_input_tokens}, "
            f"out={self.state.total_output_tokens}"
        )
        return CommandResult(message="\n".join(lines), style="info", action="history")

    async def _handle_sessions(self, arg: str) -> CommandResult:
        # Listing sessions requires the SessionStore, so the TUI must execute.
        return CommandResult(action="sessions")

    async def _handle_debug(self, arg: str) -> CommandResult:
        self.state.debug = not self.state.debug
        return CommandResult(
            message=f"Debug mode: {'on' if self.state.debug else 'off'}",
            style="info",
        )

    async def _handle_help(self, arg: str) -> CommandResult:
        lines: list[str] = []
        lines.append("Commands (between messages):")
        for cmd_line in BETWEEN_MESSAGE_COMMANDS:
            lines.append(f"  {cmd_line}")
        lines.append("")
        lines.append("Commands (during streaming):")
        for cmd_line in DURING_STREAMING_COMMANDS:
            lines.append(f"  {cmd_line}")
        return CommandResult(message="\n".join(lines), style="info")

    @staticmethod
    def _handle_unknown(cmd: str) -> CommandResult:
        known = "/tools /model /system /clear /compact /history /sessions /debug /help /quit"
        return CommandResult(
            message=f"Unknown command: {cmd}\nCommands: {known}",
            style="warn",
        )
