# M1: Lift + Modularize + Ship — Design Doc

**Date:** 2026-03-26
**Status:** Approved
**Owner:** Tachikoma
**Branch:** `user/tachikoma/dev-m1` (from `main`)
**PRD Reference:** §5 (Tool System), §12 M1 checklist

---

## Goal

Working CLI agent with modular tools, preset system, and `@tool` decorator. Ship to PyPI.

After M1: `pip install isotopes[tui]` → `isotopes chat --preset coding` works.

## Success Criteria

- `isotopes chat` launches interactive TUI with all existing features
- `isotopes run "prompt"` works in print mode
- `--preset coding|assistant|minimal` selects tool sets + system prompts
- All 6 tools work (bash, read, write, edit, grep, glob) with truncation
- `@tool` decorator generates JSON schema from type hints
- TUI code removed from `packages/isotopes-core/tui/`
- All existing isotopes-core tests still pass
- New tests for isotopes tools, presets, CLI

---

## Subtasks

### M1.1: `@tool` decorator in isotopes-core

**File:** `packages/isotopes-core/src/isotopes_core/tools.py`
**~100 LOC, S**

Add a `@tool` decorator that auto-generates a `Tool` from a function:

```python
from isotopes_core import tool

@tool
async def grep(pattern: str, path: str = ".", include: str | None = None) -> str:
    """Search for a pattern using ripgrep.

    Args:
        pattern: Regex pattern to search for.
        path: Directory to search in.
        include: Glob pattern to filter files.
    """
    ...
```

The decorator:
1. Extracts function name → `tool.name`
2. First line of docstring → `tool.description`
3. Args section of docstring → parameter descriptions
4. Type hints → JSON schema types (`str` → `string`, `int` → `integer`, `bool` → `boolean`, `float` → `number`)
5. Parameters without defaults → `required`
6. `X | None` → optional (not required)
7. Wraps function to match `Tool.execute` signature (`tool_call_id, params, signal, on_update`)

The result is a standard `Tool` object — same as manually constructed.

**Tests:** Add to `packages/isotopes-core/tests/test_tools.py`

**Commit after done.**

---

### M1.2: Tool output truncation utility

**File:** `packages/isotopes/src/isotopes/tools/__init__.py`
**~50 LOC, S**

```python
def truncate_output(text: str, max_chars: int = 30_000, strategy: str = "head_tail") -> str:
    """Truncate tool output to stay within context limits.

    Strategies:
        head: Keep first max_chars characters
        tail: Keep last max_chars characters
        head_tail: Keep first and last portions with '... truncated ...' in middle
    """
```

**Tests:** `packages/isotopes/tests/test_truncation.py`

**Commit after done.**

---

### M1.3: Extract tools from TUI into separate modules

**Files:**
- `packages/isotopes/src/isotopes/tools/bash.py`
- `packages/isotopes/src/isotopes/tools/read.py`
- `packages/isotopes/src/isotopes/tools/write.py`
- `packages/isotopes/src/isotopes/tools/edit.py`

**~300 LOC total (mostly lift from tui/main.py `_make_tools()`), M**

Lift each tool function from `tui/main.py` lines 196-345 into its own module. Each module exports a `Tool` instance. Use the `@tool` decorator where appropriate, or `Tool()` constructor for tools needing complex parameter schemas.

Key changes from the TUI originals:
- Use `truncate_output()` from M1.2 instead of inline truncation
- Consistent timeout handling for bash (configurable, default 30s, cap 120s)
- Better error messages

**Tests:** `packages/isotopes/tests/test_tools_bash.py`, etc.

**Commit after done.**

---

### M1.4: New tools — GrepTool + GlobTool

**Files:**
- `packages/isotopes/src/isotopes/tools/grep.py`
- `packages/isotopes/src/isotopes/tools/glob.py`

**~150 LOC total, M**

**GrepTool:**
- Uses `ripgrep` (`rg`) if available, falls back to Python `re` + `os.walk`
- Parameters: `pattern` (required), `path` (default "."), `include` (glob filter), `max_results` (default 100)
- Output truncated via `truncate_output()`

**GlobTool:**
- Uses Python `pathlib.Path.glob()` / `Path.rglob()`
- Parameters: `pattern` (required), `path` (default ".")
- Lists matching files with relative paths
- Output truncated

**Tests:** `packages/isotopes/tests/test_tools_grep.py`, `test_tools_glob.py`

**Commit after done.**

---

### M1.5: Preset system

**File:** `packages/isotopes/src/isotopes/presets.py`
**~100 LOC, S**

