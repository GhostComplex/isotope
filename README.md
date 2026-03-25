# Isotope

A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.

## Packages

| Package | Location | Description |
|---|---|---|
| `isotope-core` | [`packages/isotope-core/`](packages/isotope-core/) | LLM providers, agent loop, middleware, events, context management |
| `isotope-agents` | [`packages/isotope-agents/`](packages/isotope-agents/) | Agent framework: tools, TUI, sessions, RPC, presets |

## Quick Start

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and set up
git clone https://github.com/GhostComplex/isotope.git
cd isotope
uv sync

# Run tests
uv run pytest packages/isotope-core/tests/

# Lint and type check
uv run ruff check packages/isotope-core/
uv run mypy packages/isotope-core/src/
```

## Architecture

Isotope is a mono-repo with two packages:

- **isotope-core** — the foundation. Provides the agent loop (plan → act → observe → repeat), LLM provider abstraction (OpenAI, Anthropic, proxy, router), middleware chain, typed event streaming, context management with pruning strategies, and a tool framework. Minimal dependencies (just Pydantic v2).

- **isotope-agents** — the framework. Built on isotope-core. Provides concrete tools (bash, read, write, edit, grep, glob), a TUI, session persistence, RPC protocol for embedding, preset configurations, and an extension system. This is what users install.

## Development

```bash
# Install all packages in development mode
uv pip install -e "packages/isotope-core[all]" -e "packages/isotope-agents"

# Run isotope-core tests
uv run pytest packages/isotope-core/tests/ -q

# Run with coverage
uv run pytest packages/isotope-core/tests/ --cov=isotope_core --cov-report=term-missing
```

## License

MIT
