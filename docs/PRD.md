# Isotope — PRD

**A daemon-first AI agent platform with native Apple integration.**

---

## 1. What Is Isotope

Isotope is a TypeScript monorepo that provides:

1. A **reusable agent engine** (loop, providers, middleware, tools)
2. A **headless daemon** that any frontend can connect to via HTTP + Unix socket
3. A **native macOS/iOS app** as the primary product surface
4. Deep **Apple OS integration** (Calendar, Mail, Reminders, Shortcuts, etc.)

It is **not** a chatbot, not a TUI-first tool, not a Python library. It is a product — a personal AI agent that lives on your devices.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  PRODUCTS (platform-specific UX)                        │
│                                                         │
│  macOS/iOS App    Web Dashboard     CLI (optional)      │
│  (Swift)          (React, P2)       (TS, thin client)   │
│       │                │                 │              │
│       └────────────────┼─────────────────┘              │
│                        │  same HTTP + Unix socket API   │
├────────────────────────┼────────────────────────────────┤
│  PLATFORM EXTENSIONS   │                                │
│                        │                                │
│  isotope-apple-tools (Swift package)                    │
│  Calendar, Mail, Reminders, Contacts, Shortcuts, etc.   │
│  Exposed via local HTTP bridge                          │
│       │                                                 │
│       │  register as tools                              │
├───────┼─────────────────────────────────────────────────┤
│  INFRASTRUCTURE (cross-platform, headless, TypeScript)  │
│       │                                                 │
│  ┌────▼──────────────────────────────────────────────┐  │
│  │  @isotope/daemon                                  │  │
│  │  HTTP + Unix socket server, SSE streaming,        │  │
│  │  fire-and-forget tasks, session management        │  │
│  ├───────────────────────────────────────────────────┤  │
│  │  @isotope/agents                                  │  │
│  │  ToolAgent, MultiAgent, built-in tools (13+),     │  │
│  │  tool confirmation, sandbox, ShellAgentTool,      │  │
│  │  MCP client, A2A client/server, memory, planning  │  │
│  ├───────────────────────────────────────────────────┤  │
│  │  @isotope/core                                    │  │
│  │  Agent loop, LLM providers, middleware pipeline,  │  │
│  │  event system, context management                 │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Monorepo Structure

```
isotope/
├── packages/
│   ├── core/              # Agent loop, providers, middleware, events
│   ├── agents/            # ToolAgent, MultiAgent, tools, sandbox, confirmation
│   ├── daemon/            # HTTP + Unix socket server, SSE, task management
│   └── cli/               # Optional CLI client (thin daemon client)
├── apps/
│   └── web/               # Web dashboard (React, P2)
├── docs/
│   └── PRD.md             # This file
├── package.json           # Workspace root (pnpm)
├── turbo.json             # Build orchestration
└── README.md
```

Swift repos (separate, different build system):
- `isotope-apple-tools` — Swift package, Apple framework tools + HTTP bridge
- `isotope-app` — SwiftUI macOS/iOS/iPadOS app

---

## 3. Key Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **TypeScript monorepo** | Unified language for core → agents → daemon → web → CLI. Bun-compatible. One CI pipeline. |
| 2 | **Daemon-first** | Headless daemon is the product surface. All frontends (macOS app, web, CLI) are thin API clients. |
| 3 | **No CodeAgent** | Claude Code, Gemini CLI, Codex already exist. Wrap them as tools via `ShellAgentTool` or A2A. |
| 4 | **OS-level sandboxing** | macOS Seatbelt (`sandbox-exec` + SBPL profiles) + Linux bwrap + seccomp BPF. Lighter than Docker, Apple-native. |
| 5 | **Tool confirmation** | Human-in-the-loop: allow-once / allow-always / deny per tool. From Gemini CLI research. |
| 6 | **A2A protocol** | Both client (call external agents) and server (expose isotope agents). First-class, not bolted on. |
| 7 | **Swift ↔ TS bridge via HTTP** | Simple, debuggable. Apple tools run as local HTTP server, daemon calls them like any tool. |
| 8 | **isotope-core as reference** | Original Python isotope-core (5.3k LoC) is the architectural blueprint. Rewritten in TS for unified stack. |
| 9 | **Infra-first** | Python layers are headless, no UX opinions. Any frontend connects via the same daemon API. |