```python
@dataclass
class Preset:
    name: str
    system_prompt: str
    tools: list[Tool]
    description: str = ""

CODING_PRESET = Preset(
    name="coding",
    system_prompt="You are a coding agent...",
    tools=[bash_tool, read_tool, write_tool, edit_tool, grep_tool, glob_tool],
)

ASSISTANT_PRESET = Preset(
    name="assistant",
    system_prompt="You are a helpful assistant...",
    tools=[bash_tool, read_tool, write_tool],
)

MINIMAL_PRESET = Preset(
    name="minimal",
    system_prompt="",
    tools=[],
)

def get_preset(name: str) -> Preset: ...
def list_presets() -> list[str]: ...
```

**Tests:** `packages/isotopes/tests/test_presets.py`

**Commit after done.**

---

### M1.6: Agent class wrapping isotopes-core

**File:** `packages/isotopes/src/isotopes/agent.py`
**~150 LOC, M**

Thin wrapper around `isotopes_core.Agent` that:
- Takes a preset name or `Preset` object
- Registers preset tools with the core agent
- Sets system prompt from preset
- Passes through all other `Agent` functionality (streaming, steering, follow-up, abort)

```python
class IsotopeAgent:
    def __init__(self, preset: str | Preset = "coding", model: str = "default", **kwargs):
        ...
```

**Tests:** `packages/isotopes/tests/test_agent.py`

**Commit after done.**

---

### M1.7: Lift TUI into isotopes

**Files:**
- `packages/isotopes/src/isotopes/tui/app.py` — main loop + orchestration
- `packages/isotopes/src/isotopes/tui/input.py` — prompt-toolkit input, steering
- `packages/isotopes/src/isotopes/tui/output.py` — rendering, token display
- `packages/isotopes/src/isotopes/tui/commands.py` — slash command handlers

**~1100 LOC (split from tui/main.py), L**

Split the existing `tui/main.py` (1116 lines) into 4 focused modules:

1. **app.py** (~400 LOC): `TUIApp` class — main event loop, agent instantiation, message handling, `run()` entry point
2. **input.py** (~250 LOC): `InputHandler` — prompt-toolkit integration, steering during streaming, follow-up queue, abort
3. **output.py** (~250 LOC): `OutputHandler` — event consumption, tool call display, token usage, StreamBuffer
4. **commands.py** (~200 LOC): `CommandHandler` — slash command parsing + handlers (/tools, /model, /system, /clear, /history, /debug, /help, /quit)

The TUI now uses `IsotopeAgent` from M1.6 instead of directly using `isotopes_core.Agent`. Tools come from presets (M1.5), not inline `_make_tools()`.

**After this subtask:** Remove `packages/isotopes-core/tui/` directory and `test_tui_main.py`.

**Tests:** Adapt existing `test_tui_main.py` to new structure.

**Commit after done.**

---

### M1.8: CLI entry point

**File:** `packages/isotopes/src/isotopes/cli.py`
**~100 LOC, S**

```bash
# Interactive TUI
isotopes chat
isotopes chat --preset coding
isotopes chat --model claude-sonnet-4-20250514

# One-shot (print mode, non-interactive)
isotopes run "fix the bug in auth.py"
isotopes run --preset assistant "summarize this document"
isotopes run --print "explain this code"
```

Uses argparse or click. Subcommands: `chat`, `run`.

Common flags: `--preset`, `--model`, `--system` (system prompt override), `--debug`.

**Tests:** `packages/isotopes/tests/test_cli.py` (argument parsing only, no live agent)

**Commit after done.**

---

### M1.9: Clean up + verify

- Remove `packages/isotopes-core/tui/` directory
- Remove `packages/isotopes-core/tests/test_tui_main.py`
- Verify all isotopes-core tests still pass (437 - tui test)
- Verify all new isotopes tests pass
- `ruff check` + `mypy` clean for both packages
- Update `packages/isotopes/pyproject.toml` with any missing dependencies
- Update `packages/isotopes/README.md`

**Commit, push, open PR to main.**

---

## Notes

- The `@tool` decorator goes in isotopes-core because it's schema generation — no tool implementations
- Tool implementations go in isotopes — that's the opinionated layer
- The TUI split doesn't need to be architecturally perfect — we can refactor later. The goal is to get it out of isotopes-core and working in isotopes
- System prompts for presets should be thoughtful but not overthought — they'll be iterated
- `get_current_time` tool from the original TUI is dropped — it's trivial enough for the model to handle via bash
