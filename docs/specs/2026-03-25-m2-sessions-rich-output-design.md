# M1 Completion: PyPI Release

## Status
M1 is feature-complete. All code, tests, and CLI are working. This task covers the final step: publishing to PyPI.

## Subtask

### M1.final: PyPI Release (~30 min, S)
- Verify all 80 tests pass: `python -m pytest tests/ -v`
- Verify package builds cleanly: `python -m build`
- Verify `isotope --version` shows `0.1.0`
- Publish to PyPI: `python -m twine upload dist/*`
- Verify install from PyPI works: `pip install isotope-agents[tui]`
- Commit tag: `git tag v0.1.0 && git push origin v0.1.0`

**Credentials:** Ask Steins for PyPI token before publishing.

---

# M2: Sessions + Rich Output

## Goal
Session persistence and improved output rendering. Users can resume conversations across restarts. TUI output is properly formatted with markdown rendering and syntax highlighting.

## Architecture Notes
- Sessions stored as JSON in `~/.isotope/sessions/`
- Each session has a UUID, timestamp, preset name, and message history
- Session compaction is NOT in M2 (that's M3) — M2 just stores raw messages
- Rich rendering uses the `rich` library (already in `[tui]` deps)
- Config file loading already exists in `config.py` — extend it for session-related settings

## Subtasks

### M2.1: Session model + persistence (~350 LOC, M)
**What:** Define the Session data model and save/load logic.
- New file: `src/isotope_agents/session.py`
- Session dataclass: `id` (UUID), `name` (optional), `preset` (str), `model` (str), `created_at`, `updated_at`, `messages` (list of isotope-core message types)
- `SessionStore` class:
  - `save(session)` — serialize to `~/.isotope/sessions/{id}.json`
  - `load(id)` — deserialize from file
  - `list()` — list all saved sessions with metadata (without loading full messages)
  - `delete(id)` — remove session file
- Message serialization: convert isotope-core `UserMessage`/`AssistantMessage`/`ToolResult` to JSON and back
- Auto-create `~/.isotope/sessions/` directory
- Tests: `tests/test_session.py` — save/load round-trip, list, delete, corrupt file handling
- Commit after tests pass

### M2.2: Session integration with Agent + TUI (~300 LOC, M)
**What:** Wire sessions into IsotopeAgent and TUI so conversations persist.
- Modify: `agent.py` — add `session_id` property, `load_session()`, `save_session()` methods
- Modify: `tui/app.py` — auto-save session on exit, load session on startup if `--session` flag provided
- Modify: `cli.py` — add `--session <id>` flag to `chat` command, add `isotope sessions` subcommand (list sessions)
- New slash commands in `tui/commands.py`:
  - `/session` — show current session info
  - `/sessions` — list saved sessions
  - `/session <id>` — switch to a different session (save current first)
  - `/save` — force save current session
  - `/new` — start a new session (save current first)
- Auto-save triggers: on exit, on `/save`, on session switch
- Tests: `tests/test_session_integration.py` — verify session flows
- Commit after tests pass

### M2.3: Rich markdown rendering (~250 LOC, S)
**What:** Render LLM output as formatted markdown in the TUI.
- Modify: `tui/output.py` — add `render_markdown(text)` using `rich.markdown.Markdown`
- Modify: `tui/app.py` — after streaming completes, render the full response as markdown (don't render during streaming — that's too complex for now; stream as plain text, then re-render at the end)
- Syntax highlighting for code blocks via `rich.syntax.Syntax`
- Respect terminal width
- Graceful fallback if `rich` not installed (plain text)
- Tests: `tests/test_output.py` — verify markdown rendering produces expected output
- Commit after tests pass

### M2.4: Config file extensions + polish (~200 LOC, S)
**What:** Extend config to support session-related settings and polish the experience.
- Modify: `config.py` — add `sessions_dir` (default `~/.isotope/sessions/`), `auto_save` (bool, default true), `theme` (for future rich theming)
- Modify: `cli.py` — `isotope sessions` shows a nice table with rich
- Add `isotope sessions --delete <id>` for cleanup
- Update README.md with M2 features (sessions, markdown rendering)
- Update version to `0.2.0` in `pyproject.toml`
- Tests: verify config loading with new fields
- Commit, open PR

**Ship:** `isotope chat` persists sessions across restarts. Output is formatted with markdown rendering. `isotope sessions` lists past sessions.

---

## Branch
`feat/sessions/dev-m2` — branch from `main`

## Definition of Done
- All existing tests still pass (80+)
- New tests for session model, integration, rendering
- `isotope chat` auto-saves sessions
- `isotope sessions` lists saved sessions
- `isotope chat --session <id>` resumes a session
- Markdown + syntax highlighting in TUI output
- README updated
- PR opened targeting `main`
