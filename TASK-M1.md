# M1 Implementation Task: Lift + Modularize + Ship

## Context

You are building `isotope-agents`, a pluggable Python agent framework built on top of `isotope-core` (isotopo-core).

**isotope-core** already exists at `/tmp/isotopo-core/` — it provides:
- `Agent` class with `prompt()`, `continue_()`, steering, follow-ups, abort
- `Tool` class with name, description, parameters (JSON schema), execute function
- `ToolResult` with `.text()`, `.error()` factory methods
- `Provider` abstraction (OpenAI, Anthropic, proxy)
- Event system (AgentEvent, streaming events)
- Context management, middleware, hooks

**isotope-core TUI** exists at `/tmp/isotopo-core/tui/main.py` (~1062 LoC) — it provides:
- Interactive chat with streaming
- Claude Code-style steering (type during streaming to redirect)
- prompt-toolkit integration
- Slash commands (/tools, /model, /system, /clear, /history, /debug)
- Built-in tools: read_file, write_file, edit_file, terminal, get_current_time
- Follow-up queuing (/follow) and abort (/abort)

## What to Build

Create the `isotope-agents` package in `/tmp/isotope/` with this structure:

```
isotope/
├── src/isotope_agents/
│   ├── __init__.py              # Public API exports
│   ├── agent.py                 # IsotopeAgent wrapping isotope-core Agent
│   ├── presets.py               # Preset definitions (coding, assistant, minimal)
│   ├── config.py                # Config file loading (~/.isotope/config.yaml)
│   ├── cli.py                   # CLI entry point (click)
│   ├── tui/
│   │   ├── __init__.py
│   │   ├── app.py               # Main TUI app (lifted from isotopo-core tui/main.py)
│   │   ├── input.py             # Input handling (prompt-toolkit)
│   │   ├── output.py            # Output rendering
│   │   └── commands.py          # Slash command handlers
│   └── tools/
│       ├── __init__.py          # Tool registry / helpers
│       ├── bash.py              # BashTool (from existing terminal tool)
│       ├── read.py              # ReadTool (from existing read_file)
│       ├── write.py             # WriteTool (from existing write_file)
│       ├── edit.py              # EditTool (from existing edit_file)
│       ├── grep.py              # GrepTool (NEW — ripgrep-backed)
│       └── glob.py              # GlobTool (NEW — glob patterns + directory listing)
├── tests/
│   ├── __init__.py
│   ├── test_tools.py            # Tool unit tests
│   ├── test_presets.py          # Preset tests
│   ├── test_agent.py            # Agent wrapper tests
│   └── test_cli.py              # CLI smoke tests
├── pyproject.toml
├── README.md
└── docs/
    └── PRD.md                   # Already exists
```

## Step-by-Step Instructions

