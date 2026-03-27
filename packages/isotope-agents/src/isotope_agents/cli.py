"""CLI interface for isotope-agents.

Provides command-line access to run agents in TUI mode or one-shot execution.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import NoReturn

from isotope_core.providers.proxy import ProxyProvider
from isotope_core.types import AgentEvent, AssistantMessage

from isotope_agents import __version__
from isotope_agents.agent import IsotopeAgent
from isotope_agents.config import load_config
from isotope_agents.presets import get_preset
from isotope_agents.rpc.server import RpcServer
from isotope_agents.session import SessionStore


# Default configuration values
DEFAULT_MODEL = "claude-opus-4.6"
DEFAULT_PRESET = "coding"
PROXY_BASE_URL = "http://localhost:4141/v1"


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="isotope",
        description="Isotope AI agent framework",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"isotope-agents {__version__}",
    )

    # Global options
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model to use (default: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--preset",
        choices=["coding", "assistant", "minimal"],
        default=DEFAULT_PRESET,
        help=f"Preset configuration to use (default: {DEFAULT_PRESET})",
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
) -> None:
    """Execute a one-shot prompt and stream the response to stdout.

    Args:
        prompt: User prompt to send to the agent.
        model: Model name to use.
        preset: Preset configuration name.
        no_tools: Whether to disable tools.
    """
    try:
        # Create provider
        provider = ProxyProvider(
            model=model,
            base_url=PROXY_BASE_URL,
            api_key="not-needed",
        )

        # Get preset configuration
        preset_config = get_preset(preset)

        # Create agent
        agent = IsotopeAgent(
            provider=provider,
            preset=preset_config,
            model=model,
            workspace=os.getcwd(),
        )

        # Disable tools if requested
        if no_tools:
            agent._tools = []
            # Rebuild the core agent with no tools
            from isotope_core import Agent
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


def launch_tui(model: str, preset: str, no_tools: bool, session_id: str | None = None) -> None:
    """Launch the TUI interface.

    Args:
        model: Model name to use.
        preset: Preset configuration name.
        no_tools: Whether to disable tools.
        session_id: Optional session ID to resume.
    """
    try:
        # Import TUI here to avoid import errors if dependencies aren't installed
        from isotope_agents.tui.app import TUI

        # Create and configure TUI
        tui = TUI()
        tui.model = model
        tui.preset = get_preset(preset)
        tui.tools_enabled = not no_tools

        # Set session ID if provided
        if session_id:
            tui.resume_session_id = session_id

        # Run the TUI
        asyncio.run(tui.run())

    except KeyboardInterrupt:
        # Safety net — the asyncio SIGINT handler in TUI.run() should
        # handle Ctrl+C cleanly via os._exit(0), but catch it here too
        # in case it escapes (e.g., during model selection before the
        # handler is installed).
        print("\nBye!")
        sys.exit(0)
    except ImportError as e:
        if "prompt_toolkit" in str(e) or "rich" in str(e):
            print(
                "Error: TUI dependencies not installed. "
                "Install with: pip install isotope-agents[tui]",
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
            started_str = session.started_at[:19].replace('T', ' ')
            last_msg_preview = session.last_message_preview[:40] + ("..." if len(session.last_message_preview) > 40 else "")

            print(f"{session.id:<8} {started_str:<19} {session.message_count:<8} {last_msg_preview}")

    except Exception as e:
        print(f"Error listing sessions: {e}", file=sys.stderr)
        sys.exit(1)


def run_rpc(model: str, preset: str, session_id: str | None = None) -> None:
    """Start the JSONL-over-stdio RPC server.

    Loads config, creates an IsotopeAgent, wraps it in an RpcServer,
    and runs until stdin is closed.  All log output goes to stderr so
    that stdout is reserved exclusively for JSONL events.

    Args:
        model: Model name to use.
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

    # CLI flags override config-file values
    effective_model = model if model != DEFAULT_MODEL else (config.model if config.model != "default" else DEFAULT_MODEL)

    provider = ProxyProvider(
        model=effective_model,
        base_url=config.provider.base_url + "/v1",
        api_key=config.provider.api_key or "not-needed",
    )

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

    # Handle no command case
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "chat":
        session_id = getattr(args, 'session', None)
        launch_tui(args.model, args.preset, args.no_tools, session_id)

    elif args.command == "run":
        try:
            asyncio.run(run_one_shot(
                args.prompt,
                args.model,
                args.preset,
                args.no_tools,
            ))
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