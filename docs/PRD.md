# Isotope — PRD v6

**A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.**

> **Design principle: Restrained but extensible.** Ship the minimal useful surface. Make everything hookable. Don't build what users haven't asked for — but never paint yourself into a corner.

---

## 1. What Is Isotope

A **mono-repo** containing two Python packages:

| Package | Location | Role |
|---|---|---|
| `isotopes-core` | `packages/isotopes-core/` | LLM providers, agent loop, middleware, events, context |
| `isotopes` | `packages/isotopes/` | Agent framework: tools, TUI, sessions, RPC, extensions, presets |

`isotopes-core` already exists as a standalone repo (`GhostComplex/isotopes-core`, 5.3k LoC, 97% test coverage, async, Pydantic v2). **M0 migrates it into this mono-repo.**

`isotopes` builds on top — and starts with existing TUI code from isotopes-core.

Isotope is **role-agnostic**. Presets define tool sets and system prompts; users choose or create their own:

```yaml
# ~/.isotopes/config.yaml
preset: coding        # or: assistant, minimal, custom
```

### Built-in Presets

| Preset | System Prompt | Default Tools | Use Case |
|---|---|---|---|
| `coding` | "You are a coding agent..." | bash, read, write, edit, grep, glob | Software development |
| `assistant` | "You are a helpful assistant..." | bash, read, write, web_search, web_fetch | General tasks, research |
| `minimal` | (none) | (none) | Bare LLM, user adds tools via config/extensions/MCP |

All tools available to all presets — the table shows defaults. Users override via config.

---

## 2. Why Not Just Use Pi-mono

Pi-mono is TypeScript. We need Python because:

- Existing backend code depends on isotopes-core (Python)
- Python AI/ML ecosystem is stronger
- isotopes-core is already built and battle-tested

We take pi-mono's **architecture** (it's good), not its code.

---

## 3. Starting Point

isotopes-core already has a working TUI (`tui/main.py`, ~1060 LoC) with:

- ✅ Claude Code-style steering (type during streaming to redirect)
- ✅ prompt-toolkit integration (visible input prompt during streaming)
- ✅ Streaming event consumption with tool call display
- ✅ Slash commands (/tools, /model, /system, /clear, /history, /debug)
- ✅ Built-in tools: read_file, write_file, edit_file, terminal, get_current_time
- ✅ Follow-up queuing (/follow) and abort (/abort)

**Strategy:** Migrate isotopes-core into this mono-repo (M0), split TUI into components, then extend (M1+).

---

## 4. Architecture

```
isotopes (mono-repo)
├── packages/
│   ├── isotopes-core/              ← migrated from GhostComplex/isotopes-core
│   │   ├── src/isotopes_core/
│   │   │   ├── agent.py           — stateful Agent wrapper
│   │   │   ├── loop.py            — agent loop (plan → act → observe → repeat)
│   │   │   ├── types.py           — Pydantic v2 types
│   │   │   ├── tools.py           — Tool framework + @tool decorator
│   │   │   ├── events.py          — EventStream
│   │   │   ├── context.py         — token counting, pruning
│   │   │   ├── middleware.py       — composable middleware
│   │   │   └── providers/         — OpenAI, Anthropic, proxy, router
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   └── isotopes/            ← new, builds on isotopes-core
│       ├── src/isotopes/
│       │   ├── agent.py           — Agent wrapping isotopes-core
│       │   ├── presets.py         — role configurations
│       │   ├── session.py         — session persistence (JSONL)
│       │   ├── compaction.py      — context compaction (file-aware)
│       │   ├── config.py          — config file loading
│       │   ├── cli.py             — CLI entry point
│       │   ├── tui/
│       │   │   ├── app.py         — main TUI (from isotopes-core tui/)
│       │   │   ├── input.py       — input handling (prompt-toolkit)
│       │   │   ├── output.py      — output rendering (rich)
│       │   │   └── commands.py    — slash command handlers
│       │   └── tools/
│       │       ├── __init__.py    — tool registry + truncation utilities
│       │       ├── bash.py        — from existing terminal tool
│       │       ├── read.py        — from existing read_file
│       │       ├── write.py       — from existing write_file
│       │       ├── edit.py        — from existing edit_file
│       │       ├── grep.py        — new (ripgrep-backed)
│       │       └── glob.py        — new (glob patterns)
│       ├── tests/
│       └── pyproject.toml
│
├── docs/                          — shared docs (this PRD, etc.)
├── pyproject.toml                 — workspace root (uv workspace)
└── README.md
```

