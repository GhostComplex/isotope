# M4: RPC + Skills + MCP — Design Doc

**Date:** 2026-03-26
**Status:** Approved
**Owner:** Tachikoma
**Branch:** `user/tachikoma/dev-m4` (from `main`)
**PRD Reference:** §9 (RPC Protocol), §10 (Skills & Extensions), M4 checklist

---

## Goal

Embeddable agent via RPC protocol. Skill loading from directories. External tools via MCP. After M4: `isotope rpc` enables embedding in any UI, skills load from `~/.isotope/skills/`, and MCP tools integrate seamlessly.

## Success Criteria

- `isotope rpc` starts JSONL stdin/stdout RPC mode
- RPC supports all commands from PRD §9 (prompt, steer, follow_up, abort, get_state, set_model, compact, new_session)
- RPC emits all event types (agent_start, text_delta, tool_call_start, tool_call_end, agent_end, state)
- Skills loaded from configured directories via AgentSkills spec (frontmatter scan + lazy load)
- MCP client loads tools from MCP servers
- `tools:` config registers additional tools by Python module path
- Documentation: README.md updated with usage guides
- All existing tests pass + new tests

---

## Subtasks

### M4.1: RPC protocol types

**File:** `packages/isotope-agents/src/isotope_agents/rpc/protocol.py`

**~150 LOC, S**

Define the JSONL RPC protocol types as Pydantic models:

```python
# Commands (stdin → agent)
class RpcCommand(BaseModel):
    id: str | None = None
    type: str

class PromptCommand(RpcCommand):
    type: Literal["prompt"] = "prompt"
    content: str
    images: list[str] = []

class SteerCommand(RpcCommand):
    type: Literal["steer"] = "steer"
    content: str

class FollowUpCommand(RpcCommand):
    type: Literal["follow_up"] = "follow_up"
    content: str

class AbortCommand(RpcCommand):
    type: Literal["abort"] = "abort"

class GetStateCommand(RpcCommand):
    type: Literal["get_state"] = "get_state"

class SetModelCommand(RpcCommand):
    type: Literal["set_model"] = "set_model"
    model: str

class CompactCommand(RpcCommand):
    type: Literal["compact"] = "compact"

class NewSessionCommand(RpcCommand):
    type: Literal["new_session"] = "new_session"


# Events (agent → stdout)
class RpcEvent(BaseModel):
    type: str
    stream_id: str | None = None

class AgentStartRpcEvent(RpcEvent):
    type: Literal["agent_start"] = "agent_start"

class TextDeltaRpcEvent(RpcEvent):
    type: Literal["text_delta"] = "text_delta"
    content: str

class ToolCallStartRpcEvent(RpcEvent):
    type: Literal["tool_call_start"] = "tool_call_start"
    name: str
    arguments: dict

class ToolCallEndRpcEvent(RpcEvent):
    type: Literal["tool_call_end"] = "tool_call_end"
    name: str
    output: str
    is_error: bool

class AgentEndRpcEvent(RpcEvent):
    type: Literal["agent_end"] = "agent_end"
    usage: dict

class StateRpcEvent(RpcEvent):
    type: Literal["state"] = "state"
    model: str
    preset: str
    session_id: str

class ErrorRpcEvent(RpcEvent):
    type: Literal["error"] = "error"
    message: str
    command_id: str | None = None
```

Add a command parser:
```python
def parse_command(line: str) -> RpcCommand: ...
```

**Tests:** `packages/isotope-agents/tests/test_rpc_protocol.py`

**Commit after done.**

---

### M4.2: RPC server

**File:** `packages/isotope-agents/src/isotope_agents/rpc/server.py`

**~250 LOC, L**

The RPC server:
1. Reads JSONL commands from stdin (asyncio StreamReader)
2. Processes commands against an `IsotopeAgent` instance
3. Translates `AgentEvent` stream into `RpcEvent` JSONL on stdout
4. Handles concurrent concerns: prompt running + steering/abort arriving

```python
class RpcServer:
    def __init__(self, agent: IsotopeAgent, *, input_stream=None, output_stream=None):
        self.agent = agent
        self._input = input_stream or sys.stdin
        self._output = output_stream or sys.stdout

    async def run(self) -> None:
        """Main loop: read commands, dispatch, emit events."""

    async def _handle_prompt(self, cmd: PromptCommand) -> None:
        """Run agent with prompt, stream events to stdout."""

    async def _handle_steer(self, cmd: SteerCommand) -> None:
        """Queue steering message."""

    async def _handle_follow_up(self, cmd: FollowUpCommand) -> None:
        """Queue follow-up message."""

    async def _handle_abort(self, cmd: AbortCommand) -> None:
        """Abort current agent run."""

    async def _handle_get_state(self, cmd: GetStateCommand) -> None:
        """Emit current state."""

    async def _handle_set_model(self, cmd: SetModelCommand) -> None:
        """Change model."""

    async def _handle_compact(self, cmd: CompactCommand) -> None:
        """Trigger compaction."""

    async def _handle_new_session(self, cmd: NewSessionCommand) -> None:
        """Start new session."""

    def _emit(self, event: RpcEvent) -> None:
        """Write a JSONL event to stdout."""
        self._output.write(event.model_dump_json() + "\n")
        self._output.flush()
```

Key mapping from `AgentEvent` → `RpcEvent`:
- `MessageUpdateEvent` → `TextDeltaRpcEvent` (content deltas)
- `ToolStartEvent` → `ToolCallStartRpcEvent`
- `ToolEndEvent` → `ToolCallEndRpcEvent`
- `AgentStartEvent` → `AgentStartRpcEvent`
- `AgentEndEvent` → `AgentEndRpcEvent` (with usage)

