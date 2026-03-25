# Isotope — PRD v4

**A pluggable Python agent framework — configure it as a coding agent, personal assistant, or anything in between.**

---

## 1. What Is Isotope

Two Python packages:

| Package | Role |
|---|---|
| `isotope-core` | LLM providers, agent loop, middleware, events, context |
| `isotope-agents` | Agent framework: tools, TUI, sessions, RPC, extensions, presets |

`isotope-core` already exists (5.3k LoC, 97% test coverage, async, Pydantic v2).
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

**Strategy:** Lift this code into isotope-agents, modularize, then extend.

---

## 4. Architecture

```
isotope-agents (the framework)
├── Agent         — agent wrapping isotope-core loop
├── Presets       — role configurations (coding, assistant, minimal, custom)
├── Tools         — modularized from existing TUI + new tools
│   ├── Existing  — bash (terminal), read_file, write_file, edit_file
│   └── New       — grep, glob/ls, web_search, web_fetch, memory
├── TUI           — lifted from isotope-core tui/main.py
│   ├── Existing  — streaming, steering, slash commands, prompt-toolkit
│   └── New       — markdown rendering (rich), session switching
├── Sessions      — session persistence, history, compaction
├── RPC           — stdin/stdout JSON protocol for embedding
└── Extensions    — plugin system for custom tools/behaviors

         │
         │ depends on
         ▼

isotope-core (exists, separate repo)
├── Agent loop    — plan → act → observe → repeat
├── Providers     — OpenAI, Anthropic, proxy, router
├── Middleware    — composable request/response transforms
├── Events        — typed async event system
└── Context       — messages, token counting, overflow handling
```

### How It Runs

```
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

## 5. Package: isotope-agents

### 5.1 Tools

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

### 5.2 TUI

Existing features (from isotope-core `tui/main.py`):

- ✅ Streaming response with event consumption
- ✅ Claude Code-style steering (interrupt + redirect)
- ✅ prompt-toolkit input during streaming
- ✅ Follow-up queuing and abort
- ✅ Slash commands (/tools, /model, /system, /clear, /history, /debug)
- ✅ Tool call display (`[calling tool_name]`)
- ✅ Token usage display

New features to add:

- 🆕 Markdown rendering (rich)
- 🆕 Syntax highlighting for code blocks
- 🆕 Session switching (/session, /sessions)
- 🆕 Config file loading (`~/.isotope/config.yaml`)

### 5.3 Sessions

- Session persistence (save/resume conversations)
- History compaction (LLM-based summarization when context overflows)
- Session listing and management
- Auto-save on exit

### 5.4 RPC Mode

Stdin/stdout JSON protocol for embedding in other applications:

```json
// Input (command)
{"type": "prompt", "id": "1", "content": "fix the bug"}

// Output (events)
{"type": "text_delta", "content": "I'll look at..."}
{"type": "tool_call", "name": "bash", "arguments": {"command": "grep -r 'bug' src/"}}
{"type": "tool_result", "name": "bash", "output": "..."}
{"type": "response", "id": "1", "success": true}
```

This enables:
- macOS/iOS app embedding (spawn process, talk JSON)
- VS Code extension
- Web UI backend
- Any app that wants to embed an agent

### 5.5 Skills (AgentSkills Spec)

Skills are packaged capabilities — tools + instructions + context files. Isotope adopts the [AgentSkills spec](https://agentskills.io) (same format as Claude/OpenClaw).

```
skill-name/
├── SKILL.md              # Required: frontmatter (name, description) + instructions
├── scripts/              # Optional: executable code (Python/Bash)
├── references/           # Optional: docs loaded on demand
└── assets/               # Optional: files used in output (templates, etc.)
```

**How it works:**

1. At startup, agent scans all configured skill directories and reads SKILL.md **frontmatter only** (name + description) — cheap, just metadata
2. When a user request matches a skill's description, the agent loads the full SKILL.md instructions into context
3. The skill's tools (if any) are registered with the agent
4. References are loaded on demand (the SKILL.md tells the agent when to read them)

**Configuration:**

```yaml
# ~/.isotope/config.yaml
preset: coding
skills:
  - ~/.isotope/skills/github/
  - ~/.isotope/skills/docker/
  - /path/to/custom-skill/
