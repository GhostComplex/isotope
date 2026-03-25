# Isotope — PRD v5

**A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.**

---

## 1. What Is Isotope

A **mono-repo** containing two Python packages:

| Package | Location | Role |
|---|---|---|
| `isotope-core` | `packages/isotope-core/` | LLM providers, agent loop, middleware, events, context |
| `isotope-agents` | `packages/isotope-agents/` | Agent framework: tools, TUI, sessions, RPC, extensions, presets |

`isotope-core` already exists as a standalone repo (`GhostComplex/isotope-core`, 5.3k LoC, 97% test coverage, async, Pydantic v2). **M0 migrates it into this mono-repo.**

`isotope-agents` builds on top — and starts with existing TUI code from isotope-core.

Isotope is **role-agnostic**. It ships a set of decoupled tools and preset configurations. Users choose (or create) a preset that defines the agent's role:

```yaml
# ~/.isotope/config.yaml
preset: coding        # or: assistant, researcher, custom

# Presets define: system prompt, enabled tools, behavior
# Users can override any preset setting
```

### Built-in Presets

| Preset | System Prompt | Tools | Use Case |
|---|---|---|---|
| `coding` | "You are a coding agent..." | bash, read, write, edit, grep, glob | Software development |
| `assistant` | "You are a personal assistant..." | bash, read, write, web_search, web_fetch, memory | General tasks, research |
| `minimal` | (none) | (none) | Bare LLM, user adds tools via extensions/MCP |

Users can create custom presets or extend existing ones. The tool system is fully pluggable — add tools via Python API, config file, or MCP servers.

---

## 2. Why Not Just Use Pi-mono

Pi-mono is TypeScript. We need Python because:

- Existing backend code depends on isotope-core (Python)
- Python AI/ML ecosystem is stronger (LangChain, MCP SDK, CrewAI, etc.)
- isotope-core is already built and battle-tested

We take pi-mono's **architecture** (it's good), not its code.

---

## 3. Starting Point

isotope-core already has a working TUI (`tui/main.py`, ~1060 LoC) with:

- ✅ Claude Code-style steering (type during streaming to redirect)
- ✅ prompt-toolkit integration (visible input prompt during streaming)
- ✅ Streaming event consumption with tool call display
- ✅ Slash commands (/tools, /model, /system, /clear, /history, /debug)
- ✅ Built-in tools: read_file, write_file, edit_file, terminal, get_current_time
- ✅ Follow-up queuing (/follow) and abort (/abort)

**Strategy:** Migrate isotope-core into this mono-repo (M0), split TUI into components, then extend (M1+).

---

## 4. Architecture

```
isotope (mono-repo)
├── packages/
│   ├── isotope-core/              ← migrated from GhostComplex/isotope-core
│   │   ├── src/isotope_core/
│   │   │   ├── agent.py           — stateful Agent wrapper
│   │   │   ├── loop.py            — agent loop (plan → act → observe → repeat)
│   │   │   ├── types.py           — Pydantic v2 types
│   │   │   ├── tools.py           — Tool framework
│   │   │   ├── events.py          — EventStream
│   │   │   ├── context.py         — token counting, pruning
│   │   │   ├── middleware.py       — composable middleware
│   │   │   └── providers/         — OpenAI, Anthropic, proxy, router
│   │   ├── tests/
│   │   └── pyproject.toml
│   │
│   └── isotope-agents/            ← new, builds on isotope-core
│       ├── src/isotope_agents/
│       │   ├── agent.py           — Agent wrapping isotope-core
│       │   ├── presets.py         — role configurations
│       │   ├── session.py         — session persistence
│       │   ├── compaction.py      — context compaction
│       │   ├── extensions.py      — plugin system
│       │   ├── config.py          — config file loading
│       │   ├── skills.py          — skill loader
│       │   ├── rpc.py             — stdin/stdout JSON protocol
│       │   ├── cli.py             — CLI entry point
│       │   ├── tui/
│       │   │   ├── app.py         — main TUI (from isotope-core tui/)
│       │   │   ├── input.py       — input handling (prompt-toolkit)
│       │   │   ├── output.py      — output rendering (rich)
│       │   │   └── commands.py    — slash command handlers
│       │   └── tools/
│       │       ├── bash.py        — from existing terminal tool
│       │       ├── read.py        — from existing read_file
│       │       ├── write.py       — from existing write_file
│       │       ├── edit.py        — from existing edit_file
│       │       ├── grep.py        — new (ripgrep-backed)
│       │       ├── glob.py        — new (glob patterns)
│       │       ├── web_search.py  — new (Brave/SerpAPI)
│       │       ├── web_fetch.py   — new (URL extraction)
│       │       └── memory.py      — new (persistent KV)
│       ├── tests/
│       └── pyproject.toml
│
├── docs/                          — shared docs (this PRD, etc.)
├── pyproject.toml                 — workspace root (uv workspace)
└── README.md
```

### How It Runs

