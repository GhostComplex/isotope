"""Tests for the truncate_output utility."""

from isotopes.tools import truncate_output


class TestTruncateOutput:
    """Tests for truncate_output."""

    def test_no_truncation_needed(self) -> None:
        """Short text is returned unchanged."""
        text = "Hello, world!"
        assert truncate_output(text, max_chars=100) == text

    def test_exact_limit(self) -> None:
        """Text exactly at the limit is not truncated."""
        text = "x" * 100
        assert truncate_output(text, max_chars=100) == text

    def test_head_strategy(self) -> None:
        """Head strategy keeps the beginning."""
        text = "a" * 200
        result = truncate_output(text, max_chars=50, strategy="head")
        assert result.startswith("a" * 50)
        assert "truncated" in result
        assert len(result.split("a" * 50)[0]) == 0  # starts with content

    def test_tail_strategy(self) -> None:
        """Tail strategy keeps the end."""
        text = "a" * 200
        result = truncate_output(text, max_chars=50, strategy="tail")
        assert result.endswith("a" * 50)
        assert "truncated" in result

    def test_head_tail_strategy(self) -> None:
        """Head_tail keeps beginning and end with marker in middle."""
        text = "HEAD" * 50 + "MIDDLE" * 50 + "TAIL" * 50
        result = truncate_output(text, max_chars=100, strategy="head_tail")
        assert "truncated" in result
        assert result.startswith("HEAD")
        # The tail portion should contain TAIL
        after_marker = result.split("...")[-1]
        assert "TAIL" in after_marker

    def test_head_tail_is_default(self) -> None:
        """head_tail is the default strategy."""
        text = "x" * 200
        result_default = truncate_output(text, max_chars=50)
        result_explicit = truncate_output(text, max_chars=50, strategy="head_tail")
        assert result_default == result_explicit

    def test_default_max_chars(self) -> None:
        """Default max_chars is 30_000."""
        text = "x" * 30_000
        assert truncate_output(text) == text
        text_larger = "x" * 30_001
        assert truncate_output(text_larger) != text_larger

    def test_preserves_content_within_limit(self) -> None:
        """The total output length is close to max_chars."""
        text = "x" * 10_000
        result = truncate_output(text, max_chars=500, strategy="head_tail")
        # Should be roughly around max_chars (plus marker)
        assert len(result) < 600  # some room for the marker text
