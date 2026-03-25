"""Context compaction engine for isotope-agents.

Provides the Compactor class that summarizes old messages when context
exceeds a configurable token threshold, preserving recent messages verbatim.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from isotope_core.types import (
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)

if TYPE_CHECKING:
    from isotope_core.providers.base import Provider

# Type alias for isotope-core message union
Message = UserMessage | AssistantMessage | ToolResultMessage


class Compactor:
    """Context compaction engine that summarizes old messages via LLM calls.

    The Compactor handles long conversation sessions by summarizing older messages
    when the total context exceeds a configurable token threshold. It preserves
    the most recent messages verbatim while replacing older messages with a
    compact summary.

    Attributes:
        max_context_tokens: Maximum tokens before compaction triggers.
        preserve_recent: Number of recent messages to keep verbatim.
    """

    def __init__(
        self,
        max_context_tokens: int = 100000,
        preserve_recent: int = 10,
    ) -> None:
        """Initialize the Compactor.

        Args:
            max_context_tokens: Maximum tokens before compaction is needed.
            preserve_recent: Number of recent messages to preserve verbatim.
        """
        self.max_context_tokens = max_context_tokens
        self.preserve_recent = preserve_recent

    def should_compact(self, messages: list[Message], max_tokens: int | None = None) -> bool:
        """Check if message list needs compaction.

        Args:
            messages: List of messages to check.
            max_tokens: Override the instance max_tokens if provided.

        Returns:
            True if compaction is needed, False otherwise.
        """
        threshold = max_tokens if max_tokens is not None else self.max_context_tokens

        # If we have fewer messages than preserve_recent, no need to compact
        if len(messages) <= self.preserve_recent:
            return False

        total_tokens = self._count_tokens(messages)
        return total_tokens > threshold

    async def compact(
        self,
        messages: list[Message],
        provider: Provider
    ) -> list[Message]:
        """Compact messages by summarizing old ones and preserving recent ones.

        Args:
            messages: List of messages to compact.
            provider: LLM provider for summarization.

        Returns:
            Compacted message list: [summary_message] + recent_messages
        """
        if len(messages) <= self.preserve_recent:
            # Nothing to compact
            return messages

        # Split messages into old (to be summarized) and recent (to preserve)
        old_messages = messages[:-self.preserve_recent]
        recent_messages = messages[-self.preserve_recent:]

        # Handle edge case: if old_messages is empty after split, return original
        if not old_messages:
            return messages

        # Generate summary of old messages
        summary_text = await self._summarize_messages(old_messages, provider)

        # Create a system-level summary message
        summary_message = UserMessage(
            content=[TextContent(text=f"[CONTEXT SUMMARY] {summary_text}")],
            timestamp=int(time.time()),
            pinned=True,  # Pin the summary to preserve it
        )

        # Return summary + recent messages
        return [summary_message] + recent_messages

    def _count_tokens(self, messages: list[Message]) -> int:
        """Estimate token count for a list of messages.

        This is a simple approximation: ~4 chars per token.
        In a production system, this would use the actual tokenizer.

        Args:
            messages: List of messages to count.

        Returns:
            Estimated token count.
        """
        total_chars = 0

        for message in messages:
            total_chars += self._count_message_chars(message)

        # Rough approximation: ~4 characters per token
        return total_chars // 4

    def _count_message_chars(self, message: Message) -> int:
        """Count characters in a single message.

        Args:
            message: Message to count.

        Returns:
            Character count.
        """
        char_count = 0

        # Count content characters
        if hasattr(message, 'content') and message.content:
            for content in message.content:
                if isinstance(content, TextContent):
                    char_count += len(content.text)
                elif isinstance(content, ThinkingContent):
                    char_count += len(content.thinking)
                elif isinstance(content, ToolCallContent):
                    # Count tool name and arguments
                    char_count += len(content.name)
                    if content.arguments:
                        char_count += len(json.dumps(content.arguments))

        # Add some overhead for message metadata
        char_count += 50

        return char_count

    async def _summarize_messages(
        self,
        messages: list[Message],
        provider: Provider
    ) -> str:
        """Summarize a list of messages using the LLM provider.

        Args:
            messages: Messages to summarize.
            provider: LLM provider for summarization.

        Returns:
            Summary text.
        """
        # Convert messages to text for summarization
        message_text = self._messages_to_text(messages)

        # Create summarization prompt
        system_prompt = (
            "You are a conversation summarizer. Summarize the provided conversation "
            "history concisely while preserving key information, decisions made, "
            "code changes, and important context. Focus on what was accomplished "
            "and any important details that might be referenced later."
        )

        summarization_prompt = f"""
