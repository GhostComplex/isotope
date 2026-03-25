"""Slash command handlers for the isotope-agents TUI.

Handles all slash commands available between messages and during streaming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from isotope_agents.tui.output import tui_print

if TYPE_CHECKING:
    from isotope_agents.tui.app import TUIApp

BETWEEN_MESSAGE_COMMANDS = (
    "/tools          Toggle tools",
    "/model <name>   Switch model",
    "/system <text>  Change system prompt",
    "/clear          Clear conversation",
    "/history        Show usage stats",
    "/debug          Toggle debug mode",
    "/help           Show available commands",
    "/quit           Exit",
)

DURING_STREAMING_COMMANDS = (
    "Any text       Steering — cancels stream, queues your message",
    "/follow <msg>  Queue follow-up for after completion",
    "/abort         Abort current response",
)


def print_help() -> None:
    """Print interactive help with all available commands."""
    print_command_group("Commands (between messages):", BETWEEN_MESSAGE_COMMANDS)
    tui_print("\nCommands (during streaming):", style="info")
    for command in DURING_STREAMING_COMMANDS:
        tui_print(f"  {command}", style="dim")


def print_command_group(title: str, commands: tuple[str, ...]) -> None:
    """Print a formatted command list."""
    tui_print(title, style="info")
    for command in commands:
        tui_print(f"  {command}", style="dim")


def print_known_commands() -> None:
    """Print the short known-command summary."""
    tui_print(
        "Commands: /tools /model /system /clear /history /debug /help /quit",
        style="dim",
    )


async def handle_command(app: TUIApp, line: str) -> bool:
    """Handle a slash command.

    Args:
        app: The TUI application instance.
        line: The full command line (including the leading /).

    Returns:
        True if the TUI should quit, False otherwise.
    """
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/quit":
        tui_print("Bye!", style="info")
        return True

    if cmd == "/tools":
        app.tools_enabled = not app.tools_enabled
        if app.tools_enabled:
            names = ", ".join(t.name for t in app.isotope_agent.tools)
            tui_print(f"Tools enabled: {names}", style="tool")
        else:
            tui_print("Tools disabled", style="tool")
        app.isotope_agent.set_tools_enabled(app.tools_enabled)
        return False

    if cmd == "/model":
        if arg:
            app.isotope_agent.set_model(arg)
            tui_print(f"Model switched to: {arg}", style="model")
        else:
            tui_print("Usage: /model <name>", style="warn")
        return False

    if cmd == "/system":
        if arg:
            app.isotope_agent.set_system_prompt(arg)
            tui_print("System prompt updated.", style="info")
        else:
            tui_print("Usage: /system <prompt>", style="warn")
        return False

    if cmd == "/clear":
        app.total_input_tokens = 0
        app.total_output_tokens = 0
        app.isotope_agent.agent.clear_messages()
        tui_print("Conversation cleared.", style="info")
        return False

    if cmd == "/history":
        msg_count = len(app.isotope_agent.agent.messages)
        tui_print(f"Messages: {msg_count}", style="info")
        tui_print(
            f"Total tokens: in={app.total_input_tokens}, out={app.total_output_tokens}",
            style="info",
        )
        return False

    if cmd == "/debug":
        app.debug = not app.debug
        tui_print(f"Debug mode: {'on' if app.debug else 'off'}", style="info")
        return False

    if cmd == "/help":
        print_help()
        return False

    tui_print(f"Unknown command: {cmd}", style="warn")
    print_known_commands()
    return False


def handle_stream_input_line(
    app: TUIApp, line: str, *, prompt_toolkit: bool
) -> bool:
    """Handle one line of user input while streaming.

    Args:
        app: The TUI application instance.
        line: The input line.
        prompt_toolkit: Whether prompt_toolkit is active.

    Returns:
        True when the caller should stop reading more input.
    """
    line = line.strip()
    if not line:
        return False

    agent = app.isotope_agent.agent

    if line.startswith("/"):
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/follow" and arg:
            agent.follow_up(arg)
            _print_stream_notice(
                f"follow-up queued: {arg}",
                prompt_toolkit=prompt_toolkit,
                style="tool",
            )
        elif cmd == "/abort":
            agent.abort()
            _print_stream_notice(
                "aborting...",
                prompt_toolkit=prompt_toolkit,
                style="warn",
            )
            return True
        elif cmd in ("/follow", "/steer") and not arg:
            _print_stream_notice(
                f"usage: {cmd} <message>",
                prompt_toolkit=prompt_toolkit,
                style="warn",
            )
        return False

    # Any non-command text = steering
    app.steer_text = line
    app.cancel_stream()
    return True


def _print_stream_notice(
    message: str, *, prompt_toolkit: bool, style: str
) -> None:
    """Print a status line while the model is streaming."""
    if prompt_toolkit:
        print(f"  [{message}]", flush=True)
    else:
        tui_print(f"\n  [{message}]", style=style)
