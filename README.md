# isotope

A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.

## Architecture

Isotope is a monorepo with two packages:

| Package | Location | Description |
|---|---|---|
| **isotope-core** | [`packages/isotope-core/`](packages/isotope-core/) | Agent loop engine, LLM providers, middleware, events, context management |
| **isotope-agents** | [`packages/isotope-agents/`](packages/isotope-agents/) | Tools, TUI, CLI, sessions, RPC protocol, presets, skills, MCP integration |

**isotope-core** is the foundation. It provides:
- Agent loop (plan → act → observe → repeat)
- LLM provider abstraction (OpenAI, Anthropic, proxy, router)
- Composable middleware chain
- Typed event streaming
- Context management with pruning strategies
- `@auto_tool` decorator for zero-boilerplate tool definitions
- File operation tracking

**isotope-agents** is the framework built on isotope-core. It provides:
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
uvx --from 'isotope-agents[tui]' isotope chat
uvx --from 'isotope-agents[tui]' isotope run "Explain this codebase"
```

### From Source (Development)

```bash
git clone https://github.com/GhostComplex/isotope.git
cd isotope

# Sync with TUI support
uv sync --package isotope-agents --extra tui

# Launch interactive TUI
uv run isotope --model claude-opus-4.6 --preset coding chat

# Run a one-shot prompt
uv run isotope run "Explain this codebase"

# Start RPC server
uv run isotope rpc
```

#### Available Extras

| Extra | Install | What it adds |
|-------|---------|--------------|
| `tui` | `uv sync --package isotope-agents --extra tui` | Interactive TUI (Rich + prompt-toolkit) |
| `mcp` | `uv sync --package isotope-agents --extra mcp` | MCP server integration |
| `all` | `uv sync --package isotope-agents --extra all` | Everything above |

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

Packages are published individually. `isotope-core` must be published before `isotope-agents` (since it depends on it).

```bash
# Build and publish isotope-core
uv build --package isotope-core
uv publish dist/isotope_core-*.tar.gz dist/isotope_core-*.whl

# Build and publish isotope-agents
uv build --package isotope-agents
uv publish dist/isotope_agents-*.tar.gz dist/isotope_agents-*.whl
```

Set your PyPI token via `UV_PUBLISH_TOKEN` or pass `--token` to `uv publish`.

## Configuration

Isotope reads configuration from `~/.isotope/config.yaml`. See the [isotope-agents README](packages/isotope-agents/README.md#configuration) for details.

## Documentation

- [isotope-core API](packages/isotope-core/README.md) — engine, providers, middleware, tools
- [isotope-agents guide](packages/isotope-agents/README.md) — CLI, tools, presets, RPC, sessions
- [Project Requirements](docs/PRD.md) — design goals and product requirements
- [Design Specs](docs/specs/) — milestone design documents

## Requirements

- Python 3.11+
- LLM provider access (OpenAI, Anthropic, or any OpenAI-compatible endpoint)

## License

MIT