Please summarize the following conversation history:

{message_text}

Provide a concise summary that captures:
- Main topics discussed
- Key decisions or actions taken
- Important technical details or code changes
- Any ongoing context that might be referenced later

Keep the summary focused and under 500 words.
"""

        # Create messages for the summarization request
        summary_request = [
            UserMessage(
                content=[TextContent(text=summarization_prompt)],
                timestamp=int(time.time()),
            )
        ]

        try:
            # Make the summarization request
            response = await provider.complete(
                messages=summary_request,
                system_prompt=system_prompt,
                max_tokens=1000,  # Limit summary length
            )

            # Extract text from response
            if response.content:
                for content in response.content:
                    if isinstance(content, TextContent):
                        return content.text.strip()

            # Fallback if no text content found
            return self._fallback_summary(messages)

        except Exception as e:
            # If summarization fails, provide a fallback
            print(f"Warning: Summarization failed ({e}), using fallback summary")
            return self._fallback_summary(messages)

    def _messages_to_text(self, messages: list[Message]) -> str:
        """Convert messages to human-readable text format.

        Args:
            messages: Messages to convert.

        Returns:
            Text representation of the conversation.
        """
        lines = []

        for message in messages:
            if isinstance(message, UserMessage):
                role = "User"
            elif isinstance(message, AssistantMessage):
                role = "Assistant"
            elif isinstance(message, ToolResultMessage):
                role = f"Tool({message.tool_name})"
            else:
                role = "Unknown"

            # Extract text content from message
            content_parts = []
            if hasattr(message, 'content') and message.content:
                for content in message.content:
                    if isinstance(content, TextContent):
                        content_parts.append(content.text)
                    elif isinstance(content, ThinkingContent):
                        content_parts.append(f"[Thinking] {content.thinking}")
                    elif isinstance(content, ToolCallContent):
                        args_str = json.dumps(content.arguments) if content.arguments else ""
                        content_parts.append(f"[Tool Call] {content.name}({args_str})")

            content_text = " ".join(content_parts)
            if content_text:
                lines.append(f"{role}: {content_text}")

        return "\n".join(lines)

    def _fallback_summary(self, messages: list[Message]) -> str:
        """Provide a simple fallback summary when LLM summarization fails.

        Args:
            messages: Messages to summarize.

        Returns:
            Simple fallback summary.
        """
        user_messages = sum(1 for msg in messages if isinstance(msg, UserMessage))
        assistant_messages = sum(1 for msg in messages if isinstance(msg, AssistantMessage))
        tool_messages = sum(1 for msg in messages if isinstance(msg, ToolResultMessage))

        # Try to extract first user message as context
        first_topic = "general conversation"
        for msg in messages:
            if isinstance(msg, UserMessage) and msg.content:
                for content in msg.content:
                    if isinstance(content, TextContent):
                        # Use first 100 chars as topic indicator
                        first_topic = content.text[:100].strip().replace('\n', ' ')
                        if len(first_topic) > 97:
                            first_topic = first_topic[:97] + "..."
                        break
                break

        return (
            f"Previous conversation with {user_messages} user messages, "
            f"{assistant_messages} assistant messages, and {tool_messages} tool results. "
            f"Started with: {first_topic}"
        )