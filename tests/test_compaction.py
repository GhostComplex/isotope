"""Tests for the context compaction engine."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from isotope_core.types import (
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)

from isotope_agents.compaction import Compactor


@pytest.fixture
def compactor():
    """Create a Compactor instance for testing."""
    return Compactor(max_context_tokens=1000, preserve_recent=3)


@pytest.fixture
def sample_messages():
    """Create sample messages for testing."""
    timestamp = int(time.time())
    return [
        UserMessage(
            content=[TextContent(text="Hello, can you help me with Python?")],
            timestamp=timestamp,
        ),
        AssistantMessage(
            content=[TextContent(text="Of course! I'd be happy to help with Python.")],
            usage=Usage(input_tokens=10, output_tokens=15),
            timestamp=timestamp + 1,
        ),
        UserMessage(
            content=[TextContent(text="How do I create a list?")],
            timestamp=timestamp + 2,
        ),
        AssistantMessage(
            content=[TextContent(text="You can create a list using square brackets: my_list = [1, 2, 3]")],
            usage=Usage(input_tokens=20, output_tokens=25),
            timestamp=timestamp + 3,
        ),
        UserMessage(
            content=[TextContent(text="What about dictionaries?")],
            timestamp=timestamp + 4,
        ),
        AssistantMessage(
            content=[TextContent(text="Dictionaries use curly braces: my_dict = {'key': 'value'}")],
            usage=Usage(input_tokens=15, output_tokens=20),
            timestamp=timestamp + 5,
        ),
    ]


@pytest.fixture
def large_messages():
    """Create a large set of messages that should trigger compaction."""
    messages = []
    timestamp = int(time.time())

    # Create enough messages with enough content to exceed token threshold
    for i in range(20):
        # Large user message
        long_text = f"This is message number {i}. " + "A" * 500  # ~500 chars
        messages.append(UserMessage(
            content=[TextContent(text=long_text)],
            timestamp=timestamp + i * 2,
        ))

        # Large assistant response
        long_response = f"Response to message {i}. " + "B" * 500  # ~500 chars
        messages.append(AssistantMessage(
            content=[TextContent(text=long_response)],
            usage=Usage(input_tokens=100, output_tokens=100),
            timestamp=timestamp + i * 2 + 1,
        ))

    return messages


@pytest.fixture
def mock_provider():
    """Create a mock LLM provider for testing."""
    mock = AsyncMock()

    # Mock the complete method to return a summary
    mock_response = Mock()
    mock_response.content = [
        TextContent(text="Summary of previous conversation about Python basics including lists and dictionaries.")
    ]
    mock.complete.return_value = mock_response

    return mock


class TestCompactor:
    """Test cases for the Compactor class."""

    def test_initialization(self):
        """Test Compactor initialization with default and custom parameters."""
        # Default initialization
        compactor = Compactor()
        assert compactor.max_context_tokens == 100000
        assert compactor.preserve_recent == 10

        # Custom initialization
        compactor = Compactor(max_context_tokens=5000, preserve_recent=5)
        assert compactor.max_context_tokens == 5000
        assert compactor.preserve_recent == 5

    def test_count_tokens_empty_messages(self, compactor):
        """Test token counting with empty message list."""
        assert compactor._count_tokens([]) == 0

    def test_count_tokens_single_message(self, compactor):
        """Test token counting with a single message."""
        message = UserMessage(
            content=[TextContent(text="Hello world")],  # 11 chars
            timestamp=int(time.time()),
        )
        # Expected: (11 + 50 overhead) // 4 = 15 tokens
        assert compactor._count_tokens([message]) == 15

    def test_count_tokens_multiple_messages(self, compactor, sample_messages):
        """Test token counting with multiple messages."""
        token_count = compactor._count_tokens(sample_messages)
        # Should return a reasonable token count
        assert token_count > 0
        assert isinstance(token_count, int)

    def test_count_message_chars_text_content(self, compactor):
        """Test character counting for text content."""
        message = UserMessage(
            content=[TextContent(text="Hello world")],  # 11 chars
            timestamp=int(time.time()),
        )
        # Expected: 11 + 50 overhead = 61
        assert compactor._count_message_chars(message) == 61

    def test_count_message_chars_thinking_content(self, compactor):
        """Test character counting for thinking content."""
        message = AssistantMessage(
            content=[ThinkingContent(thinking="I need to think about this")],  # 26 chars
            usage=Usage(input_tokens=10, output_tokens=10),
            timestamp=int(time.time()),
        )
        # Expected: 26 + 50 overhead = 76
        assert compactor._count_message_chars(message) == 76

    def test_count_message_chars_tool_call_content(self, compactor):
        """Test character counting for tool call content."""
        message = AssistantMessage(
            content=[ToolCallContent(
                id="call_1",
                name="test_tool",  # 9 chars
                arguments={"key": "value"}  # JSON: {"key": "value"} = 16 chars
            )],
            usage=Usage(input_tokens=10, output_tokens=10),
            timestamp=int(time.time()),
        )
        # Expected: 9 + 16 + 50 overhead = 75
        assert compactor._count_message_chars(message) == 75

    def test_count_message_chars_multiple_content(self, compactor):
        """Test character counting for messages with multiple content blocks."""
        message = UserMessage(
            content=[
                TextContent(text="Hello"),  # 5 chars
                TextContent(text="world"),  # 5 chars
            ],
            timestamp=int(time.time()),
        )
        # Expected: 5 + 5 + 50 overhead = 60
        assert compactor._count_message_chars(message) == 60

    def test_should_compact_false_few_messages(self, compactor, sample_messages):
        """Test should_compact returns False when there are few messages."""
        # Only 6 messages, preserve_recent is 3, so no compaction needed
        compactor.preserve_recent = 10  # More than number of messages
        assert not compactor.should_compact(sample_messages)

    def test_should_compact_false_under_threshold(self, compactor, sample_messages):
        """Test should_compact returns False when under token threshold."""
        compactor.max_context_tokens = 999999  # Very high threshold
        assert not compactor.should_compact(sample_messages)

    def test_should_compact_true_over_threshold(self, compactor, large_messages):
        """Test should_compact returns True when over token threshold."""
        compactor.max_context_tokens = 100  # Very low threshold
        assert compactor.should_compact(large_messages)

    def test_should_compact_with_override_threshold(self, compactor, large_messages):
        """Test should_compact with override max_tokens parameter."""
        # Default threshold would not trigger compaction
        compactor.max_context_tokens = 999999

        # But override threshold should trigger it
        assert compactor.should_compact(large_messages, max_tokens=100)

    def test_should_compact_empty_messages(self, compactor):
        """Test should_compact with empty message list."""
        assert not compactor.should_compact([])

    def test_messages_to_text_conversion(self, compactor, sample_messages):
        """Test conversion of messages to text format."""
        text = compactor._messages_to_text(sample_messages)

        # Check that all message types are represented
        assert "User: Hello, can you help me with Python?" in text
        assert "Assistant: Of course! I'd be happy to help with Python." in text
        assert "User: How do I create a list?" in text
        assert "Assistant: You can create a list using square brackets" in text

    def test_messages_to_text_with_tool_messages(self, compactor):
        """Test message to text conversion with tool messages."""
        messages = [
            AssistantMessage(
                content=[ToolCallContent(
                    id="call_1",
                    name="test_tool",
                    arguments={"input": "test"}
                )],
                usage=Usage(input_tokens=10, output_tokens=10),
                timestamp=int(time.time()),
            ),
            ToolResultMessage(
                tool_call_id="call_1",
                tool_name="test_tool",
                content=[TextContent(text="Tool result")],
                timestamp=int(time.time()),
            ),
        ]

        text = compactor._messages_to_text(messages)
        assert '[Tool Call] test_tool({"input": "test"})' in text
        assert "Tool(test_tool): Tool result" in text

    def test_messages_to_text_with_thinking(self, compactor):
        """Test message to text conversion with thinking content."""
        messages = [
            AssistantMessage(
                content=[
                    ThinkingContent(thinking="Let me think about this"),
                    TextContent(text="Here's my response"),
                ],
                usage=Usage(input_tokens=10, output_tokens=10),
                timestamp=int(time.time()),
            ),
        ]

        text = compactor._messages_to_text(messages)
        assert "[Thinking] Let me think about this" in text
        assert "Here's my response" in text

    def test_fallback_summary_basic(self, compactor, sample_messages):
        """Test fallback summary generation."""
        summary = compactor._fallback_summary(sample_messages)

        assert "3 user messages" in summary
        assert "3 assistant messages" in summary
        assert "0 tool results" in summary
        assert "Hello, can you help me with Python?" in summary

    def test_fallback_summary_with_long_first_message(self, compactor):
        """Test fallback summary with a very long first message."""
        long_text = "A" * 200  # Very long message
        messages = [
            UserMessage(
                content=[TextContent(text=long_text)],
                timestamp=int(time.time()),
            ),
        ]

        summary = compactor._fallback_summary(messages)

        # Should truncate long first message
        assert "A" * 97 + "..." in summary

    def test_fallback_summary_empty_messages(self, compactor):
        """Test fallback summary with empty message list."""
        summary = compactor._fallback_summary([])

        assert "0 user messages" in summary
        assert "0 assistant messages" in summary
        assert "general conversation" in summary

    @pytest.mark.asyncio
    async def test_compact_few_messages(self, compactor, sample_messages, mock_provider):
        """Test compact with fewer messages than preserve_recent."""
        # Set preserve_recent higher than number of messages
        compactor.preserve_recent = 10

        result = await compactor.compact(sample_messages, mock_provider)

        # Should return original messages unchanged
        assert result == sample_messages
        # Should not call the provider
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_compact_no_old_messages(self, compactor, sample_messages, mock_provider):
        """Test compact when all messages are recent."""
        # Set preserve_recent equal to number of messages
        compactor.preserve_recent = 6

        result = await compactor.compact(sample_messages, mock_provider)

        # Should return original messages unchanged
        assert result == sample_messages
        # Should not call the provider
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_compact_successful(self, compactor, large_messages, mock_provider):
        """Test successful compaction with summary generation."""
        original_count = len(large_messages)

        result = await compactor.compact(large_messages, mock_provider)

        # Should have fewer messages than original
        assert len(result) < original_count

        # Should have exactly preserve_recent + 1 (summary) messages
        assert len(result) == compactor.preserve_recent + 1

        # First message should be the summary
        assert isinstance(result[0], UserMessage)
        assert result[0].content[0].text.startswith("[CONTEXT SUMMARY]")
        assert result[0].pinned is True

        # Remaining messages should be the most recent ones
        expected_recent = large_messages[-compactor.preserve_recent:]
        assert result[1:] == expected_recent

        # Provider should have been called for summarization
        mock_provider.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_compact_provider_failure(self, compactor, large_messages):
        """Test compact behavior when LLM provider fails."""
        # Create a mock provider that raises an exception
        failing_provider = AsyncMock()
        failing_provider.complete.side_effect = Exception("API Error")

        with patch('builtins.print'):  # Suppress warning print
            result = await compactor.compact(large_messages, failing_provider)

        # Should still return compacted messages with fallback summary
        assert len(result) == compactor.preserve_recent + 1
        assert isinstance(result[0], UserMessage)
        assert result[0].content[0].text.startswith("[CONTEXT SUMMARY]")

        # Summary should contain fallback text
        summary_text = result[0].content[0].text
        assert "Previous conversation with" in summary_text

    @pytest.mark.asyncio
    async def test_compact_provider_no_text_content(self, compactor, large_messages):
        """Test compact when provider returns response without text content."""
        # Create a mock provider that returns non-text content
        mock_provider = AsyncMock()
        mock_response = Mock()
        mock_response.content = [ToolCallContent(id="test", name="test", arguments={})]
        mock_provider.complete.return_value = mock_response

        result = await compactor.compact(large_messages, mock_provider)

        # Should use fallback summary
        summary_text = result[0].content[0].text
        assert "Previous conversation with" in summary_text

    @pytest.mark.asyncio
    async def test_compact_provider_empty_content(self, compactor, large_messages):
        """Test compact when provider returns response with empty content."""
        # Create a mock provider that returns empty content
        mock_provider = AsyncMock()
        mock_response = Mock()
        mock_response.content = []
        mock_provider.complete.return_value = mock_response

        result = await compactor.compact(large_messages, mock_provider)

        # Should use fallback summary
        summary_text = result[0].content[0].text
        assert "Previous conversation with" in summary_text

    @pytest.mark.asyncio
    async def test_summarize_messages_successful(self, compactor, sample_messages, mock_provider):
        """Test successful message summarization."""
        summary = await compactor._summarize_messages(sample_messages, mock_provider)

        expected_summary = "Summary of previous conversation about Python basics including lists and dictionaries."
        assert summary == expected_summary

        # Verify the provider was called with correct parameters
        mock_provider.complete.assert_called_once()
        call_args = mock_provider.complete.call_args

        # Check that system prompt mentions summarization
        assert "summarizer" in call_args.kwargs['system_prompt'].lower()

        # Check that max_tokens is set for summary length
        assert call_args.kwargs['max_tokens'] == 1000

    @pytest.mark.asyncio
    async def test_end_to_end_compaction_flow(self, mock_provider):
        """Test complete end-to-end compaction flow."""
        # Create compactor with small thresholds for testing
        compactor = Compactor(max_context_tokens=150, preserve_recent=2)

        # Create messages that exceed threshold
        messages = []
        for i in range(5):
            long_text = "A" * 100  # 100 characters each
            messages.append(UserMessage(
                content=[TextContent(text=f"Message {i}: {long_text}")],
                timestamp=int(time.time()) + i,
            ))

        # Test that compaction is needed
        assert compactor.should_compact(messages)

        # Perform compaction
        result = await compactor.compact(messages, mock_provider)

        # Verify results
        assert len(result) == 3  # 1 summary + 2 preserved
        assert "[CONTEXT SUMMARY]" in result[0].content[0].text
        assert result[1] == messages[3]  # Second-to-last original message
        assert result[2] == messages[4]  # Last original message

        # After compaction, should not need further compaction (with higher threshold)
        compactor_check = Compactor(max_context_tokens=500, preserve_recent=2)
        assert not compactor_check.should_compact(result)


class TestCompactorEdgeCases:
    """Test edge cases and error conditions for the Compactor."""

    def test_compactor_with_zero_preserve_recent(self):
        """Test compactor behavior with zero preserve_recent."""
        compactor = Compactor(preserve_recent=0)
        messages = [
            UserMessage(content=[TextContent(text="test")], timestamp=int(time.time()))
        ]

        # Should still work, but preserve nothing
        assert not compactor.should_compact(messages)

    def test_compactor_with_zero_max_tokens(self):
        """Test compactor behavior with zero max_tokens."""
        compactor = Compactor(max_context_tokens=0, preserve_recent=0)
        messages = [
            UserMessage(content=[TextContent(text="test")], timestamp=int(time.time()))
        ]

        # Should need compaction with 0 threshold and 0 preserve_recent
        assert compactor.should_compact(messages)

    @pytest.mark.asyncio
    async def test_compact_empty_message_list(self, mock_provider):
        """Test compaction with empty message list."""
        compactor = Compactor()

        result = await compactor.compact([], mock_provider)

        assert result == []
        mock_provider.complete.assert_not_called()

    def test_message_chars_with_none_content(self, compactor):
        """Test character counting with message containing None content."""
        # Create a message without content attribute (edge case)
        message = ToolResultMessage(
            tool_call_id="test",
            tool_name="test",
            content=[],  # Empty content
            timestamp=int(time.time()),
        )

        # Should just return overhead
        assert compactor._count_message_chars(message) == 50

    def test_messages_to_text_with_empty_content(self, compactor):
        """Test message to text conversion with messages containing empty content."""
        messages = [
            UserMessage(content=[], timestamp=int(time.time())),
            AssistantMessage(
                content=[],
                usage=Usage(input_tokens=0, output_tokens=0),
                timestamp=int(time.time()),
            ),
        ]

        text = compactor._messages_to_text(messages)

        # Should handle empty content gracefully
        lines = [line for line in text.split('\n') if line.strip()]
        assert len(lines) == 0  # No content to display