### 1. pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "isotope-agents"
version = "0.1.0"
description = "A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [{ name = "GhostComplex" }]
dependencies = [
    "isotopo-core>=0.1.0",
    "click>=8.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
tui = [
    "prompt-toolkit>=3.0",
    "rich>=13.0",
]
search = ["httpx>=0.27"]
all = ["isotope-agents[tui,search]"]

[project.scripts]
isotope = "isotope_agents.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/isotope_agents"]
```

### 2. Tools (src/isotope_agents/tools/)

Lift the existing tools from `/tmp/isotopo-core/tui/main.py`. The existing TUI defines tools inline — extract them into separate files.

Each tool should be a function that returns an `isotopo_core.Tool` instance. Use the `@tool` decorator or manual Tool construction.

**Important**: Look at how the existing TUI defines its tools (search for `Tool(` in `/tmp/isotopo-core/tui/main.py`) and extract them. The tools use `isotopo_core.tools.Tool` and `isotopo_core.tools.ToolResult`.

#### BashTool (tools/bash.py)
- Lift from the `terminal` tool in the TUI
- Runs shell commands via subprocess
- Returns stdout/stderr
- Has timeout support

#### ReadTool (tools/read.py)
- Lift from `read_file` in the TUI
- Reads file contents
- Supports offset/limit for large files

#### WriteTool (tools/write.py)
- Lift from `write_file` in the TUI
- Creates/overwrites files
- Creates parent directories

#### EditTool (tools/edit.py)
- Lift from `edit_file` in the TUI
- Find-and-replace exact text in files

#### GrepTool (tools/grep.py) — NEW
- Search file contents using regex patterns
- Use `subprocess` to call `rg` (ripgrep) if available, fall back to `grep -rn`
- Parameters: pattern (required), path (default "."), include (file glob), max_results (default 50)
- Returns matching lines with file:line format

#### GlobTool (tools/glob.py) — NEW
- List files matching glob patterns
- Use Python's `pathlib.Path.glob()` or `glob.glob()`
- Parameters: pattern (required), path (default ".")
- Returns list of matching file paths

### 3. Presets (src/isotope_agents/presets.py)

```python
from dataclasses import dataclass, field
from isotopo_core import Tool

@dataclass
class Preset:
    name: str
    system_prompt: str
    tools: list[str]  # tool names to enable by default
    description: str = ""

CODING_PRESET = Preset(
    name="coding",
    system_prompt="You are an expert coding assistant...",  # Write a good one
    tools=["bash", "read", "write", "edit", "grep", "glob"],
    description="Software development with file and shell tools",
)

ASSISTANT_PRESET = Preset(
    name="assistant",
    system_prompt="You are a helpful personal assistant...",  # Write a good one
    tools=["bash", "read", "write"],
    description="General tasks with basic file and shell tools",
)

MINIMAL_PRESET = Preset(
    name="minimal",
    system_prompt="",
    tools=[],
    description="Bare LLM — add your own tools",
)

PRESETS = {
    "coding": CODING_PRESET,
    "assistant": ASSISTANT_PRESET,
    "minimal": MINIMAL_PRESET,
}
```

### 4. Agent (src/isotope_agents/agent.py)

A thin wrapper around `isotopo_core.Agent` that:
- Takes a preset name or Preset object
- Resolves tools from the preset
- Sets the system prompt
- Delegates to `isotopo_core.Agent` for the actual loop

### 5. Config (src/isotope_agents/config.py)

Load config from `~/.isotope/config.yaml`:
```yaml
preset: coding
model: claude-opus-4.6
provider:
  base_url: http://localhost:4141/v1
```

Use PyYAML. Fall back to defaults if file doesn't exist.

### 6. TUI (src/isotope_agents/tui/)

Lift the TUI from `/tmp/isotopo-core/tui/main.py` and modularize:

- `app.py` — Main TUI application class, the run loop
- `input.py` — prompt-toolkit input handling (extract the input-related code)
- `output.py` — Output printing/formatting
- `commands.py` — Slash command parsing and handlers

The TUI should use `IsotopeAgent` (from agent.py) with the configured preset.
It should work the same as the existing TUI but use the modular tool/preset system.

### 7. CLI (src/isotope_agents/cli.py)

```python
import click

@click.group()
def main():
    """Isotope — a pluggable Python agent framework."""
    pass

@main.command()
@click.option("--preset", default=None, help="Preset to use (coding, assistant, minimal)")
@click.option("--model", default=None, help="Model to use")
def chat(preset, model):
    """Start interactive TUI chat."""
    # Load config, create agent with preset, run TUI
    ...

@main.command()
@click.argument("prompt")
@click.option("--preset", default=None)
@click.option("--model", default=None)
@click.option("--print", "print_mode", is_flag=True, help="Non-interactive output")
def run(prompt, preset, model, print_mode):
    """Run a one-shot prompt."""
    ...
```

### 8. Tests

Write tests that:
- Test each tool can be instantiated and has correct schema
- Test presets contain valid tool names
- Test config loading with missing file (defaults)
- Test CLI commands exist (click testing)
- Test tool execution where possible (read, write, edit on temp files; grep/glob on temp dirs)

### 9. README.md

Write a concise README with:
- What isotope-agents is
- Installation: `pip install isotope-agents[tui]`
- Quick start: `isotope chat`, `isotope run "prompt"`
- Presets explanation
- Link to PRD

## Key References

- isotope-core source: `/tmp/isotopo-core/src/isotopo_core/`
- isotope-core TUI (to lift from): `/tmp/isotopo-core/tui/main.py`
- isotope-core tools API: `Tool(name, description, parameters, execute)`, `ToolResult.text()`, `ToolResult.error()`
- isotope-core Agent API: `Agent(provider=...)`, `agent.set_system_prompt()`, `agent.set_tools()`, `agent.prompt()`, `agent.continue_()`
- PRD: `/tmp/isotope/docs/PRD.md`

## Rules

1. All code goes in `/tmp/isotope/` (the repo)
2. Do NOT modify isotope-core (`/tmp/isotopo-core/`)
3. Use `isotopo_core` as import name (that's the installed package name)
4. Python >=3.11, type hints everywhere
5. Create a working `pyproject.toml` that can be pip installed
6. Branch: work on a new branch `feat/m1-agents`, NOT main
7. Make atomic commits as you go
8. The TUI must actually work end-to-end (with a proxy at localhost:4141)
9. Tests should pass without a running LLM proxy (mock where needed)
