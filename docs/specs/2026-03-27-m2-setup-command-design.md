# M2: /setup Slash Command & Hot-Swap Provider

**Date:** 2026-03-27
**Status:** Draft
**Author:** Major (AI Engineering Manager)
**Depends on:** PR #37 (M1: Multi-Provider Config + FRE)

## Goal

Add a `/setup` slash command in the TUI that lets users reconfigure their provider, model, and system prompt without restarting. Support hot-swapping providers mid-session.

## Background

M1 delivered the FRE wizard and `settings.json` config. But once configured, the only way to change settings is to manually edit `settings.json` or delete it to re-trigger FRE. Users need an in-session way to reconfigure.

## Design

### `/setup` Command

A new TUI slash command that re-runs the setup wizard inline:

```
› /setup
```

**Flow:**
1. Show current config summary (provider, model, system prompt mode)
2. Ask: "Reconfigure? (provider/model/prompt/all) [all]:"
   - `provider` — change provider + API key + base URL
   - `model` — change model only (fetch available models)
   - `prompt` — change system prompt mode (default/custom + edit agent.md)
   - `all` — full wizard (same as FRE)
3. Save updated `settings.json` (and `agent.md` if applicable)
4. Hot-swap: rebuild the agent with new provider/model without losing session history

### Hot-Swap Provider

When provider or model changes mid-session:

1. Create new provider instance via `create_provider()`
2. Rebuild the agent with new provider but **preserve message history**
3. Print confirmation: `"✓ Switched to {provider} / {model}"`

The existing `_rebuild_agent()` method (used by `/clear`) already handles this pattern — extend it to accept new provider/model params.

### `/model` Shortcut

Quick model switch without full setup:

```
› /model claude-opus-4.6
✓ Switched to claude-opus-4.6

› /model
Available models:
  1. claude-sonnet-4.6 (current)
  2. claude-opus-4.6
  ...
Model [1]:
```

### `/provider` Shortcut

Quick provider info:

```
› /provider
Current: proxy (http://localhost:4141/v1)
Model: claude-sonnet-4.6
System prompt: default (coding preset)
```

## Implementation

### Files to Change

| File | Changes |
|---|---|
| `tui/app.py` | Add `/setup`, `/model`, `/provider` command handlers |
| `tui/commands.py` | Register new commands in command handler |
| `config.py` | No changes (M1 already provides save/load/create_provider) |

### Command Registration

Add to the existing `CommandHandler`:

```python
"/setup"    → _handle_setup()    # Full reconfigure wizard
"/model"    → _handle_model()    # Quick model switch  
"/provider" → _handle_provider() # Show current provider info
```

### Agent Rebuild

Extend `_rebuild_agent()`:

```python
def _rebuild_agent(self, *, keep_history=True, new_model=None, new_config=None):
    if new_config:
        self.config = new_config
    if new_model:
        self.model = new_model
    # ... existing rebuild logic
```

## Testing

### Unit Tests
- `/setup` command parsing and dispatch
- `/model` with and without argument
- `/provider` output format
- Config save after `/setup`
- Agent rebuild preserves history

### Smoke Tests (superqa-isotope)
- Launch TUI → `/setup` → change model → verify new model used
- Launch TUI → `/model claude-opus-4.6` → verify switch
- Launch TUI → `/setup` → change provider → verify hot-swap
- `/provider` shows correct current state

## Out of Scope
- Multi-provider fallback/routing (future milestone)
- Provider-specific advanced settings (temperature, max_tokens — future)
- OAuth/SSO provider auth flows

## Open Questions
1. Should `/setup` preserve the current session or start fresh? → Preserve (hot-swap)
2. Should model changes persist to `settings.json` or be session-only? → Persist
3. Should `/model` without args show the fetched model list or just current? → Show list (same as FRE)
