"""Tests for the skill loader module."""

from __future__ import annotations

from pathlib import Path

import pytest

from isotopes.skills import SkillLoader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SKILL = """\
---
name: git-commit
description: Helps write conventional commit messages
---

# Git Commit Skill

Follow conventional-commits when drafting messages.
"""

VALID_SKILL_2 = """\
---
name: code-review
description: Perform thorough code review with security analysis
---

# Code Review

Check for bugs, security issues, and style.
"""

NO_FRONTMATTER = """\
# Just a regular Markdown file

No YAML frontmatter here.
"""

BAD_FRONTMATTER_MISSING_FIELDS = """\
---
name: incomplete
---

Missing the description field.
"""

BAD_FRONTMATTER_NOT_DICT = """\
---
- just
- a
- list
---

Not a dict.
"""


def _write_skill(directory: Path, content: str) -> Path:
    """Write a SKILL.md file in *directory* and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Scan tests
# ---------------------------------------------------------------------------


class TestScan:
    """Tests for SkillLoader.scan()."""

    def test_scan_finds_skill_md_with_valid_frontmatter(self, tmp_path: Path) -> None:
        """scan() discovers SKILL.md files with valid frontmatter."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        results = loader.scan()

        assert len(results) == 1
        info = results[0]
        assert info.name == "git-commit"
        assert info.description == "Helps write conventional commit messages"
        assert info.loaded is False
        assert info.instructions == ""

    def test_scan_finds_multiple_skills(self, tmp_path: Path) -> None:
        """scan() discovers multiple SKILL.md files across subdirectories."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)
        _write_skill(tmp_path / "skills" / "code-review", VALID_SKILL_2)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        results = loader.scan()

        names = {s.name for s in results}
        assert names == {"git-commit", "code-review"}

    def test_scan_ignores_files_without_frontmatter(self, tmp_path: Path) -> None:
        """Files without YAML frontmatter are silently skipped."""
        _write_skill(tmp_path / "skills" / "valid", VALID_SKILL)
        _write_skill(tmp_path / "skills" / "no-fm", NO_FRONTMATTER)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        results = loader.scan()

        assert len(results) == 1
        assert results[0].name == "git-commit"

    def test_scan_ignores_incomplete_frontmatter(self, tmp_path: Path) -> None:
        """Frontmatter missing required fields is skipped."""
        _write_skill(tmp_path / "skills" / "bad", BAD_FRONTMATTER_MISSING_FIELDS)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        results = loader.scan()

        assert results == []

    def test_scan_ignores_non_dict_frontmatter(self, tmp_path: Path) -> None:
        """Frontmatter that parses to a non-dict is skipped."""
        _write_skill(tmp_path / "skills" / "bad", BAD_FRONTMATTER_NOT_DICT)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        results = loader.scan()

        assert results == []

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """Scanning an empty directory returns no skills."""
        empty = tmp_path / "empty"
        empty.mkdir()

        loader = SkillLoader(skill_dirs=[empty])
        results = loader.scan()

        assert results == []

    def test_scan_nonexistent_directory(self, tmp_path: Path) -> None:
        """Scanning a nonexistent directory returns no skills (no error)."""
        loader = SkillLoader(skill_dirs=[tmp_path / "does-not-exist"])
        results = loader.scan()

        assert results == []

    def test_scan_multiple_dirs(self, tmp_path: Path) -> None:
        """scan() searches across all configured skill directories."""
        _write_skill(tmp_path / "dir_a" / "s1", VALID_SKILL)
        _write_skill(tmp_path / "dir_b" / "s2", VALID_SKILL_2)

        loader = SkillLoader(skill_dirs=[tmp_path / "dir_a", tmp_path / "dir_b"])
        results = loader.scan()

        names = {s.name for s in results}
        assert names == {"git-commit", "code-review"}


# ---------------------------------------------------------------------------
# Load tests
# ---------------------------------------------------------------------------


class TestLoad:
    """Tests for SkillLoader.load()."""

    def test_load_populates_instructions(self, tmp_path: Path) -> None:
        """load() reads the full SKILL.md content into instructions."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        loader.scan()

        info = loader.load("git-commit")
        assert info.loaded is True
        assert info.instructions == VALID_SKILL
        assert "conventional-commits" in info.instructions

    def test_load_is_idempotent(self, tmp_path: Path) -> None:
        """Calling load() twice returns the same object without re-reading."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        loader.scan()

        first = loader.load("git-commit")
        second = loader.load("git-commit")
        assert first is second

    def test_load_nonexistent_skill_raises_key_error(self, tmp_path: Path) -> None:
        """Loading a skill that doesn't exist raises KeyError."""
        loader = SkillLoader(skill_dirs=[tmp_path])
        loader.scan()

        with pytest.raises(KeyError, match="no-such-skill"):
            loader.load("no-such-skill")

    def test_load_without_scan_raises_key_error(self) -> None:
        """Loading before scanning raises KeyError (nothing indexed)."""
        loader = SkillLoader(skill_dirs=[])
        with pytest.raises(KeyError):
            loader.load("anything")


# ---------------------------------------------------------------------------
# Match tests
# ---------------------------------------------------------------------------


class TestMatch:
    """Tests for SkillLoader.match()."""

    def test_match_returns_best_match(self, tmp_path: Path) -> None:
        """match() returns the skill whose name/description best matches."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)
        _write_skill(tmp_path / "skills" / "code-review", VALID_SKILL_2)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        loader.scan()

        result = loader.match("review code for security")
        assert result is not None
        assert result.name == "code-review"

    def test_match_by_name_keyword(self, tmp_path: Path) -> None:
        """match() can find a skill by a keyword from its name."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)
        _write_skill(tmp_path / "skills" / "code-review", VALID_SKILL_2)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        loader.scan()

        result = loader.match("commit")
        assert result is not None
        assert result.name == "git-commit"

    def test_match_returns_none_for_no_match(self, tmp_path: Path) -> None:
        """match() returns None when no skill matches the query."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        loader.scan()

        result = loader.match("quantum computing entanglement")
        assert result is None

    def test_match_empty_skills(self) -> None:
        """match() returns None when no skills have been scanned."""
        loader = SkillLoader(skill_dirs=[])
        assert loader.match("anything") is None

    def test_match_empty_query(self, tmp_path: Path) -> None:
        """match() returns None for an empty query string."""
        _write_skill(tmp_path / "skills" / "git-commit", VALID_SKILL)

        loader = SkillLoader(skill_dirs=[tmp_path / "skills"])
        loader.scan()

        assert loader.match("") is None
        assert loader.match("   ") is None
