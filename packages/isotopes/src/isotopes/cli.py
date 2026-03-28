"""CLI interface for isotopes.

Provides command-line access to run agents in TUI mode or one-shot execution.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import NoReturn

from isotopes_core.types import AgentEvent, AssistantMessage

from isotopes import __version__
from isotopes.agent import IsotopeAgent
from isotopes.config import (
    PROVIDER_DEFAULTS,
    create_provider,
    load_config,
)
from isotopes.presets import get_preset
from isotopes.rpc.server import RpcServer
from isotopes.session import SessionStore


# Default configuration values
DEFAULT_PRESET = "coding"


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="isotopes",
        description="Isotope AI agent framework",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"isotopes {__version__}",
    )

    # Global options
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use (overrides config)",
    )

    parser.add_argument(
        "--preset",
        choices=["coding", "assistant", "minimal"],
        default=DEFAULT_PRESET,
        help=f"Preset configuration to use (default: {DEFAULT_PRESET})",
    )

    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "minimax", "minimax-global", "proxy"],
        default=None,
        help="Provider type override for this session",
    )

    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable all tools",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat command
    chat_parser = subparsers.add_parser(
        "chat",
        help="Launch interactive TUI mode",
    )
    chat_parser.add_argument(
        "--session",
        help="Resume an existing session by session ID",
    )

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run a one-shot prompt",
    )
    run_parser.add_argument(
        "prompt",
        help="The prompt to send to the agent",
    )

    # Sessions command
    sessions_parser = subparsers.add_parser(
        "sessions",
        help="List and manage sessions",
    )
    sessions_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of sessions to display (default: 10)",
    )

    # RPC command
    rpc_parser = subparsers.add_parser(
        "rpc",
        help="Start JSONL-over-stdio RPC server",
    )
    rpc_parser.add_argument(
        "--session",
        help="Resume an existing session by session ID",
    )

    return parser


async def run_one_shot(
    prompt: str,
    model: str,
    preset: str,
    no_tools: bool,
    provider_type: str | None = None,
) -> None:
    """Execute a one-shot prompt and stream the response to stdout.

    Args:
        prompt: User prompt to send to the agent.
        model: Model name to use.
        preset: Preset configuration name.
        no_tools: Whether to disable tools.
        provider_type: Optional provider type override.
    """
    try:
        config = load_config()

        # Apply provider override
        if provider_type:
            defaults = PROVIDER_DEFAULTS.get(provider_type, {})
            config.provider.type = provider_type
            config.provider.base_url = defaults.get(
                "base_url", config.provider.base_url
            )

        # Resolve model
        effective_model = model or (config.model if config.model != "default" else None)
        if not effective_model:
            defaults = PROVIDER_DEFAULTS.get(
                config.provider.type, PROVIDER_DEFAULTS["proxy"]
            )
            effective_model = defaults["default_model"]

        # Env var notice
        if config.from_env:
            print(
                f"Using {config.provider.type} (from env). "
                "Run /setup in chat to configure.",
                file=sys.stderr,
            )

        provider = create_provider(effective_model, config)

        # Get preset configuration
        preset_config = get_preset(preset)

        # Create agent
        agent = IsotopeAgent(
            provider=provider,
            preset=preset_config,
            model=effective_model,
            workspace=os.getcwd(),
        )

        # Disable tools if requested
        if no_tools:
            agent._tools = []
            # Rebuild the core agent with no tools
            from isotopes_core import Agent

            agent._agent = Agent(
                provider=provider,
                system_prompt=agent._system_prompt,
                tools=[],
            )

        # Stream the response
        try:
            async for event in agent.run(prompt):
                handle_agent_event(event)

        except KeyboardInterrupt:
            print("\n[Interrupted]", file=sys.stderr)
            agent.abort()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_agent_event(event: AgentEvent) -> None:
    """Handle a single agent event for one-shot mode.

    Args:
        event: The agent event to process.
    """
    if event.type == "message_update":
        # Stream text content to stdout
        delta = getattr(event, "delta", None)
        if delta:
            print(delta, end="", flush=True)

    elif event.type == "tool_start":
        tool_name = getattr(event, "tool_name", "?")
        print(f"\n[calling {tool_name}]", file=sys.stderr)

    elif event.type == "tool_end":
        is_error = getattr(event, "is_error", False)
        if is_error:
            print("[tool error]", file=sys.stderr)

    elif event.type == "turn_end":
        # Print a final newline after the response
        print()

        # Optionally show token usage
        msg = getattr(event, "message", None)
        if isinstance(msg, AssistantMessage):
            usage = msg.usage
            print(
                f"[tokens: in={usage.input_tokens}, out={usage.output_tokens}]",
                file=sys.stderr,
            )


def launch_tui(
    model: str | None,
    preset: str,
    no_tools: bool,
    session_id: str | None = None,
    provider_type: str | None = None,
) -> None:
    """Launch the TUI interface.

    Args:
        model: Model name to use (None = use config default).
        preset: Preset configuration name.
        no_tools: Whether to disable tools.
        session_id: Optional session ID to resume.
        provider_type: Optional provider type override.
    """
    try:
        # Import TUI here to avoid import errors if dependencies aren't installed
        from isotopes.tui.app import TUI

        config = load_config()

        # Apply provider override
        if provider_type:
            defaults = PROVIDER_DEFAULTS.get(provider_type, {})
            config.provider.type = provider_type
            config.provider.base_url = defaults.get(
                "base_url", config.provider.base_url
            )

        # Resolve model
        effective_model = model or (config.model if config.model != "default" else None)

        # Create and configure TUI
        tui = TUI()
        tui.config = config
        if effective_model:
            tui.model = effective_model
        tui.preset = get_preset(preset)
        tui.tools_enabled = not no_tools

        # Set session ID if provided
        if session_id:
            tui.resume_session_id = session_id

        # Run the TUI
        asyncio.run(tui.run())

    except ImportError as e:
        if "prompt_toolkit" in str(e) or "rich" in str(e):
            print(
                "Error: TUI dependencies not installed. "
                "Install with: pip install isotopes[tui]",
                file=sys.stderr,
            )
        else:
            print(f"Import error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def list_sessions(limit: int = 10) -> None:
    """List sessions with formatted output.

    Args:
        limit: Maximum number of sessions to display.
    """
    session_store = SessionStore()

    try:
        sessions = session_store.list_sessions()

        if not sessions:
            print("No sessions found.")
            return

        # Limit the number of sessions
        sessions = sessions[:limit]

        # Print header
        print(f"{'ID':<8} {'Started':<19} {'Messages':<8} {'Last message'}")
        print("-" * 80)

        # Print session rows
        for session in sessions:
            # Format timestamp to remove timezone and seconds
            started_str = session.started_at[:19].replace("T", " ")
            last_msg_preview = session.last_message_preview[:40] + (
                "..." if len(session.last_message_preview) > 40 else ""
            )

            print(
                f"{session.id:<8} {started_str:<19} {session.message_count:<8} {last_msg_preview}"
            )

    except Exception as e:
        print(f"Error listing sessions: {e}", file=sys.stderr)
        sys.exit(1)


def run_rpc(model: str | None, preset: str, session_id: str | None = None) -> None:
    """Start the JSONL-over-stdio RPC server.

    Loads config, creates an IsotopeAgent, wraps it in an RpcServer,
    and runs until stdin is closed.  All log output goes to stderr so
    that stdout is reserved exclusively for JSONL events.

    Args:
        model: Model name to use (None = use config default).
        preset: Preset configuration name.
        session_id: Optional session ID to resume.
    """
    # Configure logging to stderr so stdout stays clean for JSONL
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = load_config()

    # Resolve model
    effective_model = model or (config.model if config.model != "default" else None)
    if not effective_model:
        defaults = PROVIDER_DEFAULTS.get(
            config.provider.type, PROVIDER_DEFAULTS["proxy"]
        )
        effective_model = defaults["default_model"]

    provider = create_provider(effective_model, config)

    preset_config = get_preset(preset)

    agent = IsotopeAgent(
        provider=provider,
        preset=preset_config,
        model=effective_model,
        workspace=os.getcwd(),
        session_id=session_id,
    )

    server = RpcServer(agent)
    asyncio.run(server.run())


def main() -> NoReturn:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Default to chat (TUI) when no command is given
    if not args.command:
        args.command = "chat"

    if args.command == "chat":
        session_id = getattr(args, "session", None)
        launch_tui(
            args.model,
            args.preset,
            args.no_tools,
            session_id,
            provider_type=args.provider,
        )

    elif args.command == "run":
        try:
            asyncio.run(
                run_one_shot(
                    args.prompt,
                    args.model,
                    args.preset,
                    args.no_tools,
                    provider_type=args.provider,
                )
            )
            sys.exit(0)
        except KeyboardInterrupt:
            print("\n[Interrupted]", file=sys.stderr)
            sys.exit(1)
        except Exception:
            sys.exit(1)

    elif args.command == "sessions":
        list_sessions(args.limit)
        sys.exit(0)

    elif args.command == "rpc":
        session_id = getattr(args, "session", None)
        run_rpc(args.model, args.preset, session_id)
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
