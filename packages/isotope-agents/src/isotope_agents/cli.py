"""CLI interface for isotope-agents.

Provides command-line access to run agents in TUI mode or one-shot execution.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import NoReturn

from isotope_core.providers.proxy import ProxyProvider
from isotope_core.types import AgentEvent, AssistantMessage

from isotope_agents import __version__
from isotope_agents.agent import IsotopeAgent
from isotope_agents.presets import get_preset


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
    subparsers.add_parser(
        "chat",
        help="Launch interactive TUI mode",
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


def launch_tui(model: str, preset: str, no_tools: bool) -> None:
    """Launch the TUI interface.

    Args:
        model: Model name to use.
        preset: Preset configuration name.
        no_tools: Whether to disable tools.
    """
    try:
        # Import TUI here to avoid import errors if dependencies aren't installed
        from isotope_agents.tui.app import TUI

        # Create and configure TUI
        tui = TUI()
        tui.model = model
        tui.preset = get_preset(preset)
        tui.tools_enabled = not no_tools

        # Run the TUI
        asyncio.run(tui.run())

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


def main() -> NoReturn:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle no command case
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "chat":
        launch_tui(args.model, args.preset, args.no_tools)

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

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()