```bash
# Interactive TUI with default preset
isotope chat

# Use a specific preset
isotope chat --preset coding
isotope chat --preset assistant

# One-shot
isotope run "fix the bug in auth.py" --preset coding

# Print mode (non-interactive, for scripting)
isotope run --print "summarize this document"

# RPC mode (for embedding in other apps)
isotope rpc
```

---

## 5. Package: isotope-core (migrated)

isotope-core moves into `packages/isotope-core/` with its full codebase:

- Agent loop (`loop.py`) — plan → act → observe → repeat, streaming events
- Providers (`providers/`) — OpenAI, Anthropic, proxy, router with circuit breaker
- Middleware (`middleware.py`) — composable chain (logging, token tracking, event filtering)
- Events (`events.py`) — typed async event stream
- Context (`context.py`) — token counting, pruning strategies, message pinning
- Types (`types.py`) — Pydantic v2 models for content, messages, events
- Tools (`tools.py`) — Tool class with JSON schema validation

The TUI (`tui/`) is **not** migrated as-is. It gets split into components and moved to isotope-agents during M1.

**What stays in isotope-core:**
- Everything above (agent loop, providers, middleware, events, context, tools, types)
- All existing tests (~20.5k LoC)
- `pyproject.toml` with current dependencies

**What gets removed from isotope-core:**
- `tui/` directory (code moves to isotope-agents)
- TUI-related optional dependencies (`prompt-toolkit` extra)
- TUI test (`test_tui_main.py`)

---

## 6. Package: isotope-agents

### 6.1 Tools

| Tool | Source | Presets | Status |
|---|---|---|---|
| `BashTool` | Existing `terminal` tool from TUI | coding, assistant | ✅ Lift & rename |
| `ReadTool` | Existing `read_file` from TUI | coding, assistant | ✅ Lift |
| `WriteTool` | Existing `write_file` from TUI | coding, assistant | ✅ Lift |
| `EditTool` | Existing `edit_file` from TUI | coding | ✅ Lift |
| `GrepTool` | New (ripgrep-backed) | coding | 🆕 Build |
| `GlobTool` / `LsTool` | New (glob patterns, directory listing) | coding | 🆕 Build |
| `WebSearchTool` | New (Brave/SerpAPI) | assistant | 🆕 Build |
| `WebFetchTool` | New (URL content extraction) | assistant | 🆕 Build |
| `MemoryTool` | New (persistent key-value memory) | assistant | 🆕 Build |

All tools are available to all presets — the table shows which presets enable them **by default**. Users can add/remove tools from any preset via config.

### 6.2 TUI

Existing features (lifted from isotope-core `tui/main.py`, split into components):

- ✅ Streaming response with event consumption → `tui/app.py`
- ✅ Claude Code-style steering (interrupt + redirect) → `tui/input.py`
- ✅ prompt-toolkit input during streaming → `tui/input.py`
- ✅ Follow-up queuing and abort → `tui/input.py`
- ✅ Slash commands → `tui/commands.py`
- ✅ Tool call display → `tui/output.py`
- ✅ Token usage display → `tui/output.py`

New features to add:

- 🆕 Markdown rendering (rich) → `tui/output.py`
- 🆕 Syntax highlighting for code blocks → `tui/output.py`
- 🆕 Session switching (/session, /sessions) → `tui/commands.py`
- 🆕 Config file loading → `config.py`

### 6.3 Sessions

- Session persistence (save/resume conversations)
- History compaction (LLM-based summarization when context overflows)
- Session listing and management
- Auto-save on exit

### 6.4 RPC Mode

Stdin/stdout JSON protocol for embedding in other applications:

```json
{"type": "prompt", "id": "1", "content": "fix the bug"}
{"type": "text_delta", "content": "I'll look at..."}
{"type": "tool_call", "name": "bash", "arguments": {"command": "grep -r 'bug' src/"}}
{"type": "tool_result", "name": "bash", "output": "..."}
{"type": "response", "id": "1", "success": true}
```

This enables: macOS/iOS app embedding, VS Code extension, web UI backend.

### 6.5 Skills (AgentSkills Spec)

