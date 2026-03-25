"""Tests for loop detection in the agent loop."""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from isotope_core.loop import (
    AgentLoopConfig,
    LoopDetectionConfig,
    _check_loop_detection,
    _hash_tool_call,
    agent_loop,
)
from isotope_core.providers.base import (
    StreamDoneEvent,
    StreamEvent,
    StreamStartEvent,
    StreamTextDeltaEvent,
)
from isotope_core.tools import Tool, ToolResult
from isotope_core.types import (
    AssistantMessage,
    Context,
    LoopDetectedEvent,
    SteerEvent,
    StopReason,
    TextContent,
    ToolCallContent,
    UserMessage,
)

# =============================================================================
# Mock Provider for Testing
# =============================================================================


class MockProvider:
    """A mock provider for testing loop detection."""

    def __init__(self, responses: list[AssistantMessage]) -> None:
        """Initialize with a list of responses to return."""
        self.responses = responses
        self.call_count = 0
        self.last_context: Context | None = None

    async def stream(
        self,
        context: Context,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream a response from the mock provider."""
        self.last_context = context

        if self.call_count >= len(self.responses):
            # Return an end_turn response if we run out
            msg = AssistantMessage(
                content=[TextContent(text="Done")],
                stop_reason=StopReason.END_TURN,
                timestamp=int(time.time() * 1000),
            )
            yield StreamStartEvent(partial=msg)
            yield StreamDoneEvent(message=msg)
            return

        msg = self.responses[self.call_count]
        self.call_count += 1

        # Check for abort
        if signal and signal.is_set():
            error_msg = AssistantMessage(
                content=[],
                stop_reason=StopReason.ABORTED,
                error_message="Aborted",
                timestamp=int(time.time() * 1000),
            )
            yield StreamStartEvent(partial=error_msg)
            yield StreamDoneEvent(message=error_msg)
            return

        # Yield start event
        yield StreamStartEvent(partial=msg)

        # Yield deltas for text content
        for content in msg.content:
            if isinstance(content, TextContent):
                yield StreamTextDeltaEvent(
                    content_index=0,
                    delta=content.text,
                    partial=msg,
                )

        # Yield done event
        yield StreamDoneEvent(message=msg)


# =============================================================================
# Mock Tool for Testing
# =============================================================================


class MockTool(Tool):
    """A mock tool that always returns the same result."""

    def __init__(self, name: str, result: str = "Tool executed successfully") -> None:
        """Initialize the mock tool."""
        self.execution_count = 0
        self.result = result

        async def execute(
            tool_call_id: str,
            params: dict[str, Any],
            signal: asyncio.Event | None = None,
            on_update: Any = None,
        ) -> ToolResult:
            self.execution_count += 1
            return ToolResult.text(f"{self.result} (call #{self.execution_count})")

        super().__init__(
            name=name,
            description=f"Mock {name} tool for testing",
            parameters={
                "type": "object",
                "properties": {
                    "param": {
                        "type": "string",
                        "description": "A parameter",
                    }
                },
                "required": [],
            },
            execute=execute,
        )


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def loop_detection_config() -> LoopDetectionConfig:
    """Create a default loop detection config."""
    return LoopDetectionConfig()


@pytest.fixture
def custom_loop_detection_config() -> LoopDetectionConfig:
    """Create a custom loop detection config with different thresholds."""
    return LoopDetectionConfig(
        same_call_threshold=2,
        same_tool_threshold=3,
        enabled=True
    )


@pytest.fixture
def disabled_loop_detection_config() -> LoopDetectionConfig:
    """Create a disabled loop detection config."""
    return LoopDetectionConfig(enabled=False)


@pytest.fixture
def mock_tool() -> MockTool:
    """Create a mock tool."""
    return MockTool("test_tool")


@pytest.fixture
def another_mock_tool() -> MockTool:
    """Create another mock tool."""
    return MockTool("another_tool", "Another tool executed")


# =============================================================================
# Unit Tests for Helper Functions
# =============================================================================


def test_hash_tool_call():
    """Test that tool call hashing works correctly."""
    # Same tool and args should produce same hash
    hash1 = _hash_tool_call("test_tool", {"param": "value"})
    hash2 = _hash_tool_call("test_tool", {"param": "value"})
    assert hash1 == hash2

    # Different tools should produce different hashes
    hash3 = _hash_tool_call("other_tool", {"param": "value"})
    assert hash1 != hash3

    # Different args should produce different hashes
    hash4 = _hash_tool_call("test_tool", {"param": "different_value"})
    assert hash1 != hash4

    # Args order shouldn't matter
    hash5 = _hash_tool_call("test_tool", {"b": "2", "a": "1"})
    hash6 = _hash_tool_call("test_tool", {"a": "1", "b": "2"})
    assert hash5 == hash6


def test_check_loop_detection_disabled():
    """Test that loop detection doesn't trigger when disabled."""
    config = LoopDetectionConfig(enabled=False)
    history = [("tool1", "hash1")] * 10

    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert not should_steer
    assert message is None
    assert not should_emit


def test_check_loop_detection_empty_history():
    """Test that loop detection doesn't trigger with empty history."""
    config = LoopDetectionConfig()
    history: list[tuple[str, str]] = []

    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert not should_steer
    assert message is None
    assert not should_emit


def test_check_loop_detection_same_call_threshold():
    """Test that same call threshold triggers steering."""
    config = LoopDetectionConfig(same_call_threshold=3)

    # Should not trigger with 2 identical calls
    history = [("tool1", "hash1")] * 2
    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert not should_steer
    assert message is None
    assert not should_emit

    # Should trigger with 3 identical calls
    history = [("tool1", "hash1")] * 3
    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert should_steer
    assert message is not None
    assert "repeating the same action" in message
    assert "tool1" in message
    assert not should_emit


def test_check_loop_detection_same_tool_threshold():
    """Test that same tool threshold triggers event emission."""
    config = LoopDetectionConfig(same_tool_threshold=3)

    # Should not trigger with 2 calls to same tool
    history = [("tool1", "hash1"), ("tool1", "hash2")]
    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert not should_steer
    assert message is None
    assert not should_emit

    # Should trigger with 3 calls to same tool (different args)
    history = [("tool1", "hash1"), ("tool1", "hash2"), ("tool1", "hash3")]
    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert not should_steer
    assert message is None
    assert should_emit


def test_check_loop_detection_mixed_calls():
    """Test that loop detection works with mixed tool calls."""
    config = LoopDetectionConfig(same_call_threshold=3, same_tool_threshold=3)

    # Mixed calls should not trigger
    history = [
        ("tool1", "hash1"),
        ("tool2", "hash2"),
        ("tool1", "hash3"),
        ("tool2", "hash4")
    ]
    should_steer, message, should_emit = _check_loop_detection(history, config)
    assert not should_steer
    assert message is None
    assert not should_emit


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_loop_detection_same_call_steering(mock_tool: MockTool):
    """Test that same call loop detection triggers steering injection."""
    # Create multiple responses with identical tool calls
    responses = [
        AssistantMessage(
            content=[
                ToolCallContent(
                    id=f"call_{i}",
                    name="test_tool",
                    arguments={"param": "same_value"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        )
        for i in range(5)  # More responses to be safe
    ]

    provider = MockProvider(responses)
    steering_queue = asyncio.Queue[UserMessage]()

    config = AgentLoopConfig(
        provider=provider,
        tools=[mock_tool],
        steering_queue=steering_queue,
        loop_detection=LoopDetectionConfig(same_call_threshold=3)
    )

    context = Context()
    prompts = [UserMessage(
        content=[TextContent(text="Please use the tool")],
        timestamp=int(time.time() * 1000)
    )]

    events = []
    steer_found = False
    async for event in agent_loop(prompts, context, config):
        events.append(event)
        # Check if we found a steering event
        if isinstance(event, SteerEvent):
            steer_found = True
            # Check the steering message content
            assert "repeating the same action" in event.message.content[0].text
            assert "test_tool" in event.message.content[0].text
            break
        # Prevent infinite loop
        if len(events) > 50:
            break

    # Check that a SteerEvent was emitted (should have been found above)
    assert steer_found, (
        f"Expected SteerEvent, got {len(events)} events"
    )

    # Check that at least one SteerEvent was emitted
    steer_events = [e for e in events if isinstance(e, SteerEvent)]
    assert len(steer_events) > 0


@pytest.mark.asyncio
async def test_loop_detection_same_tool_event(mock_tool: MockTool):
    """Test that same tool loop detection triggers LoopDetectedEvent."""
    # Create responses with different arguments but same tool
    responses = [
        AssistantMessage(
            content=[
                ToolCallContent(
                    id=f"call_{i}",
                    name="test_tool",
                    arguments={"param": f"value_{i}"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        )
        for i in range(5)
    ]

    provider = MockProvider(responses)

    config = AgentLoopConfig(
        provider=provider,
        tools=[mock_tool],
        loop_detection=LoopDetectionConfig(same_tool_threshold=5)
    )

    context = Context()
    prompts = [UserMessage(
        content=[TextContent(text="Please use the tool")],
        timestamp=int(time.time() * 1000)
    )]

    events = []
    loop_found = False
    async for event in agent_loop(prompts, context, config):
        events.append(event)
        # Check if we found a loop detected event
        if isinstance(event, LoopDetectedEvent):
            loop_found = True
            assert event.tool_name == "test_tool"
            assert event.count == 5
            assert "test_tool" in event.message
            assert "5 times" in event.message
            break
        # Stop after we get enough events
        if len(events) > 50:
            break

    # Check that LoopDetectedEvent was emitted
    assert loop_found, (
        f"Expected LoopDetectedEvent, got {len(events)} events"
    )

    loop_events = [e for e in events if isinstance(e, LoopDetectedEvent)]
    assert len(loop_events) > 0


@pytest.mark.asyncio
async def test_loop_detection_disabled(mock_tool: MockTool):
    """Test that loop detection can be disabled."""
    # Create responses with identical tool calls
    responses = [
        AssistantMessage(
            content=[
                ToolCallContent(
                    id=f"call_{i}",
                    name="test_tool",
                    arguments={"param": "same_value"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        )
        for i in range(5)
    ]

    provider = MockProvider(responses)
    steering_queue = asyncio.Queue[UserMessage]()

    config = AgentLoopConfig(
        provider=provider,
        tools=[mock_tool],
        steering_queue=steering_queue,
        loop_detection=LoopDetectionConfig(enabled=False)
    )

    context = Context()
    prompts = [UserMessage(
        content=[TextContent(text="Please use the tool")],
        timestamp=int(time.time() * 1000)
    )]

    events = []
    async for event in agent_loop(prompts, context, config):
        events.append(event)
        # Stop after some events to avoid infinite loop
        if len(events) > 20:
            break

    # Check that no steering message was injected
    assert steering_queue.empty()

    # Check that no LoopDetectedEvent was emitted
    loop_events = [e for e in events if isinstance(e, LoopDetectedEvent)]
    assert len(loop_events) == 0


@pytest.mark.asyncio
async def test_loop_detection_no_repetition(mock_tool: MockTool, another_mock_tool: MockTool):
    """Test that non-repeating calls don't trigger loop detection."""
    # Create responses with different tools
    responses = [
        AssistantMessage(
            content=[
                ToolCallContent(
                    id="call_1",
                    name="test_tool",
                    arguments={"param": "value1"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        ),
        AssistantMessage(
            content=[
                ToolCallContent(
                    id="call_2",
                    name="another_tool",
                    arguments={"param": "value2"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        ),
        AssistantMessage(
            content=[TextContent(text="Done")],
            stop_reason=StopReason.END_TURN,
            timestamp=int(time.time() * 1000),
        )
    ]

    provider = MockProvider(responses)
    steering_queue = asyncio.Queue[UserMessage]()

    config = AgentLoopConfig(
        provider=provider,
        tools=[mock_tool, another_mock_tool],
        steering_queue=steering_queue,
        loop_detection=LoopDetectionConfig()
    )

    context = Context()
    prompts = [UserMessage(
        content=[TextContent(text="Please use the tools")],
        timestamp=int(time.time() * 1000)
    )]

    events = []
    async for event in agent_loop(prompts, context, config):
        events.append(event)

    # Check that no steering message was injected
    assert steering_queue.empty()

    # Check that no LoopDetectedEvent was emitted
    loop_events = [e for e in events if isinstance(e, LoopDetectedEvent)]
    assert len(loop_events) == 0


@pytest.mark.asyncio
async def test_loop_detection_threshold_customization(mock_tool: MockTool):
    """Test that loop detection thresholds can be customized."""
    # Create responses with identical tool calls
    responses = [
        AssistantMessage(
            content=[
                ToolCallContent(
                    id=f"call_{i}",
                    name="test_tool",
                    arguments={"param": "same_value"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        )
        for i in range(3)  # Need at least 3 for steering to trigger
    ]

    provider = MockProvider(responses)
    steering_queue = asyncio.Queue[UserMessage]()

    # Use custom thresholds (lower than default)
    # Set same_call_threshold to 3 and same_tool_threshold to 2
    # This way the same_tool threshold will trigger first (at 2 identical calls)
    config = AgentLoopConfig(
        provider=provider,
        tools=[mock_tool],
        steering_queue=steering_queue,
        loop_detection=LoopDetectionConfig(
            same_call_threshold=3,  # Higher threshold for steering
            same_tool_threshold=2   # Lower threshold for event
        )
    )

    context = Context()
    prompts = [UserMessage(
        content=[TextContent(text="Please use the tool")],
        timestamp=int(time.time() * 1000)
    )]

    events = []
    loop_found = False

    async for event in agent_loop(prompts, context, config):
        events.append(event)

        # Check for loop detected event
        if isinstance(event, LoopDetectedEvent) and not loop_found:
            loop_found = True
            assert event.count == 2  # Should trigger at 2 calls
            break

        # Prevent infinite loop
        if len(events) > 30:
            break

    # Check that LoopDetectedEvent was emitted with custom threshold
    assert loop_found, (
        f"Expected LoopDetectedEvent, got {len(events)} events"
    )

    # Now test the steering threshold separately with a different set of calls
    responses2 = [
        AssistantMessage(
            content=[
                ToolCallContent(
                    id=f"call2_{i}",
                    name="test_tool",
                    arguments={"param": "same_value"}
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            timestamp=int(time.time() * 1000),
        )
        for i in range(3)  # Exactly 3 to trigger steering
    ]

    provider2 = MockProvider(responses2)
    steering_queue2 = asyncio.Queue[UserMessage]()

    config2 = AgentLoopConfig(
        provider=provider2,
        tools=[mock_tool],
        steering_queue=steering_queue2,
        loop_detection=LoopDetectionConfig(
            same_call_threshold=2,  # Lower threshold for steering
            same_tool_threshold=5   # Higher threshold to not interfere
        )
    )

    context2 = Context()
    events2 = []
    steer_found = False

    async for event in agent_loop(prompts, context2, config2):
        events2.append(event)

        # Check for steering event
        if isinstance(event, SteerEvent) and not steer_found:
            steer_found = True
            assert "repeating the same action" in event.message.content[0].text
            break

        # Prevent infinite loop
        if len(events2) > 30:
            break

    # Check that steering was triggered with custom threshold
    assert steer_found, (
        f"Expected SteerEvent, got {len(events2)} events"
    )