**What's NOT in the tree (yet):** skills.py, extensions.py, rpc.py, web tools, memory tool. These come in later milestones. We don't stub what we haven't built.

### How It Runs

```bash
# Interactive TUI
isotopes chat
isotopes chat --preset coding

# One-shot (print mode)
isotopes run "fix the bug in auth.py"
isotopes run --print "summarize this document"

# RPC mode (M4)
isotopes rpc
```

---

## 5. Tool System

### 5.1 Tool Authoring

Two ways to define tools — pick what fits:

**`@tool` decorator** (simple tools):

```python
from isotopes_core import tool

@tool
async def grep(
    pattern: str,
    path: str = ".",
    include: str | None = None,
) -> str:
    """Search for a pattern in files using ripgrep.

    Args:
        pattern: Regex pattern to search for.
        path: Directory to search in.
        include: Glob pattern to filter files (e.g. "*.py").
    """
    result = await run_ripgrep(pattern, path, include)
    return truncate(result, max_chars=30_000)
```

The decorator auto-generates the JSON schema from type hints + docstring. Inspired by smolagents' `@tool` — the best DX pattern in the Python agent ecosystem.

**`Tool()` class** (complex tools needing lifecycle/state):

```python
from isotopes_core import Tool

bash_tool = Tool(
    name="bash",
    description="Execute a shell command.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to run."},
        },
        "required": ["command"],
    },
    execute=execute_bash,
)
```

Both produce the same `Tool` object. The `@tool` decorator is sugar, not a separate system.

