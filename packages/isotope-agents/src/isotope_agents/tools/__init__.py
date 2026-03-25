"""isotope-agents tools — modular tool implementations for the agent framework."""

from __future__ import annotations


def truncate_output(
    text: str,
    max_chars: int = 30_000,
    strategy: str = "head_tail",
) -> str:
    """Truncate tool output to stay within context limits.

    Args:
        text: The text to truncate.
        max_chars: Maximum characters to keep.
        strategy: Truncation strategy — "head", "tail", or "head_tail".

    Returns:
        The original text if within limits, or a truncated version with
        a marker indicating how much was removed.
    """
    if len(text) <= max_chars:
        return text

    total = len(text)
    marker = f"\n\n... [truncated {total - max_chars:,} of {total:,} chars] ...\n\n"
    marker_len = len(marker)

    if strategy == "head":
        return text[:max_chars] + f"\n\n... [truncated, {total:,} chars total]"

    if strategy == "tail":
        return f"[truncated, {total:,} chars total] ...\n\n" + text[-max_chars:]

    # head_tail (default): keep beginning and end
    usable = max_chars - marker_len
    if usable <= 0:
        return text[:max_chars] + f"\n\n... [truncated, {total:,} chars total]"

    head_size = usable * 2 // 3  # 2/3 head, 1/3 tail
    tail_size = usable - head_size
    return text[:head_size] + marker + text[-tail_size:]
