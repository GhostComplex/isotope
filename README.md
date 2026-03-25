# Isotope

**A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.**

Built on top of [isotope-core](https://github.com/GhostComplex/isotopo-core), Isotope provides a complete agent framework with modular tools, presets, an interactive TUI, and a CLI.

## Installation

```bash
# Core (CLI + agent framework)
pip install isotope-agents

# With TUI support (prompt-toolkit + rich)
pip install isotope-agents[tui]

# Everything
pip install isotope-agents[all]
```

## Quick Start

```bash
# Interactive TUI chat (default: coding preset)
isotope chat

# Use a specific preset
isotope chat --preset coding
isotope chat --preset assistant
isotope chat --preset minimal

# One-shot prompt
isotope run "explain this error" --preset coding

# Print mode (non-interactive, for scripting)
isotope run --print "summarize this file"

# Override model
isotope chat --model claude-sonnet-4-20250514
```

## Presets

Presets define the agent's role — system prompt, tools, and behavior.

| Preset | Tools | Use Case |
|---|---|---|
| `coding` | bash, read, write, edit, grep, glob | Software development |
| `assistant` | bash, read, write | General tasks |
| `minimal` | *(none)* | Bare LLM — add your own tools |

## Tools

| Tool | Description |
|---|---|
| `bash` | Execute shell commands (timeout support) |
| `read` | Read file contents (with offset/limit) |
| `write` | Create/overwrite files (creates parent dirs) |
| `edit` | Find-and-replace exact text in files |
| `grep` | Search file contents with regex (ripgrep-backed) |
| `glob` | List files matching glob patterns |

## Configuration

Create `~/.isotope/config.yaml`:

```yaml
preset: coding
model: claude-opus-4.6
provider:
  base_url: http://localhost:4141/v1
  api_key: not-needed
```

CLI flags override config file settings.

## Python API

```python
from isotope_agents import IsotopeAgent

# Create an agent with a preset
agent = IsotopeAgent(preset="coding")

# Use it programmatically
async for event in agent.agent.prompt("Fix the bug in auth.py"):
    if event.type == "message_update":
        print(getattr(event, "delta", ""), end="")
```

## Architecture

```
isotope-agents
├── IsotopeAgent      Preset-based agent wrapping isotope-core
├── Presets            Role configurations (coding, assistant, minimal)
├── Tools              Modular tools (bash, read, write, edit, grep, glob)
├── TUI                Interactive chat with streaming + steering
└── CLI                isotope chat / isotope run

         │ depends on
         ▼

isotope-core           Agent loop, providers, middleware, events
```

## TUI Features

- **Streaming responses** with real-time output
- **Claude Code-style steering** — type during streaming to redirect the agent
- **prompt-toolkit integration** — visible input prompt during streaming
- **Rich markdown rendering** — code blocks with syntax highlighting, formatted headings, lists
- **Slash commands** — `/tools`, `/model`, `/system`, `/clear`, `/history`, `/debug`
- **Follow-up queuing** — `/follow` to queue messages for after completion
- **Abort** — `/abort` or Ctrl-C to stop the current response

## Sessions

Conversations persist across restarts. Sessions are saved to `~/.isotope/sessions/`.

```bash
# Resume a saved session
isotope chat --session <session-id>

# List all sessions
isotope sessions

# Delete a session
isotope sessions --delete <session-id>
```

### TUI Session Commands

| Command | Description |
|---|---|
| `/session` | Show current session info |
| `/sessions` | List saved sessions |
| `/session <id>` | Switch to a different session |
| `/save` | Force save current session |
| `/new` | Start a new session |

## Development

```bash
# Clone and install in development mode
git clone https://github.com/GhostComplex/isotope.git
cd isotope
pip install -e ".[all]"

# Run tests
pytest tests/ -v

# Lint
ruff check src/ tests/
```

## Links

- [PRD](docs/PRD.md) — Product requirements document
- [isotope-core](https://github.com/GhostComplex/isotope-core) — Core agent loop library
