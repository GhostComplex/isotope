"""Tests for the compaction engine."""

from __future__ import annotations

import asyncio
import time

import pytest

from isotope_agents.compaction import (
    CompactionResult,
    _estimate_messages_tokens,
    _estimate_tokens,
    _serialize_messages,
    compact_messages,
)
from isotope_core.context import FileTracker
from isotope_core.providers.base import StreamDoneEvent
from isotope_core.types import (
    AssistantMessage,
    Context,
    Message,
    StopReason,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)


# =============================================================================
# Helpers
# =============================================================================


def _ts() -> int:
    """Return a millisecond timestamp for test messages."""
    return int(time.time() * 1000)


def _user(text: str) -> UserMessage:
    return UserMessage(content=[TextContent(text=text)], timestamp=_ts())


def _assistant(text: str) -> AssistantMessage:
    return AssistantMessage(
        content=[TextContent(text=text)],
        stop_reason=StopReason.END_TURN,
        usage=Usage(input_tokens=10, output_tokens=5),
        timestamp=_ts(),
    )


def _tool_result(tool_call_id: str, name: str, text: str) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id=tool_call_id,
        tool_name=name,
        content=[TextContent(text=text)],
        timestamp=_ts(),
    )


class MockProvider:
    """A mock Provider that returns a fixed summary text via stream()."""

    def __init__(self, summary_text: str = "This is a summary.") -> None:
        self._summary_text = summary_text

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def provider_name(self) -> str:
        return "mock"

    async def stream(
        self,
        context: Context,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
    ):  # type: ignore[override]
        """Yield a single StreamDoneEvent with the summary."""
        message = AssistantMessage(
            content=[TextContent(text=self._summary_text)],
            stop_reason=StopReason.END_TURN,
            usage=Usage(input_tokens=100, output_tokens=50),
            timestamp=_ts(),
        )
        yield StreamDoneEvent(message=message)


# =============================================================================
# CompactionResult tests
# =============================================================================


class TestCompactionResult:
    """Tests for the CompactionResult dataclass."""

    def test_default_fields(self) -> None:
        """CompactionResult has correct defaults."""
        result = CompactionResult(summary="test")
        assert result.summary == "test"
        assert result.files_read == []
        assert result.files_modified == []
        assert result.messages_compacted == 0
        assert result.tokens_before == 0
        assert result.tokens_after == 0

    def test_all_fields(self) -> None:
        """CompactionResult stores all provided fields."""
        result = CompactionResult(
            summary="summary",
            files_read=["a.py", "b.py"],
            files_modified=["c.py"],
            messages_compacted=5,
            tokens_before=1000,
            tokens_after=200,
        )
        assert result.summary == "summary"
        assert result.files_read == ["a.py", "b.py"]
        assert result.files_modified == ["c.py"]
        assert result.messages_compacted == 5
        assert result.tokens_before == 1000
        assert result.tokens_after == 200


# =============================================================================
# compact_messages tests
# =============================================================================


