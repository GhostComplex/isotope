"""Skill loader — scans directories for SKILL.md files with YAML frontmatter.

Discovers skills lazily: scan() reads only frontmatter (name + description),
load() reads the full SKILL.md content on demand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillInfo:
    """Metadata and content for a single skill."""

    name: str
    description: str
    path: Path  # path to SKILL.md
    loaded: bool = False
    instructions: str = ""  # full SKILL.md content (loaded lazily)


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Extract YAML frontmatter from a SKILL.md string.

    Returns a dict with at least 'name' and 'description', or None if
    the file has no valid frontmatter.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None

    try:
        import yaml
    except ImportError:  # pragma: no cover
        return None

    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        return None
    if "name" not in data or "description" not in data:
        return None
    return {
        "name": str(data["name"]),
        "description": str(data["description"]),
    }


@dataclass
class SkillLoader:
    """Scans directories for SKILL.md files and loads them on demand."""

    skill_dirs: list[Path] = field(default_factory=list)
    _skills: dict[str, SkillInfo] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> list[SkillInfo]:
        """Scan skill directories for SKILL.md files.

        Walks each directory recursively looking for files named ``SKILL.md``.
        Only the YAML frontmatter (``name`` and ``description``) is read;
        the full body is deferred until :meth:`load` is called.

        Returns:
            List of discovered :class:`SkillInfo` objects.
        """
        self._skills.clear()

        for skill_dir in self.skill_dirs:
            resolved = Path(str(skill_dir)).expanduser().resolve()
            if not resolved.is_dir():
                continue

            for md_path in resolved.rglob("SKILL.md"):
                self._index_skill(md_path)

        return list(self._skills.values())

    def load(self, name: str) -> SkillInfo:
        """Load the full SKILL.md content for a previously scanned skill.

        Args:
            name: The skill name (as declared in frontmatter).

        Returns:
            Updated :class:`SkillInfo` with ``instructions`` populated.

        Raises:
            KeyError: If the skill name was not found during the last scan.
        """
        if name not in self._skills:
            raise KeyError(f"Skill not found: {name!r}")

        info = self._skills[name]
        if not info.loaded:
            info.instructions = info.path.read_text(encoding="utf-8")
            info.loaded = True
        return info

    def match(self, query: str) -> SkillInfo | None:
        """Find the best-matching skill for a free-text query.

        Uses simple case-insensitive keyword overlap between the query
        and each skill's name + description.  Returns the skill with
        the highest overlap, or ``None`` when nothing matches.
        """
        if not self._skills:
            return None

        query_tokens = _tokenize(query)
        if not query_tokens:
            return None

        best: SkillInfo | None = None
        best_score = 0

        for info in self._skills.values():
            corpus = f"{info.name} {info.description}"
            corpus_tokens = _tokenize(corpus)
            score = len(query_tokens & corpus_tokens)
            if score > best_score:
                best_score = score
                best = info

        return best

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _index_skill(self, md_path: Path) -> None:
        """Parse frontmatter of a SKILL.md file and register it."""
        try:
            # Read only the first 4 KiB — plenty for frontmatter.
            with open(md_path, encoding="utf-8") as fh:
                head = fh.read(4096)
        except OSError:
            return

        meta = _parse_frontmatter(head)
        if meta is None:
            return

        self._skills[meta["name"]] = SkillInfo(
            name=meta["name"],
            description=meta["description"],
            path=md_path,
        )


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens from *text*."""
    return {w for w in re.split(r"\W+", text.lower()) if w}
