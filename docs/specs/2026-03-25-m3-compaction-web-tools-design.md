# M3: Compaction + Web Tools

## Goal
Handle long sessions gracefully via context compaction, and add web capabilities (search + fetch). Ship update.

## Architecture Notes
- Compaction triggers when context exceeds a configurable token threshold
- Uses LLM-based summarization: older messages get summarized into a compact block
- The summary replaces the original messages in context, preserving the system prompt and recent messages
- Web tools use `httpx` (already in `[search]` optional deps)
- WebSearchTool wraps Brave Search API (requires API key in config)
- WebFetchTool extracts readable content from URLs (HTML → text)

## Subtasks

### M3.1: Context compaction engine (~400 LOC, M)
**What:** Build the compaction module that summarizes old messages when context overflows.
- New file: `src/isotope_agents/compaction.py`
- `Compactor` class:
  - `should_compact(messages, max_tokens)` — check if compaction needed
  - `compact(messages, provider)` — summarize old messages via LLM call
  - Returns: `[summary_message] + recent_messages` (preserves last N messages verbatim)
- Configurable: `max_context_tokens`, `preserve_recent` (number of recent messages to keep)
- The summary is injected as a system-level context block, not a fake user/assistant message
- Tests: `tests/test_compaction.py` — mock LLM calls, verify message reduction, edge cases (empty history, already compact)
- Commit after tests pass

### M3.2: Compaction integration with Agent + Sessions (~250 LOC, S)
**What:** Wire compaction into the agent loop so it triggers automatically.
- Modify: `agent.py` — add compaction hook before each `prompt()` call
- Modify: `session.py` — store compaction metadata (when compacted, original message count)
- Modify: `config.py` — add `compaction.max_tokens` (default: 100000), `compaction.preserve_recent` (default: 10)
- TUI feedback: show `[context compacted: N messages → summary]` when compaction fires
- Tests: integration test verifying compaction triggers at threshold
- Commit after tests pass

### M3.3: WebSearchTool (~200 LOC, S)
**What:** Web search via Brave Search API.
- New file: `src/isotope_agents/tools/web_search.py`
- Uses `httpx` for async HTTP requests
- Requires `BRAVE_API_KEY` env var or config entry
- Returns: title, URL, snippet for top N results (default 5)
- Graceful error handling: missing API key, rate limits, network errors
- Register in `tools/__init__.py` as `"web_search"`
- Add to `assistant` preset default tools
- Tests: `tests/test_web_search.py` — mock HTTP responses, error cases
- Commit after tests pass

### M3.4: WebFetchTool (~200 LOC, S)
**What:** Fetch and extract readable content from URLs.
- New file: `src/isotope_agents/tools/web_fetch.py`
- Uses `httpx` for fetching, basic HTML-to-text extraction (strip tags, extract main content)
- Optional: use `beautifulsoup4` if available, fallback to regex stripping
- Configurable max content length (default: 50000 chars)
- Register in `tools/__init__.py` as `"web_fetch"`
- Add to `assistant` preset default tools
- Tests: `tests/test_web_fetch.py` — mock responses, HTML extraction, truncation
- Commit after tests pass

### M3.5: Polish + PR (~150 LOC, S)
**What:** Error handling improvements, system prompt engineering, version bump.
- Improve error recovery: tool failures shouldn't crash the agent loop
- Better system prompts for coding and assistant presets (based on real usage patterns)
- Update version to `0.3.0` in `pyproject.toml`
- Update README with M3 features
- All tests pass
- Commit, open PR: `user/steins-ghost/dev-m3` → `user/steins-ghost/dev-m2`

## Branch
`user/steins-ghost/dev-m3` — branch from `user/steins-ghost/dev-m2`

## Definition of Done
- Long sessions auto-compact without user intervention
- `web_search` and `web_fetch` tools work with assistant preset
- All existing + new tests pass
- README updated
- PR opened