class TestCompactMessages:
    """Tests for the compact_messages function."""

    @pytest.mark.asyncio
    async def test_empty_messages(self) -> None:
        """Empty message list returns empty result with file tracker snapshot."""
        provider = MockProvider()
        tracker = FileTracker()
        tracker.record_read("README.md")

        result = await compact_messages([], provider, tracker)

        assert result.summary == ""
        assert result.messages_compacted == 0
        assert result.tokens_before == 0
        assert result.tokens_after == 0
        assert result.files_read == ["README.md"]

    @pytest.mark.asyncio
    async def test_fewer_than_keep_last_n(self) -> None:
        """When messages <= keep_last_n, nothing is compacted."""
        provider = MockProvider()
        tracker = FileTracker()
        messages = [_user("hello"), _assistant("hi")]

        result = await compact_messages(messages, provider, tracker, keep_last_n=4)

        assert result.summary == ""
        assert result.messages_compacted == 0
        assert result.tokens_before == result.tokens_after
        assert result.tokens_before > 0

    @pytest.mark.asyncio
    async def test_exactly_keep_last_n(self) -> None:
        """When messages == keep_last_n, nothing is compacted."""
        provider = MockProvider()
        tracker = FileTracker()
        messages = [_user("a"), _assistant("b"), _user("c"), _assistant("d")]

        result = await compact_messages(messages, provider, tracker, keep_last_n=4)

        assert result.summary == ""
        assert result.messages_compacted == 0

    @pytest.mark.asyncio
    async def test_compaction_with_mock_provider(self) -> None:
        """Compaction calls the provider and returns a summary."""
        summary_text = "User asked to refactor auth. Files were modified."
        provider = MockProvider(summary_text=summary_text)
        tracker = FileTracker()
        tracker.record_read("auth.py")
        tracker.record_write("auth.py")
        tracker.record_read("tests/test_auth.py")

        messages = [
            _user("Please refactor the auth module"),
            _assistant("I'll look at auth.py first"),
            _user("Good, go ahead"),
            _assistant("Done refactoring"),
            _user("Can you also add tests?"),
            _assistant("Sure, adding tests now"),
        ]

        result = await compact_messages(messages, provider, tracker, keep_last_n=2)

        assert result.summary == summary_text
        assert result.messages_compacted == 4  # 6 - 2 kept
        assert "auth.py" in result.files_read
        assert "auth.py" in result.files_modified
        assert "tests/test_auth.py" in result.files_read
        assert result.tokens_before > 0
        assert result.tokens_after > 0
        assert result.tokens_after < result.tokens_before

    @pytest.mark.asyncio
    async def test_keep_last_n_preserves_recent_messages(self) -> None:
        """The last N messages are preserved; only older ones get compacted."""
        provider = MockProvider(summary_text="Summarized old stuff.")
        tracker = FileTracker()

        old_msg1 = _user("old message 1")
        old_msg2 = _assistant("old response 1")
        recent_msg1 = _user("recent question")
        recent_msg2 = _assistant("recent answer")

        messages = [old_msg1, old_msg2, recent_msg1, recent_msg2]

        result = await compact_messages(messages, provider, tracker, keep_last_n=2)

        # 2 old messages compacted
        assert result.messages_compacted == 2
        assert result.summary == "Summarized old stuff."

    @pytest.mark.asyncio
    async def test_keep_last_n_one(self) -> None:
        """keep_last_n=1 compacts all but the very last message."""
        provider = MockProvider(summary_text="Everything summarized.")
        tracker = FileTracker()

        messages = [_user("a"), _assistant("b"), _user("c")]

        result = await compact_messages(messages, provider, tracker, keep_last_n=1)

        assert result.messages_compacted == 2

    @pytest.mark.asyncio
    async def test_file_tracker_snapshot_in_prompt(self) -> None:
        """File tracker snapshot is included in the prompt sent to the provider."""
        captured_context: list[Context] = []

        class CapturingProvider:
            @property
            def model_name(self) -> str:
                return "capture-model"

            @property
            def provider_name(self) -> str:
                return "capture"

            async def stream(
                self,
                context: Context,
                *,
                temperature: float | None = None,
                max_tokens: int | None = None,
                signal: asyncio.Event | None = None,
            ):  # type: ignore[override]
                captured_context.append(context)
                message = AssistantMessage(
                    content=[TextContent(text="summary")],
                    stop_reason=StopReason.END_TURN,
                    usage=Usage(),
                    timestamp=_ts(),
                )
                yield StreamDoneEvent(message=message)

        tracker = FileTracker()
        tracker.record_read("src/main.py")
        tracker.record_read("src/utils.py")
        tracker.record_write("src/main.py")

        messages = [
            _user("Fix the bug in main.py"),
            _assistant("Looking at it now"),
            _user("Thanks"),
            _assistant("Fixed!"),
            _user("Great"),
        ]

        await compact_messages(messages, CapturingProvider(), tracker, keep_last_n=2)

        # Verify the prompt was sent with file information
        assert len(captured_context) == 1
        ctx = captured_context[0]
        assert len(ctx.messages) == 1
        prompt_text = ctx.messages[0].content[0].text  # type: ignore[union-attr]
        assert "src/main.py" in prompt_text
        assert "src/utils.py" in prompt_text
        # files_modified should show src/main.py
        assert "Files modified:" in prompt_text

    @pytest.mark.asyncio
    async def test_tool_result_messages_serialized(self) -> None:
        """Tool result messages are properly serialized in compaction."""
        provider = MockProvider(summary_text="Used bash tool.")
        tracker = FileTracker()

        messages = [
            _user("Run ls"),
            AssistantMessage(
                content=[
                    ToolCallContent(
                        id="tc1",
                        name="bash",
                        arguments={"command": "ls"},
                    )
                ],
                stop_reason=StopReason.TOOL_USE,
                usage=Usage(),
                timestamp=_ts(),
            ),
            _tool_result("tc1", "bash", "file1.py\nfile2.py"),
            _assistant("Here are the files."),
            _user("Thanks"),
            _assistant("You're welcome"),
        ]

        result = await compact_messages(messages, provider, tracker, keep_last_n=2)

        assert result.messages_compacted == 4
        assert result.summary == "Used bash tool."


# =============================================================================
# Token estimation tests
# =============================================================================


class TestTokenEstimation:
    """Tests for token estimation helpers."""

    def test_estimate_tokens_empty(self) -> None:
        assert _estimate_tokens("") == 0

    def test_estimate_tokens_short(self) -> None:
        # "hello" = 5 chars -> max(1, 5//4) = 1
        assert _estimate_tokens("hello") == 1

    def test_estimate_tokens_longer(self) -> None:
        # 100 chars -> 25 tokens
        assert _estimate_tokens("x" * 100) == 25

    def test_estimate_messages_tokens(self) -> None:
        messages: list[Message] = [_user("hello world"), _assistant("hi there")]
        tokens = _estimate_messages_tokens(messages)
        assert tokens > 0


# =============================================================================
# Serialization tests
# =============================================================================


class TestSerializeMessages:
    """Tests for message serialization."""

    def test_serialize_user_and_assistant(self) -> None:
        messages: list[Message] = [_user("hello"), _assistant("hi")]
        text = _serialize_messages(messages)
        assert "user: hello" in text
        assert "assistant: hi" in text

    def test_serialize_empty(self) -> None:
        assert _serialize_messages([]) == ""

    def test_serialize_tool_result(self) -> None:
        messages: list[Message] = [_tool_result("tc1", "bash", "output here")]
        text = _serialize_messages(messages)
        assert "tool_result:" in text
        assert "output here" in text