**Tests:** `packages/isotope-agents/tests/test_rpc_server.py` — test with mock streams.

**Commit after done.**

---

### M4.3: `isotope rpc` CLI command

**File:** `packages/isotope-agents/src/isotope_agents/cli.py` (add `rpc` subcommand)

**~30 LOC, S**

```bash
isotope rpc
isotope rpc --preset coding
isotope rpc --model claude-sonnet-4-20250514
isotope rpc --session abc123  # resume session
```

Starts the RPC server. Reads from stdin, writes to stdout. Stderr for logs/errors.

**Tests:** Update `packages/isotope-agents/tests/test_cli.py`.

**Commit after done.**

---

### M4.4: Skill loader

**File:** `packages/isotope-agents/src/isotope_agents/skills.py`

**~150 LOC, M**

```python
@dataclass
class SkillInfo:
    name: str
    description: str
    path: Path           # path to SKILL.md
    loaded: bool = False
    instructions: str = ""  # full SKILL.md content (loaded lazily)

class SkillLoader:
    def __init__(self, skill_dirs: list[Path]):
        self.skill_dirs = skill_dirs
        self._skills: dict[str, SkillInfo] = {}

    def scan(self) -> list[SkillInfo]:
        """Scan skill directories, read frontmatter only (name + description).
        Returns list of discovered skills."""

    def load(self, name: str) -> SkillInfo:
        """Load full SKILL.md content for a skill. Returns the updated SkillInfo."""

    def match(self, query: str) -> SkillInfo | None:
        """Simple keyword matching against skill descriptions.
        Returns best matching skill or None."""
```

Frontmatter parsing: read YAML between `---` delimiters at top of SKILL.md. Extract `name` and `description`. Don't load the full content until `load()` is called.

Skill directories are configured in `~/.isotope/config.yaml`:
```yaml
skills:
  - ~/.isotope/skills/
  - /path/to/project/skills/
```

Add `skills` field to `IsotopeConfig`.

**Tests:** `packages/isotope-agents/tests/test_skills.py`

**Commit after done.**

---

### M4.5: MCP client integration

**File:** `packages/isotope-agents/src/isotope_agents/mcp_client.py`

**~120 LOC, M**

Load tools from MCP servers and register them with the agent:

```python
class McpToolLoader:
    """Loads tools from MCP servers and converts them to isotope Tool objects."""

    async def load_from_server(self, server_config: dict) -> list[Tool]:
        """Connect to an MCP server, list its tools, and wrap them as isotope Tools.

        server_config example:
            {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]}
            {"url": "http://localhost:3000/mcp"}
        """

    def _mcp_tool_to_isotope_tool(self, mcp_tool) -> Tool:
        """Convert an MCP tool definition to an isotope-core Tool."""
```

Configuration in `~/.isotope/config.yaml`:
```yaml
mcp:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    - name: github
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
```

Use the `mcp` Python package for the client connection. Add as optional dep `[mcp]`.

**Tests:** `packages/isotope-agents/tests/test_mcp_client.py` — test with mocks (no real MCP servers).

**Commit after done.**

---

### M4.6: Tools config — register by module path

**File:** `packages/isotope-agents/src/isotope_agents/config.py` (extend)
**File:** `packages/isotope-agents/src/isotope_agents/agent.py` (wire loading)

**~60 LOC, S**

Allow registering additional tools via config:

```yaml
# ~/.isotope/config.yaml
tools:
  - mypackage.tools.custom_tool
  - mypackage.tools.another_tool
```

Each entry is a Python module path. The module is imported, and any `Tool` objects found at module level are registered with the agent.

```python
def load_tools_from_config(tool_paths: list[str]) -> list[Tool]:
    """Import modules and collect Tool objects."""
    tools = []
    for path in tool_paths:
        module = importlib.import_module(path)
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, Tool):
                tools.append(obj)
    return tools
```

**Tests:** `packages/isotope-agents/tests/test_config.py` — extend with tool loading tests.

**Commit after done.**

---

### M4.7: Documentation

**Files:**
- `README.md` (root)
- `packages/isotope-core/README.md`
- `packages/isotope-agents/README.md`

**~300 LOC total, M**

Root README:
- Project overview, architecture diagram (text)
- Quick start (install, run)
- Package descriptions
- Links to package READMEs

isotope-core README:
- What it provides (Agent, EventStream, @tool, providers, middleware)
- API overview with examples
- Provider setup

isotope-agents README:
- Quick start: `pip install isotope-agents[all]` → `isotope chat`
- CLI usage (chat, run, rpc, sessions)
- Presets
- Tools list
- Configuration guide
- Skills setup
- MCP integration
- RPC protocol reference

**Commit after done.**

---

### M4.8: Clean up + verify

- Verify all isotope-core tests pass
- Verify all isotope-agents tests pass
- `ruff check` + lint clean
- Update `pyproject.toml` files with any missing dependencies
- Verify `isotope rpc` works end-to-end (manual smoke test)
- Push, open PR to main

**Commit after done.**

---

## Notes

- RPC types use Pydantic for serialization consistency with the rest of the codebase
- RPC server uses asyncio for concurrent command handling (prompts + steering/abort can arrive simultaneously)
- Skill loader is deliberately simple — keyword matching, not semantic search. The agent can use skill descriptions in its system prompt to do smarter matching.
- MCP is optional (`[mcp]` extras) — isotope-agents works fine without it
- `tools:` config is the escape hatch — any Python tool can be loaded without MCP or skills
- Documentation is part of the milestone because "ship" means it's usable by others
