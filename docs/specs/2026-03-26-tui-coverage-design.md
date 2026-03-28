# TUI Test Coverage Improvement — Design Doc

**Date:** 2026-03-26
**Status:** Approved
**Owner:** Tachikoma
**Branch:** `user/tachikoma/tui-coverage` (from `main`)
**Goal:** Raise isotopes coverage from 65% to 85%+

---

## Problem

TUI code is the main coverage gap: `app.py` 11%, `input.py` 19%, `render.py` 48%, `cli.py` 41%. These modules mix business logic (command handling, event processing, session management) with terminal I/O (prompt-toolkit, Rich Console). The I/O coupling makes them hard to test.

## Strategy

1. **Extract testable logic** from `app.py` into pure functions/classes
2. **Test the extracted logic** with standard unit tests
3. **Test I/O wiring** with prompt-toolkit's headless testing API (`create_pipe_input()` + `DummyOutput`)
4. **Test CLI** with subprocess/argument parsing tests

---

## Subtasks

### T1: Extract command handler from TUI

**Files:**
- `packages/isotopes/src/isotopes/tui/commands.py` (new)
- `packages/isotopes/src/isotopes/tui/app.py` (refactor)

**~200 LOC, M**

Extract `_handle_command()` and related state management into a standalone `CommandHandler` class that doesn't depend on prompt-toolkit or Rich:

```python
@dataclass
class CommandResult:
    """Result of executing a TUI command."""
    should_quit: bool = False
    message: str = ""           # feedback text for the user
    style: str = "info"
    action: str | None = None   # "rebuild_agent", "compact", etc.

class CommandHandler:
    """Handles slash commands independent of terminal I/O."""

    def __init__(self, state: TUIState):
        self.state = state

    async def handle(self, line: str) -> CommandResult:
        """Parse and execute a slash command. Returns result without printing."""
        ...
```

Extract TUI mutable state into a `TUIState` dataclass:
```python
@dataclass
class TUIState:
    model: str = "claude-opus-4.6"
    preset: Any = None
    tools_enabled: bool = True
    debug: bool = False
    custom_system_prompt: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
```

`app.py` TUI class delegates to `CommandHandler`, keeping only the I/O glue.

**Tests:** `packages/isotopes/tests/test_tui_commands.py`
- Test each command: `/tools`, `/model`, `/system`, `/clear`, `/compact`, `/history`, `/sessions`, `/debug`, `/help`, `/quit`
- Test unknown commands
- Test argument parsing edge cases

**Commit after done.**

---

### T2: Extract event consumer logic

**Files:**
- `packages/isotopes/src/isotopes/tui/events.py` (new)
- `packages/isotopes/src/isotopes/tui/app.py` (refactor)

**~150 LOC, M**

Extract the event processing from `_consume_stream_events()` into a pure event handler:

```python
@dataclass
class EventAction:
    """Action to take for a TUI event."""
    type: str  # "text", "tool_start", "tool_end", "message_end", "usage", "debug", "none"
    content: str = ""
    tool_name: str = ""
    is_error: bool = False
    input_tokens: int = 0
    output_tokens: int = 0

def process_event(event: AgentEvent, *, debug: bool = False) -> list[EventAction]:
    """Convert an AgentEvent into display actions, without doing I/O."""
```

This makes event-to-display-action mapping testable without any terminal. `app.py` calls `process_event()` then applies the actions to the actual display.

**Tests:** `packages/isotopes/tests/test_tui_events.py`
- Test each event type: `message_update`, `tool_start`, `tool_end`, `message_end`, `turn_end`, `steer`, `follow_up`, `agent_end`
- Test debug mode on/off
- Test edge cases (missing attributes, empty deltas)

**Commit after done.**

---

### T3: Test render.py and StreamBuffer

**File:** `packages/isotopes/tests/test_render.py` (extend existing)

**~100 LOC, S**

Extend existing render tests to cover the untested code:

- `_print()` and `_print_inline()` — test with capsys
- `_StreamBuffer` — test `write()`, `flush()`, `drain()`, `discard()` with partial lines, newlines, empty strings
- `render_markdown()` — test with Rich unavailable (mock import failure)
- `render_tool_output()` — test error vs non-error, empty output, long output, Rich unavailable fallback

**Commit after done.**

---

### T4: Test input handler (headless prompt-toolkit)

**File:** `packages/isotopes/tests/test_tui_input.py` (new)

**~150 LOC, M**

Test `StreamInputHandler` methods:

For methods that don't need a terminal:
- `handle_stream_input_line()` — test `/follow`, `/abort`, `/follow` without arg, plain text (steering), empty input
- `set_prefill_text()` / `clear_prefill_text()`
- `has_prompt_toolkit` property

For prompt-toolkit integration (if available):
- Use `create_pipe_input()` + `DummyOutput` to test `create_stream_prompt_app()`
- Test that typing text and pressing Enter returns the text
- Test that Ctrl+C calls agent.abort()
- Skip these tests if prompt-toolkit not installed (`pytest.importorskip`)

**Commit after done.**

---

### T5: Improve CLI test coverage

**File:** `packages/isotopes/tests/test_cli.py` (extend)

**~100 LOC, S**

The existing CLI tests likely cover argument parsing. Add:

- `create_parser()` — test all subcommands and their arguments
- `handle_agent_event()` — test with each event type (capsys to capture output)
- `list_sessions()` — test with mock SessionStore (empty, with sessions, with error)
- `run_rpc()` — test that it creates RpcServer correctly (mock dependencies)
- `main()` — test with mock sys.argv for each subcommand
- Test `--version` flag
- Test no subcommand (should print help and exit)

**Commit after done.**

---

### T6: Verify + clean up

- Run full test suite, verify all pass
- Run `pytest --cov` and confirm isotopes coverage is 85%+
- `ruff check` clean
- Push, open PR

**Commit after done.**

---

## Notes

- The key insight is **extract → test → delegate**. We're not trying to test prompt-toolkit itself, just our logic.
- `CommandHandler` and `process_event()` become the tested "core" of the TUI. The actual `TUI` class becomes thin glue.
- T3 and T4 can run in parallel since they touch different files.
- Target: `app.py` from 11% → ~60%, `input.py` from 19% → ~70%, `render.py` from 48% → ~90%, `cli.py` from 41% → ~80%. Combined agents coverage: 65% → 85%+.