---

## 4. Package Details

### 4.1 `@isotope/core`

The agent loop engine. Ported from the Python isotope-core (5.3k LoC, 97% test coverage).

**Owns:**
- Agent loop (plan → act → observe → repeat)
- LLM provider abstraction (OpenAI, Anthropic, GitHub Copilot API, proxy/router)
- Middleware pipeline (composable request/response transforms)
- Event system (typed, async event emitter for the full loop lifecycle)
- Context management (messages, token counting, context window overflow)

**Does not own:** Tools, agents, daemon, CLI. Pure engine.

**Target:** <3k LoC (excluding tests).

### 4.2 `@isotope/agents`

Agent types, tools, and integrations. Builds on `@isotope/core`.

**Owns:**
- **ToolAgent** — standard tool-calling agent wrapping core's loop
- **MultiAgent** — manager delegates to worker agents
- **Built-in tools:**

| Tool | Description | Priority |
|---|---|---|
| `FinalAnswer` | Terminates agent loop with result | P0 |
| `Shell` | Execute shell commands | P0 |
| `FileRead` | Read file contents | P0 |
| `FileWrite` | Write/create files | P0 |
| `FileEdit` | Diff-based editing (search & replace) | P0 |
| `Glob` / `Ls` | List files, glob patterns | P0 |
| `Grep` | Search file contents (ripgrep-backed) | P0 |
| `WebSearch` | Web search (Brave/SerpAPI/Tavily) | P0 |
| `WebFetch` | Fetch and extract content from URLs | P0 |
| `AskUser` | Pause for human input | P0 |
| `Memory` | Session memory read/write | P1 |
| `ShellAgent` | Wrap CLI agents as tools (Claude Code, Gemini CLI, Codex) | P1 |
| `Todo` | Task management within a session | P2 |

- **Tool confirmation system** (allow-once / allow-always / deny)
- **Sandbox** (`SandboxPolicy` with OS backend for Seatbelt/bwrap, Docker backend optional)
- **Tool registry** (register/discover tools at runtime, including from HTTP bridges)
- **MCP client** (load tools from MCP servers)
- **A2A client** (delegate tasks to external A2A agents)
- **A2A server** (expose isotope agents as A2A services)
- **Agent-Tool bridge** (wrap any A2A agent as an isotope tool)
- **ShellAgent bridge** (wrap Claude Code / Gemini CLI / Codex)
- **Memory** (structured conversation history, persistence)
- **Planning** (optional plan → act → re-plan loop)
- **Context compression** (LLM-based summarization on overflow)
- **Pre-built middleware** (logging, token budget, safety, retry, telemetry)

### 4.3 `@isotope/daemon`

Headless HTTP + Unix socket server. The product surface.

**API:**

```
POST   /agents                    Create/configure agent
GET    /agents                    List agents
POST   /agents/:id/run           Submit task (fire-and-forget)
GET    /agents/:id/stream        SSE event stream
POST   /agents/:id/chat          Interactive message
POST   /agents/:id/steer         Mid-run steering
DELETE /agents/:id               Remove agent

GET    /sessions                  List sessions
GET    /sessions/:id             Session state + history
DELETE /sessions/:id             Cancel/cleanup

POST   /tasks                    Submit fire-and-forget task
GET    /tasks                    List tasks
GET    /tasks/:id                Task status + result

POST   /tools/register           Register external tools (HTTP bridge)
GET    /tools                    List registered tools
POST   /tools/mcp               Load tools from MCP server
POST   /tools/a2a               Load A2A agent as tool

GET    /.well-known/agent.json   A2A agent card
POST   /a2a/tasks               A2A task endpoint
```

**Features:**
- Unix socket (`/tmp/isotope.sock`) + HTTP (port 9200)
- SSE streaming for real-time events
- Fire-and-forget task queue
- Session management (create, resume, list, cleanup)
- Agent identity files (`~/.isotope/agents/{name}/soul.md`)

