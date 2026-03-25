# Isotope — PRD v4

**A Python coding agent — isotope-core powered, pi-mono inspired.**

---

## 1. What Is Isotope

Two Python packages:

| Package | Role | Equivalent |
|---|---|---|
| `isotope-core` | LLM providers, agent loop, middleware, events, context | `pi-ai` + `pi-agent-core` |
| `isotope-agents` | Coding agent, tools, TUI, sessions, RPC, extensions | `pi-coding-agent` |

`isotope-core` already exists (5.3k LoC, 97% test coverage, async, Pydantic v2).
`isotope-agents` is the product to build.

---

## 2. Why Not Just Use Pi-mono

Pi-mono is TypeScript. We need Python because:

- Existing backend code depends on isotope-core (Python)
- Python AI/ML ecosystem is stronger (LangChain, MCP SDK, CrewAI, etc.)
- isotope-core is already built and battle-tested

We take pi-mono's **architecture** (it's good), not its code.

---

## 3. Architecture

```
isotope-agents (the product)
├── Agent         — coding agent with tool calling
├── Tools         — bash, read, write, edit, grep, glob, web search, web fetch
├── TUI           — interactive terminal UI (prompt-toolkit + rich)
├── Sessions      — session management, history, compaction
├── RPC           — stdin/stdout JSON protocol for embedding
└── Extensions    — plugin system for custom tools/behaviors

         │
         │ depends on
         ▼

isotope-core (exists)
├── Agent loop    — plan → act → observe → repeat
├── Providers     — OpenAI, Anthropic, proxy, router
├── Middleware    — composable request/response transforms
├── Events        — typed async event system
└── Context       — messages, token counting, overflow handling
```

### How It Runs

```
# Interactive TUI (primary mode)
isotope chat

# One-shot
isotope run "fix the bug in auth.py"

# Print mode (non-interactive, for scripting)
isotope run --print "explain this codebase"

# RPC mode (for embedding in other apps)
isotope rpc
```

---

## 4. Package: isotope-agents

### 4.1 Tools

| Tool | Description | Reference |
|---|---|---|
| `BashTool` | Execute shell commands | pi: `bash.ts` |
| `ReadTool` | Read file contents | pi: `read.ts` |
| `WriteTool` | Write/create files | pi: `write.ts` |
| `EditTool` | Search & replace editing | pi: `edit.ts` |
| `GrepTool` | Search file contents (ripgrep) | pi: `grep.ts` |
| `GlobTool` / `LsTool` | List files, glob patterns | pi: `ls.ts`, `find.ts` |
| `WebSearchTool` | Web search | — |
| `WebFetchTool` | Fetch URL content | — |

### 4.2 TUI

Interactive terminal interface using `prompt-toolkit` + `rich`:

- Streaming response display with markdown rendering
- Multi-line input with history
- Tool call visualization (expandable)
- Session switching
- Keybindings (Ctrl+C cancel, Ctrl+D exit, etc.)
- Syntax highlighting for code blocks

### 4.3 Sessions

- Session persistence (save/resume conversations)
- History compaction (LLM-based summarization when context overflows)
- Session listing and management
- Auto-save on exit

### 4.4 RPC Mode

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

### 4.5 Extensions

Plugin system for extending the agent:

- Custom tools (register via Python API)
- Custom system prompts / personas
- MCP server integration (load tools from MCP)
- Hooks (before/after tool call, before/after LLM call)

---

## 5. Project Structure

```
isotope/                          # monorepo
├── packages/
│   └── agents/
│       └── src/isotope_agents/
│           ├── agent.py          # Main agent class
│           ├── session.py        # Session management
│           ├── compaction.py     # Context compaction
│           ├── extensions.py     # Extension/plugin system
│           ├── rpc.py            # RPC stdin/stdout mode
│           ├── cli.py            # CLI entry point
│           ├── tui/
│           │   ├── app.py        # TUI application
│           │   ├── input.py      # Input handling
│           │   └── output.py     # Output rendering
│           └── tools/
│               ├── bash.py
│               ├── read.py
│               ├── write.py
│               ├── edit.py
│               ├── grep.py
│               ├── glob.py
│               ├── web_search.py
│               └── web_fetch.py
├── pyproject.toml                # Workspace config
└── README.md
```

`isotope-core` remains in its own repo (`GhostComplex/isotopo-core`).

---

## 6. Dependencies

```toml
[project]
dependencies = [
    "isotope-core>=0.1.0",         # Our agent engine
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

## 7. Milestones

### M1: Agent + Tools (Week 1)

**Goal:** Working coding agent with core tools. Ship to PyPI.

- [ ] Agent class wrapping isotope-core loop
- [ ] BashTool, ReadTool, WriteTool, EditTool
- [ ] GrepTool, GlobTool
- [ ] Tool output truncation (large outputs)
- [ ] System prompt with tool instructions
- [ ] Basic CLI: `isotope run "prompt"` (print mode, non-interactive)
- [ ] Tests
- [ ] PyPI release: `pip install isotope-agents`

**Ship:** `pip install isotope-agents` → `isotope run --print "list all Python files and count lines"` works.

---

### M2: TUI + Sessions (Week 2)

**Goal:** Interactive terminal experience with session persistence. Ship update to PyPI.

- [ ] Interactive TUI with streaming display
- [ ] Multi-line input, history, keybindings
- [ ] Markdown rendering in terminal
- [ ] Tool call display (show what tools are doing)
- [ ] Session save/resume
- [ ] Session listing (`isotope sessions`)
- [ ] `isotope chat` command

**Ship:** `pip install --upgrade isotope-agents` → `isotope chat` works with multi-turn, sessions persist.

---

### M3: Compaction + Web Tools (Week 3)

**Goal:** Handle long sessions and add web capabilities. Ship update to PyPI.

- [ ] Context compaction (LLM-based summarization on overflow)
- [ ] WebSearchTool (Brave/SerpAPI)
- [ ] WebFetchTool (URL content extraction)
- [ ] Improved system prompt engineering
- [ ] Error handling and recovery (tool failures, API errors)
- [ ] Configuration file (`~/.isotope/config.yaml`)

**Ship:** Long coding sessions don't overflow. Web search and fetch work.

---

### M4: RPC + Extensions (Week 4)

**Goal:** Embeddable agent with plugin system. Ship update to PyPI.

- [ ] RPC mode (stdin/stdout JSON protocol)
- [ ] Extension system (custom tools, hooks)
- [ ] MCP client (load tools from MCP servers)
- [ ] `isotope rpc` command
- [ ] Documentation

**Ship:** Other apps can spawn `isotope rpc` and interact via JSON. MCP tools loadable.

---

## 8. Future (Post-v1)

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

---
