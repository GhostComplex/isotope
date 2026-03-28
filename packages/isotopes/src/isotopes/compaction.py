"""Compaction engine for context management.

Compacts older messages into a summary via an LLM provider, preserving
recent context and file operation metadata. This allows long-running
agent sessions to stay within context window limits without losing
critical information about the task, progress, decisions, and file state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from isotopes_core.context import FileTracker, _extract_message_text
from isotopes_core.providers.base import Provider, StreamDoneEvent
from isotopes_core.types import (
    Context,
    Message,
    TextContent,
    UserMessage,
)

# =============================================================================
# Compaction Result
# =============================================================================

_CHARS_PER_TOKEN = 4

_COMPACTION_PROMPT_TEMPLATE = """\
Summarize the following conversation. Preserve:
- What the user asked for and current progress
- Files read: {files_read}
- Files modified: {files_modified}
- Key decisions made
- Errors encountered and how they were resolved
- Any pending work or next steps

Do NOT include tool call details — just summarize what was done and learned.

Conversation:
{conversation}"""


@dataclass
class CompactionResult:
    """Result of compacting a message history.

    Attributes:
        summary: The LLM-generated summary of compacted messages.
        files_read: List of files that were read during the session.
        files_modified: List of files that were modified during the session.
        messages_compacted: Number of messages that were compacted.
        tokens_before: Estimated token count before compaction.
        tokens_after: Estimated token count after compaction.
    """

    summary: str
    files_read: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    messages_compacted: int = 0
    tokens_before: int = 0
    tokens_after: int = 0


# =============================================================================
# Message Serialization
# =============================================================================


def _estimate_tokens(text: str) -> int:
    """Estimate token count using chars/4 heuristic."""
    return max(1, len(text) // _CHARS_PER_TOKEN) if text else 0


def _serialize_messages(messages: list[Message]) -> str:
    """Serialize a list of messages into a human-readable text block.

    Each message is rendered as ``role: text_content`` on its own line(s).
    Tool results include the tool name for context.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.role
        text = _extract_message_text(msg)
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def _estimate_messages_tokens(messages: list[Message]) -> int:
    """Estimate total tokens across a list of messages."""
    total = 0
    for msg in messages:
        text = _extract_message_text(msg)
        total += _estimate_tokens(text) + 4  # 4 token overhead per message
    return total


# =============================================================================
# Compaction Engine
# =============================================================================


async def compact_messages(
    messages: list[Message],
    provider: Provider,
    file_tracker: FileTracker,
    *,
    keep_last_n: int = 4,
    model: str | None = None,
) -> CompactionResult:
    """Compact older messages into a summary, preserving recent context.

    Splits the message list into compactable (older) messages and the most
    recent ``keep_last_n`` messages. The older messages are serialized and
    sent to the LLM provider with a structured prompt that instructs the
    model to preserve essential context: task description, progress, file
    operations, key decisions, errors, and pending work.

    Args:
        messages: The full list of conversation messages.
        provider: An LLM provider to generate the summary.
        file_tracker: Tracks files read and modified in the session.
        keep_last_n: Number of most recent messages to preserve verbatim.
            Defaults to 4.
        model: Optional model name override (unused by the engine itself,
            reserved for future per-model token estimation).

    Returns:
        A ``CompactionResult`` with the summary, file lists, and token stats.
    """
    # Handle edge cases
    if not messages:
        snapshot = file_tracker.snapshot()
        return CompactionResult(
            summary="",
            files_read=snapshot["files_read"],
            files_modified=snapshot["files_modified"],
            messages_compacted=0,
            tokens_before=0,
            tokens_after=0,
        )

    # Step 1: Split messages into [compactable | keep_last_n]
    if len(messages) <= keep_last_n:
        # Nothing to compact — all messages are within the keep window
        snapshot = file_tracker.snapshot()
        tokens = _estimate_messages_tokens(messages)
        return CompactionResult(
            summary="",
            files_read=snapshot["files_read"],
            files_modified=snapshot["files_modified"],
            messages_compacted=0,
            tokens_before=tokens,
            tokens_after=tokens,
        )

    compactable = messages[: len(messages) - keep_last_n]
    kept = messages[len(messages) - keep_last_n :]

    # Step 2: Serialize compactable messages
    conversation_text = _serialize_messages(compactable)

    # Step 3: Build structured prompt with file tracker snapshot
    snapshot = file_tracker.snapshot()
    files_read = snapshot["files_read"]
    files_modified = snapshot["files_modified"]

    prompt_text = _COMPACTION_PROMPT_TEMPLATE.format(
        files_read=", ".join(files_read) if files_read else "(none)",
        files_modified=", ".join(files_modified) if files_modified else "(none)",
        conversation=conversation_text,
    )

    # Ask the LLM to summarize
    summarize_context = Context(
        system_prompt="You are a helpful summarizer. Be concise but thorough.",
        messages=[
            UserMessage(
                content=[TextContent(text=prompt_text)],
                timestamp=int(time.time() * 1000),
            )
        ],
    )

    summary_text = ""
    async for event in provider.stream(summarize_context):
        if isinstance(event, StreamDoneEvent):
            for block in event.message.content:
                if isinstance(block, TextContent):
                    summary_text += block.text

    # Step 4: Estimate tokens using chars/4 heuristic
    tokens_before = _estimate_messages_tokens(messages)
    # After compaction: summary token cost + kept messages
    tokens_after = _estimate_tokens(summary_text) + _estimate_messages_tokens(kept)

    # Step 5: Return CompactionResult
    return CompactionResult(
        summary=summary_text,
        files_read=files_read,
        files_modified=files_modified,
        messages_compacted=len(compactable),
        tokens_before=tokens_before,
        tokens_after=tokens_after,
    )
