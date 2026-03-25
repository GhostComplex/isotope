# M2: Sessions + Rich Output + Robustness — Design Doc

**Date:** 2026-03-26
**Status:** Approved
**Owner:** Tachikoma
**Branch:** `user/tachikoma/dev-m2` (from `main`)
**PRD Reference:** §6 (Sessions), §8 (Loop Detection), M2 checklist

---

## Goal

Persistent JSONL sessions, polished markdown output, loop detection, config file. After M2: conversations survive restarts, output is readable, and the agent can't burn tokens in infinite loops.

## Success Criteria

- `isotope chat` auto-saves conversation to `~/.isotope/sessions/<id>.jsonl`
- `isotope sessions` lists previous sessions with timestamps + summaries
- `isotope chat --session <id>` resumes a previous session
- Tool call repeated 3x with same args → steering injection
- Code blocks have syntax highlighting via `rich`
- `~/.isotope/config.yaml` provides defaults (model, preset, etc.)
- All existing tests still pass + new tests for each subtask

---

## Subtasks

### M2.1: JSONL session format + persistence

**Files:**
- `packages/isotope-agents/src/isotope_agents/session.py`

**~200 LOC, M**

Define the JSONL session format and implement read/write:

```python
@dataclass
class SessionEntry:
    """One line in a .jsonl session file."""
    type: str          # session_start, user_message, assistant_message, tool_call, tool_result, compaction
    timestamp: str     # ISO 8601
    data: dict         # type-specific payload

class SessionStore:
    """Manages session persistence in ~/.isotope/sessions/."""

    def __init__(self, sessions_dir: Path | None = None):
        self.sessions_dir = sessions_dir or Path.home() / ".isotope" / "sessions"

    def create(self, model: str, preset: str) -> str:
        """Create a new session, return session ID."""

    def append(self, session_id: str, entry: SessionEntry) -> None:
        """Append an entry to a session file (atomic append)."""

    def load(self, session_id: str) -> list[SessionEntry]:
        """Load all entries from a session file."""

    def list_sessions(self) -> list[SessionMeta]:
        """List all sessions with metadata (id, start time, message count, last message preview)."""

    def entries_to_messages(self, entries: list[SessionEntry]) -> list[Message]:
        """Convert JSONL entries back to isotope-core Message objects for session resume."""
```

Session ID: short UUID (8 chars), e.g. `a1b2c3d4`.

File structure:
```
~/.isotope/sessions/
  a1b2c3d4.jsonl
  e5f6g7h8.jsonl
```

Each line is a JSON object with `type`, `timestamp`, and type-specific fields per PRD §6.

**Tests:** `packages/isotope-agents/tests/test_session.py` — test create, append, load, list, round-trip message conversion.

**Commit after done.**

---

### M2.2: Wire session persistence into TUI + IsotopeAgent

**Files:**
- `packages/isotope-agents/src/isotope_agents/agent.py` (add session hooks)
- `packages/isotope-agents/src/isotope_agents/tui/app.py` (wire auto-save)

**~100 LOC changes, S**

Add session tracking to `IsotopeAgent`:
- On init: create a new session or load existing one
- After each user message: append `user_message` entry
- After each assistant response: append `assistant_message` entry (with usage)
- After each tool call/result: append `tool_call` and `tool_result` entries
- On exit: no special action needed (JSONL is already persisted per-event)

The session store is injected into `IsotopeAgent.__init__`:
```python
class IsotopeAgent:
    def __init__(self, ..., session_id: str | None = None, session_store: SessionStore | None = None):
        ...
```

If `session_id` is provided, load and replay messages from the session. If not, create a new session.

**Tests:** Update `packages/isotope-agents/tests/test_agent.py` — verify session entries are written.

**Commit after done.**

---

### M2.3: Session CLI commands

**Files:**
- `packages/isotope-agents/src/isotope_agents/cli.py` (add `sessions` subcommand + `--session` flag)
- `packages/isotope-agents/src/isotope_agents/tui/app.py` (add `/sessions` TUI command)

**~80 LOC, S**