### 4.4 `@isotope/cli` (optional)

Thin client to the daemon API. Not the priority — macOS app is.

```bash
isotope daemon start|stop|status
isotope run "prompt" --model claude-sonnet --tools web_search,shell
isotope chat --agent researcher
isotope tasks [--watch]
isotope result <id>
isotope agents list
```

### 4.5 `isotope-apple-tools` (Swift, separate repo)

Swift package exposing Apple frameworks as isotope-compatible tools via local HTTP bridge (port 9100).

| Tool | Framework | Priority |
|---|---|---|
| Calendar | EventKit | P0 |
| Reminders | EventKit | P0 |
| Contacts | Contacts.framework | P0 |
| Notes | AppleScript/Shortcuts | P1 |
| Mail | MessageUI/AppleScript | P1 |
| Clipboard | NSPasteboard/UIPasteboard | P1 |
| Notifications | UserNotifications | P1 |
| Shortcuts | Shortcuts.framework | P1 |
| Photos | PhotoKit | P2 |
| Files | FileManager + iCloud | P2 |
| Location | CoreLocation | P2 |
| SystemInfo | Various | P2 |
| FocusMode | — | P2 |
| AppControl | NSWorkspace/UIApplication | P2 |

### 4.6 `isotope-app` (Swift, separate repo)

Native macOS/iOS/iPadOS app. SwiftUI.

**macOS:**
- Menu bar agent (always available)
- Global hotkey (⌘⇧Space) for quick input
- Chat interface with streaming + tool call visualization
- Settings (providers, permissions, agents)

**iOS/iPadOS:**
- Chat interface
- Siri Shortcuts integration
- Widgets, Share sheet
- Push notifications
- iCloud sync (configs, history, Keychain for API keys)

---

## 5. Milestones

### M1: Core Engine (Week 1)

**Goal:** `@isotope/core` working — can run an agent loop with tool calling.

**Deliverables:**
- [ ] Port isotope-core from Python to TypeScript
- [ ] Agent loop (plan → act → observe → repeat)
- [ ] LLM providers: OpenAI, Anthropic, GitHub Copilot API
- [ ] Middleware pipeline (composable transforms)
- [ ] Event system (typed async events)
- [ ] Context management (messages, token counting)
- [ ] Unit tests (target: >90% coverage)
- [ ] `@isotope/core` publishable to npm

**Exit criteria:** Can run a basic agent loop from code that calls an LLM and receives tool call responses.

---

### M2: Agent Framework (Week 1-2)

**Goal:** `@isotope/agents` with ToolAgent + built-in tools + sandbox.

**Deliverables:**
- [ ] `ToolAgent` wrapping core's loop
- [ ] P0 built-in tools: Shell, FileRead, FileWrite, FileEdit, Glob, Grep, WebSearch, WebFetch, AskUser, FinalAnswer
- [ ] Tool confirmation system (allow-once / allow-always / deny)
- [ ] OS sandbox: macOS Seatbelt profiles + Linux bwrap
- [ ] `ShellAgentTool` (wrap Claude Code / Gemini CLI as tools)
- [ ] Memory (structured conversation history)
- [ ] Examples + docs
- [ ] `@isotope/agents` publishable to npm

**Exit criteria:** Can run `ToolAgent` with tools from a script, tool confirmation works, sandbox isolates shell/file tools.

---

### M3: Daemon + CLI (Week 2-3)

**Goal:** Headless daemon running, accessible via CLI and HTTP.

**Deliverables:**
- [ ] `@isotope/daemon` — HTTP + Unix socket server
- [ ] Core API: `/agents`, `/agents/:id/run`, `/agents/:id/chat`, `/agents/:id/stream`
- [ ] SSE streaming for real-time events
- [ ] Fire-and-forget tasks (`/tasks`)
- [ ] Session management
- [ ] Agent identity files (`soul.md`)
- [ ] `@isotope/cli` — `isotope daemon start`, `isotope chat`, `isotope run`
- [ ] `isotope` installable globally via npm

