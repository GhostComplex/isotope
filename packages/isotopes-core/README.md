# isotopes-core

Core primitives for building AI agent loops. Provides the engine that powers isotopes — a turn-based execution loop, LLM provider abstraction, middleware system, typed event streaming, context management, and a tool framework.

## Installation

### From PyPI

```bash
# uv
uv add isotopes-core
uv add 'isotopes-core[openai]'
uv add 'isotopes-core[anthropic]'
uv add 'isotopes-core[all]'

# pip
pip install isotopes-core              # core only (pydantic)
pip install isotopes-core[openai]      # + OpenAI provider
pip install isotopes-core[anthropic]   # + Anthropic provider
pip install isotopes-core[all]         # all providers + tiktoken
```

### From Source (monorepo)

```bash
# Sync just isotopes-core into the workspace environment
uv sync --package isotopes-core

# Include optional provider extras
uv sync --package isotopes-core --extra openai
uv sync --package isotopes-core --extra anthropic
uv sync --package isotopes-core --extra all
```

## API Overview

### Agent

The `Agent` class is the main entry point — it wraps the agent loop with state management, streaming, steering, follow-ups, and abort support.

```python
from isotopes_core import Agent

agent = Agent(
    provider=my_provider,
    system_prompt="You are a helpful assistant.",
    tools=[my_tool],
    max_turns=10,
)

async for event in agent.prompt("Hello!"):
    if event.type == "message_update":
        print(event.delta, end="")

# Inject steering mid-turn, queue follow-ups, or abort
agent.steer("Focus on error handling.")
agent.follow_up("Now write tests.")
agent.abort()
```

### Providers

Providers implement the `Provider` protocol and stream LLM responses as typed events.

```python
from isotopes_core.providers.proxy import ProxyProvider
from isotopes_core.providers.openai import OpenAIProvider
from isotopes_core.providers.anthropic import AnthropicProvider

# OpenAI-compatible proxy (LiteLLM, Ollama, vLLM, Azure, etc.)
proxy = ProxyProvider(model="gpt-4o", base_url="http://localhost:4141/v1")

# Direct OpenAI
openai = OpenAIProvider(model="gpt-4o", api_key="sk-...")

# Direct Anthropic (supports extended thinking)
anthropic = AnthropicProvider(model="claude-opus-4.6", api_key="sk-ant-...")
```

A `RouterProvider` adds multi-provider routing with automatic fallback and circuit breaker.

### @auto_tool Decorator

Define tools from plain async functions. The JSON schema is auto-generated from type hints and docstring.

```python
from isotopes_core import auto_tool

@auto_tool
async def grep(pattern: str, path: str = ".", max_results: int = 50) -> str:
    """Search file contents with a regex pattern.

    Args:
        pattern: The regex pattern to search for.
        path: Directory to search in.
        max_results: Maximum number of matches to return.
    """
    ...
```

Supported types: `str`, `int`, `float`, `bool`, `list[T]`, `T | None`. Parameters without defaults become required.

### Middleware

Composable middleware chain that intercepts events flowing through the agent loop.

```python
from isotopes_core import LoggingMiddleware, TokenTrackingMiddleware, EventFilterMiddleware

agent = Agent(
    provider=my_provider,
    middleware=[
        LoggingMiddleware(log_level="normal"),
        TokenTrackingMiddleware(),
        EventFilterMiddleware(exclude={"message_update"}),
    ],
)
```

### Context Management

- **FileTracker** — tracks file read/write operations across a session
- **SlidingWindowStrategy** — drops oldest messages when context exceeds a threshold
- **SummarizationStrategy** — summarizes old messages using the LLM
- **SelectivePruningStrategy** — removes specific message types
- **pin_message / unpin_message** — protect messages from pruning
- **count_tokens / estimate_context_usage** — token counting with optional tiktoken

### Loop Detection

The agent loop detects repetitive tool-call patterns by hashing consecutive tool names and arguments. When a loop is detected, a `LoopDetectedEvent` is emitted to prevent runaway execution.

## License

MIT