> **Design note:** The `@tool` decorator lives in `isotopes-core` (it's just schema generation + wrapping). Tool *implementations* (bash, read, grep, etc.) live in `isotopes`.

### 5.2 Tool Output Truncation

All tools producing variable-length output MUST truncate. Utility provided:

```python
from isotopes.tools import truncate_output

def execute_grep(pattern: str, path: str) -> str:
    raw = subprocess.run(["rg", pattern, path], capture_output=True).stdout
    return truncate_output(raw, max_chars=30_000, strategy="tail")
```

Strategies: `head` (keep first N chars), `tail` (keep last N), `head_tail` (keep both ends with `... truncated ...` in middle).

Without this, a single `grep` on a large codebase blows the entire context window. Every reference repo that works in practice (pi-mono, opencode, gemini-cli) has this.

### 5.3 Built-in Tools

| Tool | Presets | Source | Notes |
|---|---|---|---|
| `bash` | coding, assistant | Lift from TUI `terminal` | Timeout, truncation |
| `read` | coding, assistant | Lift from TUI `read_file` | Line range support |
| `write` | coding, assistant | Lift from TUI `write_file` | |
| `edit` | coding | Lift from TUI `edit_file` | |
| `grep` | coding | New | ripgrep-backed, truncated |
| `glob` | coding | New | Glob patterns + directory listing |

**Not in M1:** web_search, web_fetch, memory. These come in M3. We ship what we can test without API keys first.

---

## 6. Sessions (M2)

### Format: Append-only JSONL

Each session is a `.jsonl` file in `~/.isotopes/sessions/`:

```jsonl
{"type":"session_start","id":"abc123","timestamp":"...","model":"claude-sonnet-4-20250514","preset":"coding"}
{"type":"user_message","content":"fix the auth bug"}
{"type":"assistant_message","content":"I'll look at...","usage":{"input":1200,"output":340}}
{"type":"tool_call","name":"bash","arguments":{"command":"grep -r 'auth' src/"}}
{"type":"tool_result","name":"bash","output":"...","is_error":false}
{"type":"assistant_message","content":"Found the issue..."}
{"type":"compaction","summary":"...","files_read":["src/auth.py"],"files_modified":["src/auth.py"]}
```

**Why JSONL over JSON:**
- Crash-safe — append-only, no full-rewrite
- Streamable — tail -f, pipe to tools
- Forkable — copy file, append from fork point (future)
- Simple — one line per event, easy to parse

**Why not SQLite:** Overkill for v1. JSONL covers our needs. If we need querying later, we can add an index layer without changing the storage format.

---

## 7. Context Compaction (M3)

### File-Aware Summarization

When context exceeds the model's window, compaction kicks in:

1. **Track file operations** — record which files were read/modified across the session
2. **Serialize conversation** — format recent turns for summarization
3. **LLM summarization** — ask the model to summarize, preserving:
   - Current task and progress
   - Files read and modified (with paths)
   - Key decisions made
   - Errors encountered and resolved
4. **Replace old messages** — swap compacted portion with summary message
5. **Log compaction entry** — append to JSONL with file lists

This mirrors pi-mono's branch-based compaction. The file tracking is critical — without it, the agent forgets what it was working on after compaction.

```python
@dataclass
class CompactionResult:
    summary: str
    files_read: list[str]
    files_modified: list[str]
    messages_compacted: int
    tokens_saved: int
```

---

## 8. Loop Detection (M2)

Simple but essential. Detect when the agent is stuck:

```python
# In the agent loop, track recent tool calls
if same_tool_call_repeated(last_n=3):
    inject_steering("You appear to be repeating the same action. Try a different approach.")
```

Rules:
- Same tool + same arguments 3x in a row → inject steering message
- Same tool 5x in a row (any args) → warn user
- Configurable thresholds via `AgentLoopConfig`

Gemini CLI and OpenCode both have this. Prevents burning tokens on infinite loops.

---

## 9. RPC Protocol (M4)

### Stdin/stdout JSONL

Commands (stdin → agent):

```jsonl
{"id":"1","type":"prompt","content":"fix the bug","images":[]}
{"id":"2","type":"steer","content":"actually focus on auth.py"}
{"id":"3","type":"follow_up","content":"now add tests"}
{"id":"4","type":"abort"}
{"id":"5","type":"get_state"}
{"id":"6","type":"set_model","model":"claude-sonnet-4-20250514"}
{"id":"7","type":"compact"}
{"id":"8","type":"new_session"}
```

Events (agent → stdout):

```jsonl
{"type":"agent_start","stream_id":"s1"}
{"type":"text_delta","stream_id":"s1","content":"I'll look at..."}
{"type":"tool_call_start","stream_id":"s1","name":"bash","arguments":{"command":"grep -r 'bug' src/"}}
{"type":"tool_call_end","stream_id":"s1","name":"bash","output":"...","is_error":false}
{"type":"agent_end","stream_id":"s1","usage":{"input":1200,"output":340}}
{"type":"state","model":"claude-sonnet-4-20250514","preset":"coding","session_id":"abc123"}
```

**Design notes:**
- Every command has an optional `id` for request-response correlation
- Events carry `stream_id` to correlate with the agent activity that produced them
- Maps directly to isotopes-core's existing `AgentEvent` types
- Extensible — new command/event types added without breaking existing consumers

This enables: macOS/iOS app embedding, VS Code extension, web UI backend, CI scripting.

---

## 10. Skills & Extensions (M4)

### Skills (AgentSkills Spec)

Isotope adopts the [AgentSkills spec](https://agentskills.io). Restrained implementation:

- At startup, scan configured directories, read SKILL.md **frontmatter only** (name + description)
- When user request matches a skill description, agent loads full SKILL.md instructions
- Skill tools (if any) registered with the agent
- References loaded on demand

```yaml
# ~/.isotopes/config.yaml
skills:
  - ~/.isotopes/skills/github/
  - ~/.isotopes/skills/docker/
```

**isotopes-core stays skill-unaware.** isotopes owns the loader.

### Extensions

**Not building a plugin system in M4.** Instead, we provide hooks:

- MCP client — load tools from MCP servers (via `mcp` package)
- `tools:` config — register additional tools by module path
- `beforeToolCall` / `afterToolCall` — already in isotopes-core middleware

A formal extension API (lifecycle hooks, custom commands, UI components) is post-v1. We don't know what the right API looks like yet — better to wait until we have real extension use cases.

---

## 11. Dependencies

### isotopes-core

```toml
[project]
dependencies = ["pydantic>=2.0"]

[project.optional-dependencies]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.40"]
tiktoken = ["tiktoken>=0.7"]
all = ["isotopes-core[openai,anthropic,tiktoken]"]
```

### isotopes

```toml
[project]
dependencies = ["isotopes-core>=0.1.1"]

[project.optional-dependencies]
tui = ["prompt-toolkit>=3.0", "rich>=13.0"]
search = ["httpx>=0.27"]
mcp = ["mcp>=1.0"]
all = ["isotopes[tui,search,mcp]"]

[project.scripts]
isotope = "isotopes.cli:main"
```

### Workspace root

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

---

## 12. Milestones

### M0: Core Migration

**Goal:** Migrate isotopes-core into the mono-repo. No new features.

- [ ] Set up uv workspace with `packages/isotopes-core/` and `packages/isotopes/` (stub)
- [ ] Migrate all isotopes-core source, tests, docs
- [ ] Migrate `pyproject.toml` (strip TUI extras)
- [ ] Move `tui/` temporarily (consumed by M1)
- [ ] Root `pyproject.toml` with workspace config
- [ ] Verify: `uv run pytest`, `ruff check`, `mypy` all pass
- [ ] Update README.md
- [ ] Archive `GhostComplex/isotopes-core` repo

**Ship:** Mono-repo works. All tests pass. Zero functional changes.

---

### M1: Lift + Modularize + Ship

**Goal:** Working CLI agent with modular tools and presets.

- [ ] `@tool` decorator in isotopes-core (schema from type hints + docstring)
- [ ] Lift TUI → `isotopes/tui/` (app.py, input.py, output.py, commands.py)
- [ ] Extract tools → `isotopes/tools/` (bash, read, write, edit)
- [ ] Tool output truncation utility (`truncate_output()`)
- [ ] New tools: `GrepTool`, `GlobTool`
- [ ] Preset system (`coding`, `assistant`, `minimal`)
- [ ] Agent class wrapping isotopes-core with preset-based tool registration
- [ ] CLI: `isotopes chat` (TUI) + `isotopes run "prompt"` (print mode)
- [ ] `--preset` flag
- [ ] Remove `tui/` from isotopes-core
- [ ] Tests
- [ ] PyPI release

**Ship:** `pip install isotopes[tui]` → `isotopes chat --preset coding` works with all existing features + grep/glob + truncation.

---

### M2: Sessions + Rich Output + Robustness

**Goal:** Persistent sessions, polished output, loop safety.

- [ ] JSONL session persistence (`~/.isotopes/sessions/`)
- [ ] Session listing (`isotopes sessions` / `/sessions`)
- [ ] Session resume (`isotopes chat --session <id>`)
- [ ] Auto-save on exit
- [ ] Markdown rendering with rich
- [ ] Syntax highlighting for code blocks
- [ ] Loop detection (repeated tool calls → steering injection)
- [ ] Config file (`~/.isotopes/config.yaml`)

**Ship:** Sessions persist. Output looks good. Agent doesn't get stuck in loops.

---

### M3: Compaction + Web Tools

**Goal:** Handle long sessions. Add web capabilities.

- [ ] File-aware context compaction (track reads/writes across compactions)
- [ ] `WebSearchTool` (Brave/SerpAPI via httpx)
- [ ] `WebFetchTool` (URL content extraction)
- [ ] Improved system prompt engineering

**Ship:** Long coding sessions don't overflow. Web search works.

---

### M4: RPC + Skills + MCP

**Goal:** Embeddable agent. Skill loading. External tools via MCP.

- [ ] RPC mode (JSONL stdin/stdout, commands listed in §9)
- [ ] `isotopes rpc` command
- [ ] Skill loader (AgentSkills spec, frontmatter scan + lazy load)
- [ ] MCP client (load tools from MCP servers)
- [ ] `tools:` config (register tools by module path)
- [ ] Documentation

**Ship:** `isotopes rpc` works for embedding. Skills loadable from directories. MCP tools loadable.

---

## 13. What We're NOT Building (Yet)

Logged for post-v1. We don't build these until there's real demand:

- Extension/plugin API (wait for use cases)
- Daemon mode
- A2A protocol
- Multi-agent orchestration
- OS-level sandboxing (Seatbelt/bwrap)
- Tool confirmation system (allow/deny/ask)
- Model-aware tool filtering
- Apple tools (Calendar, Mail, Reminders)
- Native macOS/iOS app (RPC enables this, app itself is separate)
- Web UI
- Local models (MLX)

---

## 14. Design Decisions Log

Decisions made during PRD development, for future reference:

| Decision | Rationale | Alternatives Considered |
|---|---|---|
| Mono-repo | Atomic cross-package changes, single CI, simpler onboarding | Separate repos (rejected: too much version coordination) |
| JSONL sessions | Crash-safe, append-only, streamable, forkable | JSON files (rejected: full-rewrite on save), SQLite (rejected: overkill for v1) |
| `@tool` decorator | Best Python DX — auto-schema from type hints | Manual JSON schema only (rejected: tedious), TypeBox-like (rejected: not Pythonic) |
| No extension API in v1 | Don't know the right API yet — hooks + MCP + config covers 80% | Full plugin system (rejected: premature abstraction) |
| RPC in M4 not M1 | Need stable tool/session APIs before exposing them via RPC | RPC in M1 (rejected: API too unstable) |
| File-aware compaction | Agent forgets file context after naive summarization | Simple summarization (rejected: loses file tracking) |
| Tools in isotopes | Keep isotopes-core generic — tool implementations are opinionated | Tools in core (rejected: core should stay minimal) |
