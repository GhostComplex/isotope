# Multi-Provider Support & Setup Wizard

**Date:** 2026-03-27
**Status:** Draft
**Author:** Major (AI Engineering Manager)

## Goal

Replace the hardcoded `localhost:4141` proxy provider with multi-provider support (OpenAI, Anthropic, MiniMax, custom proxy) and an interactive first-run setup wizard. Config stored in `~/.isotope/settings.json`.

## Background

Currently, `isotope-agents` always creates a `ProxyProvider` pointing at `http://localhost:4141/v1`. This requires running the `copilot-api` proxy locally. Users with direct API keys (Anthropic, OpenAI, MiniMax) can't use Isotope without the proxy.

The providers already exist in `isotope-core`:
- `OpenAIProvider` — OpenAI Chat Completions API
- `AnthropicProvider` — Anthropic Messages API
- `ProxyProvider` — OpenAI-compatible proxy (extends OpenAIProvider)

## Design

### 1. Config: `~/.isotope/settings.json`

Replace `config.yaml` with `settings.json`. No YAML dependency needed.

```json
{
  "provider": {
    "type": "anthropic",
    "base_url": "https://api.anthropic.com",
    "api_key": "sk-ant-..."
  },
  "model": "claude-sonnet-4",
  "preset": "coding",
  "sessions_dir": "~/.isotope/sessions",
  "skills": ["~/.isotope/skills/"],
  "tools": [],
  "mcp": {
    "servers": []
  }
}
```

**Provider types and their defaults:**

| `type` | Default `base_url` | API format | API key env var |
|--------|-------------------|------------|-----------------|
| `openai` | `https://api.openai.com/v1` | OpenAI | `OPENAI_API_KEY` |
| `anthropic` | `https://api.anthropic.com` | Anthropic | `ANTHROPIC_API_KEY` |
| `minimax` | `https://api.minimaxi.com/v1` | OpenAI-compat | `MINIMAX_API_KEY` |
| `minimax-global` | `https://api.minimax.io/v1` | OpenAI-compat | `MINIMAX_API_KEY` |
| `proxy` | `http://localhost:4141` | OpenAI-compat | (none) |

Users can override `base_url` for any type. The `type` determines which provider class is instantiated.

**Env var expansion:** Support `${VAR_NAME}` syntax in `api_key` field (already implemented in current config loader).

### 2. Provider Factory

New function in `config.py` or a new `providers.py` in isotope-agents:

```python
def create_provider(model: str, config: IsotopeConfig) -> Provider:
    ptype = config.provider.type
    api_key = config.provider.api_key
    base_url = config.provider.base_url

    if ptype == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key, base_url=base_url)
    elif ptype in ("openai", "minimax", "minimax-global"):
        return OpenAIProvider(model=model, api_key=api_key, base_url=base_url)
    else:  # proxy
        return ProxyProvider(model=model, api_key=api_key or "not-needed", base_url=base_url)
```

### 3. First-Run Experience (FRE) — Inline Setup

No separate `isotope setup` subcommand. The wizard runs inline on first launch:

```
$ isotope

Welcome to Isotope! Let's configure your AI provider.

? Choose a provider:
  ❯ Anthropic        (claude-opus-4, claude-sonnet-4, ...)
    OpenAI           (gpt-4.1, o3, ...)
    MiniMax CN       (MiniMax-M2.7, api.minimaxi.com)
    MiniMax Global   (MiniMax-M2.7, api.minimax.io)
    OpenAI-compatible proxy  (localhost, LiteLLM, Ollama, ...)

? API key: sk-ant-api03-...
? Default model [claude-sonnet-4]: claude-opus-4

✓ Saved to ~/.isotope/settings.json

───────────────────────────────────────
 isotope v0.1.3 | claude-opus-4 | coding
───────────────────────────────────────
You:
```

**Trigger:** `~/.isotope/settings.json` doesn't exist AND no env vars auto-detected → run FRE before TUI starts.

**Proxy path:** If user selects proxy, ask for base URL (default `http://localhost:4141`). API key defaults to `"not-needed"`.

### 3b. `/setup` Slash Command

Re-run the FRE wizard from inside the TUI to change provider/model/key:

```
You: /setup

? Choose a provider:
  ❯ Anthropic  (current)
    OpenAI
    ...

? API key [sk-ant-...****]: (enter to keep current)
? Default model [claude-opus-4]:

✓ Config updated. Reconnecting with new provider...
```

The `/setup` command:
1. Runs the same wizard flow as FRE (pre-filled with current values)
2. Saves updated `settings.json`
3. Hot-swaps the provider — no restart needed

### 4. Env Var Auto-Detection

If no `settings.json` exists and no `isotope setup` has run, but env vars are set, auto-detect:

Priority order:
1. `ANTHROPIC_API_KEY` → Anthropic provider
2. `OPENAI_API_KEY` → OpenAI provider
3. `MINIMAX_API_KEY` → MiniMax provider
4. Fall back to proxy at `localhost:4141`

Print a one-line notice: `Using Anthropic (from ANTHROPIC_API_KEY). Run 'isotope setup' to configure.`

### 5. Migration

- If `~/.isotope/config.yaml` exists but `settings.json` doesn't, auto-migrate on first load
- Print: `Migrated config.yaml → settings.json`
- Keep `config.yaml` as backup (don't delete)

### 6. CLI Changes

- Remove `isotope setup` subcommand — FRE is inline on first launch
- `/setup` slash command in TUI — re-run wizard to change config
- `--model` flag: still works as override
- `--provider` flag: new, overrides provider type for this session
- Remove hardcoded `PROXY_BASE_URL` and `DEFAULT_MODEL` constants from `cli.py`

## File Changes

| File | Change |
|------|--------|
| `config.py` | Replace YAML with JSON, add `provider.type`, add `create_provider()`, add migration, add env var detection |
| `cli.py` | Remove hardcoded proxy, use `create_provider()`, add `--provider` flag, trigger FRE on first run |
| `setup.py` (new) | Interactive setup wizard (shared by FRE and `/setup` command) |
| `tui/app.py` | Add `/setup` slash command handler, hot-swap provider |
| `pyproject.toml` | Remove `pyyaml` from dependencies (if present) |

## Testing Strategy

- Unit tests for `create_provider()` with each provider type
- Unit tests for config loading (JSON format)
- Unit tests for env var auto-detection priority
- Unit tests for YAML → JSON migration
- No integration tests (need real API keys)

## Out of Scope

- RouterProvider / fallback chains in config (future)
- OAuth flows (future)
- Model validation against provider catalogs (future)

## Open Questions

1. Should `settings.json` support comments (JSONC)? Probably not — keep it simple.
2. Should we store the API key in the file or always use env vars? Both — support inline and `${VAR}` expansion.