Skills are packaged capabilities. Isotope adopts the [AgentSkills spec](https://agentskills.io).

```
skill-name/
├── SKILL.md              # Required: frontmatter + instructions
├── scripts/              # Optional
├── references/           # Optional
└── assets/               # Optional
```

- At startup, scan skill directories, read SKILL.md frontmatter (cheap)
- On match, load full instructions into context
- Register skill tools with the agent

**isotope-core stays skill-unaware; isotope-agents owns skill loading.**

### 6.6 Extensions

Plugin system: custom tools, custom prompts, MCP server integration, hooks.

---

## 7. Dependencies

### isotope-core (packages/isotope-core/pyproject.toml)

```toml
[project]
dependencies = ["pydantic>=2.0"]

[project.optional-dependencies]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.40"]
tiktoken = ["tiktoken>=0.7"]
all = ["isotope-core[openai,anthropic,tiktoken]"]
```

### isotope-agents (packages/isotope-agents/pyproject.toml)

```toml
[project]
dependencies = ["isotope-core>=0.1.0"]

[project.optional-dependencies]
tui = ["prompt-toolkit>=3.0", "rich>=13.0"]
search = ["httpx>=0.27"]
mcp = ["mcp>=1.0"]
all = ["isotope-agents[tui,search,mcp]"]

[project.scripts]
isotope = "isotope_agents.cli:main"
```

### Workspace root (pyproject.toml)

```toml
[tool.uv.workspace]
members = ["packages/*"]
```

---

## 8. Milestones

### M0: Core Migration (Week 0)

**Goal:** Migrate isotope-core into the mono-repo. Existing code, no new features.

- [ ] Set up uv workspace with `packages/isotope-core/` and `packages/isotope-agents/` (stub)
- [ ] Migrate all isotope-core source code (`src/isotope_core/`) into `packages/isotope-core/src/isotope_core/`
- [ ] Migrate all isotope-core tests (`tests/`) into `packages/isotope-core/tests/`
- [ ] Migrate `pyproject.toml` (strip TUI extras — they move to isotope-agents)
- [ ] Migrate isotope-core docs into `packages/isotope-core/docs/` (API.md, roadmap, milestone PRDs)
- [ ] Move `tui/` into `packages/isotope-core/tui/` temporarily (will be consumed by M1)
- [ ] Root `pyproject.toml` with uv workspace config
- [ ] Verify: `uv run pytest` passes for isotope-core (all existing tests green)
- [ ] Verify: `uv run ruff check` and `uv run mypy` pass
- [ ] Archive `GhostComplex/isotope-core` repo (add notice pointing to mono-repo)
- [ ] Update README.md

**Ship:** Mono-repo works. All isotope-core tests pass. No functional changes.

---

### M1: Lift + Modularize + Ship (Week 1)

**Goal:** Extract TUI code, modularize tools, add preset system, ship to PyPI.

- [ ] Create `packages/isotope-agents/` package structure
- [ ] Lift TUI code from `packages/isotope-core/tui/main.py` into `isotope_agents/tui/`
  - Split into: `app.py` (main loop), `input.py` (prompt-toolkit), `output.py` (rendering), `commands.py` (slash handlers)
- [ ] Extract inline tools into separate files:
  - `tools/bash.py` (from `terminal`)
  - `tools/read.py` (from `read_file`)
  - `tools/write.py` (from `write_file`)
  - `tools/edit.py` (from `edit_file`)
- [ ] Add `GrepTool` (ripgrep-backed)
- [ ] Add `GlobTool` / `LsTool`
- [ ] Preset system with `coding` and `assistant` presets
- [ ] Agent class wrapping isotope-core loop with preset-based tool registration
- [ ] CLI entry point: `isotope run "prompt"` (print mode) + `isotope chat` (TUI)
- [ ] `--preset` flag for CLI
- [ ] Remove `tui/` from isotope-core package (code now lives in isotope-agents)
- [ ] Tests
- [ ] PyPI release: `pip install isotope-agents`

**Ship:** `pip install isotope-agents[tui]` → `isotope chat --preset coding` works.

---

### M2: Sessions + Rich Output (Week 2)

**Goal:** Session persistence and improved output rendering.

- [ ] Session save/resume (JSON files in `~/.isotope/sessions/`)
- [ ] Session listing (`isotope sessions`)
- [ ] Session switching (/session command)
- [ ] Auto-save on exit
- [ ] Markdown rendering with rich
- [ ] Syntax highlighting for code blocks
- [ ] Configuration file (`~/.isotope/config.yaml`)

**Ship:** Multi-turn sessions persist across restarts. Output is properly formatted.

---

### M3: Compaction + Web Tools (Week 3)

**Goal:** Handle long sessions and add web capabilities.

- [ ] Context compaction (LLM-based summarization on overflow)
- [ ] WebSearchTool (Brave/SerpAPI)
- [ ] WebFetchTool (URL content extraction)
- [ ] Improved system prompt engineering
- [ ] Error handling and recovery

**Ship:** Long sessions don't overflow. Web tools work.

---

### M4: RPC + Skills + Extensions (Week 4)

**Goal:** Embeddable agent with skills and plugin system.

- [ ] RPC mode (stdin/stdout JSON protocol)
- [ ] Skill loader (AgentSkills spec)
- [ ] Extension system
- [ ] MCP client
- [ ] `isotope rpc` command
- [ ] Documentation

**Ship:** Skills loadable. Other apps can spawn `isotope rpc` and interact via JSON.

---

## 9. Future (Post-v1)

- Daemon mode (always-on background process)
- A2A protocol (agent-to-agent)
- Multi-agent orchestration
- OS-level sandboxing (Seatbelt/bwrap)
- Apple tools (Calendar, Mail, Reminders)
- Native macOS/iOS app
- Web UI
- Tool confirmation system (allow/deny)
- Local models (MLX)