CLI:
```bash
# List sessions
isotope sessions
isotope sessions --limit 10

# Resume a session
isotope chat --session a1b2c3d4

# Output example:
# ID        Started              Messages  Last message
# a1b2c3d4  2026-03-26 01:00:00  12        "fix the auth bug..."
# e5f6g7h8  2026-03-25 23:00:00  5         "summarize this doc..."
```

TUI: `/sessions` command shows the same listing inline.

**Tests:** `packages/isotope-agents/tests/test_cli.py` — add tests for sessions subcommand.

**Commit after done.**

---

### M2.4: Loop detection

**Files:**
- `packages/isotope-core/src/isotope_core/loop.py` (add loop detection to agent loop)
- `packages/isotope-core/src/isotope_core/types.py` (add `LoopDetectedEvent`)

**~80 LOC, S**

Add to `AgentLoopConfig`:
```python
@dataclass
class LoopDetectionConfig:
    """Configuration for loop detection."""
    same_call_threshold: int = 3      # same tool + same args repeated N times → steer
    same_tool_threshold: int = 5      # same tool (any args) repeated N times → warn
    enabled: bool = True

@dataclass
class AgentLoopConfig:
    ...
    loop_detection: LoopDetectionConfig = field(default_factory=LoopDetectionConfig)
```

In the agent loop, after each tool call:
1. Track the last N tool calls (tool name + args hash)
2. If same tool+args repeated `same_call_threshold` times → inject a steering message: "You appear to be repeating the same action with the same arguments. Try a different approach or explain what's blocking you."
3. If same tool repeated `same_tool_threshold` times (any args) → emit a `LoopDetectedEvent` for the TUI to display a warning

Add `LoopDetectedEvent` to `AgentEvent` union.

**Tests:** `packages/isotope-core/tests/test_loop_detection.py`

**Commit after done.**

---

### M2.5: Rich markdown rendering

**Files:**
- `packages/isotope-agents/src/isotope_agents/tui/render.py` (enhance existing)

**~100 LOC, M**

Replace plain text output with `rich` library rendering:
- Assistant text: render as markdown (rich.Markdown)
- Code blocks: syntax highlighting via rich.syntax
- Tool output: display in a Panel with tool name as title
- Streaming: buffer text, render markdown on message completion (stream plain text, render final)

Add `rich` as a dependency of isotope-agents (in `[tui]` extras group).

**Tests:** `packages/isotope-agents/tests/test_render.py` — test markdown rendering output.

**Commit after done.**

---

### M2.6: Config file

**Files:**
- `packages/isotope-agents/src/isotope_agents/config.py`

**~80 LOC, S**

```yaml
# ~/.isotope/config.yaml
model: claude-sonnet-4-20250514
preset: coding
debug: false
sessions_dir: ~/.isotope/sessions
provider:
  base_url: http://localhost:8080
  api_key: ${ISOTOPE_API_KEY}  # env var expansion
```

```python
@dataclass
class IsotopeConfig:
    model: str = "default"
    preset: str = "coding"
    debug: bool = False
    sessions_dir: str = "~/.isotope/sessions"
    provider: dict | None = None

def load_config(path: Path | None = None) -> IsotopeConfig:
    """Load config from ~/.isotope/config.yaml, with env var expansion."""
```

Config priority: CLI flags > env vars > config file > defaults.

Wire into CLI (cli.py) so `isotope chat` picks up defaults from config.

**Tests:** `packages/isotope-agents/tests/test_config.py`

**Commit after done.**

---

### M2.7: Clean up + verify

- Verify all isotope-core tests pass (should be ~450+)
- Verify all isotope-agents tests pass (should be ~100+)
- `ruff check` + lint clean
- Update `packages/isotope-agents/pyproject.toml` with `rich` dependency
- Push, open PR to main

**Commit after done.**

---

## Notes

- Loop detection goes in isotope-core (it's agent loop behavior, not opinionated)
- Session persistence goes in isotope-agents (it's opinionated — file format, directory layout)
- Rich rendering goes in isotope-agents TUI (obviously)
- Config goes in isotope-agents (opinionated defaults)
- The session format is designed for M3 (compaction entries) and M4 (RPC replay) — don't break forward compatibility
- `rich` is gated behind `[tui]` extras so isotope-agents stays lightweight for programmatic use
