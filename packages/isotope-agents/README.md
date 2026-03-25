# isotope-agents

Agent framework built on [isotope-core](../isotope-core/) — provides tools, a TUI, CLI, session persistence, RPC protocol, presets, skills, and MCP integration.

## Quick Start

```bash
# Install with all extras
pip install isotope-agents[all]

# Launch interactive chat
isotope chat

# Run a one-shot prompt
isotope run "Explain this project"

# List saved sessions
isotope sessions
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `isotope chat` | Launch interactive TUI (requires `isotope-agents[tui]`) |
| `isotope run <prompt>` | Execute a one-shot prompt, stream response to stdout |
| `isotope rpc` | Start JSONL-over-stdio RPC server for embedding |
| `isotope sessions` | List saved sessions with message counts and previews |

### Global Options

```
--model MODEL        Model to use (default: claude-opus-4.6)
--preset PRESET      Preset: coding, assistant, minimal (default: coding)
--no-tools           Disable all tools
--version            Show version
```

### Resuming Sessions

```bash
isotope chat --session abc12345
isotope rpc --session abc12345
```

## Presets

Presets define which tools and system prompt the agent uses.

| Preset | Tools | Description |
|--------|-------|-------------|
| **coding** | read, write, edit, bash, grep, glob, web_search, web_fetch | Full coding agent |
| **assistant** | read, bash, grep, glob, web_search, web_fetch | General assistant (read-only files) |
| **minimal** | bash | Minimal agent with shell access only |

## Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents by path |
| `write_file` | Create new files or fully rewrite existing ones |
| `edit_file` | Make surgical edits to existing files |
| `bash` | Run shell commands |
| `grep` | Search file contents with regex patterns |
| `glob_tool` | Discover files by glob patterns |
| `web_search` | Search the web (requires `isotope-agents[search]`) |
| `web_fetch` | Fetch and read content from a URL (requires `isotope-agents[search]`) |

## Configuration

Isotope reads configuration from `~/.isotope/config.yaml`. Environment variables can be referenced with `${VAR}` syntax.

```yaml
# ~/.isotope/config.yaml
model: claude-opus-4.6
preset: coding
debug: false
sessions_dir: ~/.isotope/sessions

provider:
  base_url: http://localhost:4141
  api_key: ${ANTHROPIC_API_KEY}

skills:
  - ~/.isotope/skills/

tools:
  - my_package.custom_tools

mcp:
  servers:
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    - name: remote-api
      url: http://localhost:3001/sse
```

**Priority order:** CLI flags > environment variables > config file > defaults.

## Skills

Skills are reusable instruction sets defined as `SKILL.md` files with YAML frontmatter. Place them in `~/.isotope/skills/` (or any directory listed in `skills:` config).

```markdown
---
name: deploy
description: Deploy the application to production
---

## Instructions

1. Run the test suite with `pytest`
2. Build the Docker image
3. Push to the container registry
4. Update the deployment manifest
```

Skills are discovered lazily — frontmatter is scanned on startup, and the full content is loaded on demand when matched.

## MCP Integration

Isotope supports [Model Context Protocol](https://modelcontextprotocol.io/) servers. MCP tools are automatically converted to isotope tools and made available to the agent.

Configure MCP servers in `~/.isotope/config.yaml`:

```yaml
mcp:
  servers:
    # Stdio transport (subprocess)
    - name: filesystem
      command: npx
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]

    # SSE transport (HTTP)
    - name: my-api
      url: http://localhost:3001/sse
```

Requires the `mcp` extra: `pip install isotope-agents[mcp]`

## RPC Protocol

The `isotope rpc` command starts a JSONL-over-stdio server for embedding isotope in external applications (editors, IDEs, custom UIs).

### Commands (stdin → agent)

| Type | Fields | Description |
|------|--------|-------------|
| `prompt` | `content`, `images[]` | Send a user prompt |
| `steer` | `content` | Inject steering instruction mid-turn |
| `follow_up` | `content` | Queue a follow-up message |
| `abort` | — | Abort the current turn |
| `get_state` | — | Request current agent state |
| `set_model` | `model` | Change the active model |
| `compact` | — | Trigger context compaction |
| `new_session` | — | Start a fresh session |

All commands accept an optional `id` field for correlation.

### Events (agent → stdout)

| Type | Fields | Description |
|------|--------|-------------|
| `agent_start` | `stream_id` | Agent begins processing |
| `text_delta` | `content` | Streamed text chunk |
| `tool_call_start` | `name`, `arguments` | Tool execution begins |
| `tool_call_end` | `name`, `output`, `is_error` | Tool execution completes |
| `agent_end` | `usage` | Agent finishes processing |
| `state` | `model`, `preset`, `session_id` | Response to `get_state` |
| `error` | `message`, `command_id` | Error occurred |

### Example

```bash
# Start the RPC server
isotope rpc &

# Send a prompt
echo '{"type":"prompt","content":"What files are in this directory?"}' | isotope rpc

# Abort
echo '{"type":"abort"}' | isotope rpc
```

## Session Management

Sessions are persisted as JSONL files in `~/.isotope/sessions/` (configurable via `sessions_dir`). Each session gets an 8-character UUID.

```bash
# List recent sessions
isotope sessions
isotope sessions --limit 20

# Resume a session
isotope chat --session abc12345
```

Session entries include: `session_start`, `user_message`, `assistant_message`, `tool_result`, and `compaction` events. Compaction summaries are pinned so they survive context pruning on resume.

## Extras

| Extra | Dependency | Enables |
|-------|-----------|---------|
| `tui` | prompt-toolkit, rich | Interactive TUI (`isotope chat`) |
| `search` | httpx | Web search and fetch tools |
| `mcp` | mcp | MCP server integration |
| `all` | all of the above | Everything |

## License

MIT