```

**Skill ↔ isotope-core boundary:**

- isotope-core knows `Tool(name, schema, execute)` — nothing about skills
- isotope-agents owns the skill loader, discovery, instruction injection, and tool registration
- This keeps core lean and skill-unaware

### 5.6 Extensions

Plugin system for extending the agent beyond skills:

- Custom tools (register via Python API)
- Custom system prompts / personas
- MCP server integration (load tools from MCP)
- Hooks (before/after tool call, before/after LLM call)

---

## 6. Project Structure

```
isotope/                          # this repo
├── src/isotope_agents/
│   ├── __init__.py
│   ├── agent.py                  # Agent class wrapping isotope-core
│   ├── presets.py                # Built-in preset definitions
│   ├── session.py                # Session management
│   ├── compaction.py             # Context compaction
│   ├── extensions.py             # Extension/plugin system
│   ├── config.py                 # Config file loading
│   ├── skills.py                 # Skill loader (AgentSkills spec)
│   ├── rpc.py                    # RPC stdin/stdout mode
│   ├── cli.py                    # CLI entry point
│   ├── tui/
│   │   ├── app.py                # Main TUI (lifted from isotope-core)
│   │   ├── input.py              # Input handling (prompt-toolkit)
│   │   ├── output.py             # Output rendering (rich)
│   │   └── commands.py           # Slash command handlers
│   └── tools/
│       ├── __init__.py           # Tool registry
│       ├── bash.py               # ✅ from existing terminal tool
│       ├── read.py               # ✅ from existing read_file
│       ├── write.py              # ✅ from existing write_file
│       ├── edit.py               # ✅ from existing edit_file
│       ├── grep.py               # 🆕
│       ├── glob.py               # 🆕
│       ├── web_search.py         # 🆕
│       ├── web_fetch.py          # 🆕
│       └── memory.py             # 🆕
├── tests/
├── pyproject.toml
└── README.md
```

`isotope-core` remains in its own repo (`GhostComplex/isotopo-core`).

---

## 7. Dependencies

```toml
[project]
dependencies = [
    "isotope-core>=0.1.0",
]

[project.optional-dependencies]
tui = [
    "prompt-toolkit>=3.0",
    "rich>=13.0",
]
search = ["httpx>=0.27"]
mcp = ["mcp>=1.0"]
all = ["isotope-agents[tui,search,mcp]"]

[project.scripts]
isotope = "isotope_agents.cli:main"
```

---

## 8. Milestones

### M1: Lift + Modularize + Ship (Week 1)

**Goal:** Extract existing code, modularize, add preset system, ship to PyPI.

- [ ] Lift TUI code from `isotope-core/tui/main.py` into `isotope_agents/tui/`
- [ ] Extract inline tools into separate files (`tools/bash.py`, `tools/read.py`, etc.)
- [ ] Add GrepTool (ripgrep-backed)
- [ ] Add GlobTool / LsTool
- [ ] Preset system with `coding` and `assistant` presets
- [ ] Agent class wrapping isotope-core loop with preset-based tool registration
- [ ] CLI entry point: `isotope run "prompt"` (print mode) + `isotope chat` (TUI)
- [ ] `--preset` flag for CLI
- [ ] Tests
- [ ] PyPI release: `pip install isotope-agents`

**Ship:** `pip install isotope-agents[tui]` → `isotope chat --preset coding` works with all existing TUI features + grep/glob tools. `isotope chat --preset assistant` works with web/memory tools.

---

### M2: Sessions + Rich Output (Week 2)

**Goal:** Session persistence and improved output rendering. Ship update.

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

**Goal:** Handle long sessions and add web capabilities. Ship update.

- [ ] Context compaction (LLM-based summarization on overflow)
- [ ] WebSearchTool (Brave/SerpAPI)
- [ ] WebFetchTool (URL content extraction)
- [ ] Improved system prompt engineering
- [ ] Error handling and recovery (tool failures, API errors)

**Ship:** Long coding sessions don't overflow. Web search and fetch work.

---

### M4: RPC + Skills + Extensions (Week 4)

**Goal:** Embeddable agent with skills and plugin system. Ship update.

- [ ] RPC mode (stdin/stdout JSON protocol)
- [ ] Skill loader (scan SKILL.md frontmatter, lazy-load instructions)
- [ ] Skill → Tool registration bridge
- [ ] Skill → System prompt injection
- [ ] `skills:` config support
- [ ] Extension system (custom tools, hooks)
- [ ] MCP client (load tools from MCP servers)
- [ ] `isotope rpc` command
- [ ] Documentation

**Ship:** Skills loadable from local directories. Other apps can spawn `isotope rpc` and interact via JSON. MCP tools loadable.

---

## 9. Future (Post-v1)

Things we're **not building now** but may add later:

- Daemon mode (always-on background process)
- A2A protocol (agent-to-agent)
- Multi-agent orchestration
- OS-level sandboxing (Seatbelt/bwrap)
- Apple tools (Calendar, Mail, Reminders)
- Native macOS/iOS app
- Web UI
- Tool confirmation system (allow/deny)
- Local models (MLX)

These are logged in the backlog repo for when the time comes.
