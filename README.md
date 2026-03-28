# isotopes

A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.

## Architecture

Isotopes is a monorepo with two packages:

| Package | Location | Description |
|---|---|---|
| **isotopes-core** | [`packages/isotope-core/`](packages/isotope-core/) | Agent loop engine, LLM providers, middleware, events, context management |
| **isotopes** | [`packages/isotope-agents/`](packages/isotope-agents/) | Tools, TUI, CLI, sessions, RPC protocol, presets, skills, MCP integration |

**isotopes-core** is the foundation. It provides:
- Agent loop (plan → act → observe → repeat)
- LLM provider abstraction (OpenAI, Anthropic, proxy, router)
- Composable middleware chain
- Typed event streaming
- Context management with pruning strategies
- `@auto_tool` decorator for zero-boilerplate tool definitions
- File operation tracking

**isotopes** is the framework built on isotopes-core. It provides:
- Concrete tools (bash, read, write, edit, grep, glob, web search, web fetch)
- Interactive TUI with Rich rendering
- CLI with chat, run, rpc, and sessions commands
- Session persistence in JSONL format
- RPC protocol for embedding agents in external applications
- Preset configurations (coding, assistant, minimal)
- Skill extension system via SKILL.md files
- MCP (Model Context Protocol) integration

## Quick Start

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run directly without installing (uses uvx)
uvx --from 'isotopes[tui]' isotopes chat
uvx --from 'isotopes[tui]' isotopes run "Explain this codebase"
```

### From Source (Development)

```bash
git clone https://github.com/GhostComplex/isotopes.git
cd isotopes

# Sync with TUI support
uv sync --package isotopes --extra tui

# Launch interactive TUI
uv run isotopes --model claude-opus-4.6 --preset coding chat

# Run a one-shot prompt
uv run isotopes run "Explain this codebase"

# Start RPC server
uv run isotopes rpc
```

#### Available Extras

| Extra | Install | What it adds |
|-------|---------|--------------|
| `tui` | `uv sync --package isotopes --extra tui` | Interactive TUI (Rich + prompt-toolkit) |
| `mcp` | `uv sync --package isotopes --extra mcp` | MCP server integration |
| `all` | `uv sync --package isotopes --extra all` | Everything above |

## Development

```bash
# Run all tests
uv run pytest packages/isotope-core/tests/ -q
uv run pytest packages/isotope-agents/tests/ -q

# Lint
uv run ruff check packages/

# Type check
uv run mypy packages/isotope-core/src/
```

### Publishing to PyPI

Packages are published via GitHub releases with trusted publishing:

```bash
# Release isotopes-core
gh release create core-v0.0.1 --title "isotopes-core v0.0.1"

# Release isotopes
gh release create v0.0.1 --title "isotopes v0.0.1"
```

## Configuration

Isotope reads configuration from `~/.isotopes/config.yaml`. See the [isotopes README](packages/isotope-agents/README.md#configuration) for details.

## Documentation

- [isotopes-core API](packages/isotope-core/README.md) — engine, providers, middleware, tools
- [isotopes guide](packages/isotope-agents/README.md) — CLI, tools, presets, RPC, sessions
- [Project Requirements](docs/PRD.md) — design goals and product requirements
- [Design Specs](docs/specs/) — milestone design documents

## Requirements

- Python 3.11+
- LLM provider access (OpenAI, Anthropic, or any OpenAI-compatible endpoint)

## License

MIT