**Exit criteria:** `isotope daemon start` → `isotope chat` works. Can also hit the API with curl/fetch.

---

### M4: Protocols (Week 3-4)

**Goal:** MCP and A2A integration.

**Deliverables:**
- [ ] MCP client (load tools from MCP servers)
- [ ] A2A client (delegate to external agents)
- [ ] A2A server (expose isotope agents)
- [ ] Agent-Tool bridge (wrap A2A agent as isotope tool)
- [ ] MultiAgent orchestrator
- [ ] Planning loop (plan → act → re-plan)
- [ ] Context compression
- [ ] Tool registry (dynamic tool registration via HTTP)
- [ ] Pre-built middleware: logging, token budget, safety, retry

**Exit criteria:** Can load MCP tools, call an external A2A agent, expose an isotope agent via A2A.

---

### M5: Apple Tools (Week 4-5)

**Goal:** `isotope-apple-tools` Swift package + bridge.

**Deliverables:**
- [ ] Swift tool protocol + JSON schema generator
- [ ] Local HTTP tool server (port 9100)
- [ ] P0 tools: Calendar, Reminders, Contacts
- [ ] P1 tools: Notes, Mail, Clipboard, Notifications, Shortcuts
- [ ] Bridge client in `@isotope/agents` (tool registry auto-discovery)
- [ ] Swift package publishable

**Exit criteria:** "What's on my calendar today?" works end-to-end through the daemon.

---

### M6: macOS App MVP (Week 5-7)

**Goal:** Native macOS app — the product.

**Deliverables:**
- [ ] Menu bar agent with chat panel
- [ ] Global hotkey (⌘⇧Space) quick input
- [ ] Chat interface with streaming
- [ ] Tool call visualization (expandable panels)
- [ ] Session history sidebar
- [ ] Settings: model providers, tool permissions, agent management
- [ ] Connects to daemon + Apple tools server
- [ ] TestFlight / direct download

**Exit criteria:** Install the app → menu bar icon appears → chat with agent → agent can check your calendar, run shell commands, search the web.

---

### M7: iOS App (Week 7-9)

**Goal:** iOS/iPadOS companion app.

**Deliverables:**
- [ ] Chat interface
- [ ] Siri Shortcuts ("Hey Siri, ask isotope to...")
- [ ] Widgets (quick actions, recent conversations)
- [ ] Share sheet (send content to agent)
- [ ] iCloud sync (configs, history, Keychain for keys)
- [ ] Push notifications for task completion
- [ ] App Store submission

**Exit criteria:** Works on iPhone, syncs with macOS app via iCloud.

---

### M8: Polish & Scale (Ongoing)

- [ ] Web dashboard (React, conversation viz, agent management)
- [ ] Local model support (MLX on Apple Silicon)
- [ ] Voice input/output
- [ ] Multi-device handoff
- [ ] Agent iteration (Docker containers, workspace persistence, git-tracked, image snapshots)
- [ ] Async messaging (inter-agent comms, Redis/NATS for scale)
- [ ] Telemetry middleware (OpenTelemetry)

---

## 6. Open Questions

| # | Question | Options |
|---|---|---|
| 1 | **Product name** | `isotope` for everything, or friendlier consumer name for the app? |
| 2 | **Distribution** | Mac App Store vs direct download vs both? |
| 3 | **Python embedding** | Bundle Python in macOS app for MCP servers that need it, or require user install? |
| 4 | **Pricing** | Free + OSS? Freemium? |
| 5 | **License** | MIT for all packages, or different for the app? |
| 6 | **iCloud sync** | CloudKit vs custom sync? |
| 7 | **Async messaging backend** | In-process EventEmitter (MVP) → when to add Redis/NATS? |

---

## 7. Non-Goals (v1)

- CodeAgent / built-in code execution
- Android/Windows native apps
- Browser extension
- K8s multi-node clustering
- Enterprise features (SSO, teams, billing)
- Training or fine-tuning
- Third-party agent marketplace
