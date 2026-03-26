"""isotope-agents TUI — interactive terminal user interface.

This module provides the modular TUI implementation for isotope-agents,
restructured from isotope-core/tui/main.py into clean, modular components.

Main components:
- app.TUI: Main TUI class with command handling and streaming
- commands.CommandHandler: Slash command handling (I/O-independent)
- commands.TUIState: Mutable TUI state
- commands.CommandResult: Return value from command handlers
- events.EventAction: Display-action descriptor for an agent event
- events.process_event: Pure event-to-action mapping (no I/O)
- input.StreamInputHandler: Input handling with prompt_toolkit support
- render: Output rendering helpers and stream buffering

Usage:
    from isotope_agents.tui import TUI, main

    # Run the TUI directly
    main()

    # Or create and configure a TUI instance
    tui = TUI()
    await tui.run()
"""

from __future__ import annotations

from .app import TUI, main
from .commands import CommandHandler, CommandResult, TUIState
from .events import EventAction, process_event
from .input import StreamInputHandler
from .render import _print, _print_inline, _StreamBuffer

__all__ = [
    "TUI",
    "main",
    "CommandHandler",
    "CommandResult",
    "TUIState",
    "EventAction",
    "process_event",
    "StreamInputHandler",
    "_print",
    "_print_inline",
    "_StreamBuffer",
]