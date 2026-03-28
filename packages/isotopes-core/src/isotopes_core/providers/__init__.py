"""Provider implementations for isotopes-core."""

from isotopes_core.providers.base import (
    Provider,
    StreamDoneEvent,
    StreamErrorEvent,
    StreamEvent,
    StreamStartEvent,
    StreamTextDeltaEvent,
    StreamTextEndEvent,
    StreamThinkingDeltaEvent,
    StreamThinkingEndEvent,
    StreamToolCallDeltaEvent,
    StreamToolCallEndEvent,
    StreamToolCallStartEvent,
)
from isotopes_core.providers.router import CircuitState, RouterProvider

# Import utilities (always available)
from isotopes_core.providers.utils import (
    RetryConfig,
    create_error_message,
    current_timestamp_ms,
    get_retry_after,
    is_retryable_error,
    map_error_to_stop_reason,
    retry_with_backoff,
)

__all__ = [
    # Base provider protocol and events
    "Provider",
    "StreamEvent",
    "StreamStartEvent",
    "StreamTextDeltaEvent",
    "StreamTextEndEvent",
    "StreamThinkingDeltaEvent",
    "StreamThinkingEndEvent",
    "StreamToolCallStartEvent",
    "StreamToolCallDeltaEvent",
    "StreamToolCallEndEvent",
    "StreamDoneEvent",
    "StreamErrorEvent",
    # Router
    "RouterProvider",
    "CircuitState",
    # Utilities
    "RetryConfig",
    "retry_with_backoff",
    "is_retryable_error",
    "get_retry_after",
    "map_error_to_stop_reason",
    "create_error_message",
    "current_timestamp_ms",
]

# Graceful imports for optional provider dependencies
# These will only be available if the corresponding SDK is installed

try:
    from isotopes_core.providers.openai import OpenAIProvider  # noqa: F401

    __all__.append("OpenAIProvider")
except ImportError:
    # openai SDK not installed
    pass

try:
    from isotopes_core.providers.anthropic import AnthropicProvider, ThinkingConfig  # noqa: F401

    __all__.extend(["AnthropicProvider", "ThinkingConfig"])
except ImportError:
    # anthropic SDK not installed
    pass

try:
    from isotopes_core.providers.proxy import ProxyProvider  # noqa: F401

    __all__.append("ProxyProvider")
except ImportError:
    # openai SDK not installed (ProxyProvider depends on it)
    pass
