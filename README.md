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
# Install with all extras
pip install isotope-agents[all]

# Launch interactive chat
isotope chat

# Run a one-shot prompt
isotope run "Explain this codebase"

# Start RPC server for embedding
isotope rpc
```

## Development

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and set up
git clone https://github.com/GhostComplex/isotope.git
cd isotope
uv sync

# Run all tests
uv run pytest packages/isotope-core/tests/ -q
uv run pytest packages/isotope-agents/tests/ -q

# Lint
uv run ruff check packages/

# Type check
uv run mypy packages/isotope-core/src/
```

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
