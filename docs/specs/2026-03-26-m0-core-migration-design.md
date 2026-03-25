# M0: Core Migration — Design Doc

**Date:** 2026-03-26
**Status:** Approved (per PRD v6)
**Owner:** Tachikoma
**Branch:** `user/tachikoma/dev-m0`

---

## Goal

Migrate isotope-core from its standalone repo (`GhostComplex/isotope-core`) into the isotope mono-repo (`GhostComplex/isotope`) under `packages/isotope-core/`. Set up uv workspace. Zero functional changes.

## Success Criteria

- All isotope-core source code lives in `packages/isotope-core/`
- All existing tests pass (`uv run pytest`)
- `ruff check` and `mypy` pass
- `packages/isotope-agents/` exists as a stub (pyproject.toml + empty `__init__.py`)
- Root `pyproject.toml` configures uv workspace
- README.md updated

## Subtasks

### M0.1: Workspace scaffolding (~50 LOC, S)

Set up the mono-repo structure and root workspace config.

**Create:**
- `packages/isotope-core/` directory
- `packages/isotope-agents/` directory
- `packages/isotope-agents/src/isotope_agents/__init__.py` (empty stub)
- `packages/isotope-agents/pyproject.toml` (stub — name, version, dependency on isotope-core)
- Root `pyproject.toml` with uv workspace config

**Root pyproject.toml:**
```toml
[project]
name = "isotope"
version = "0.1.0"
description = "Isotope mono-repo"
requires-python = ">=3.11"

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
isotope-core = { workspace = true }
```

**Commit** after structure is in place.

### M0.2: Migrate isotope-core source (~0 new LOC, S)

Copy all source code from isotope-core repo into `packages/isotope-core/`.

**Copy:**
- `src/isotope_core/` → `packages/isotope-core/src/isotope_core/`
- `tests/` → `packages/isotope-core/tests/`
- `tui/` → `packages/isotope-core/tui/` (temporary, consumed by M1)
- `pyproject.toml` → `packages/isotope-core/pyproject.toml`
  - Strip TUI optional dependency (`tui` extra removed — moves to isotope-agents)
  - Keep all other extras (openai, anthropic, tiktoken)
- `docs/` → `packages/isotope-core/docs/` (API.md, roadmap, milestone PRDs)

**Do NOT copy:** `.git/`, `uv.lock` (regenerated), `.github/` (CI will be at root level)

**Commit** after migration.

### M0.3: Fix imports and verify (~0 new LOC, S)

Ensure everything works in the new location.

- Run `uv sync` at repo root
- Run `uv run pytest packages/isotope-core/tests/` — all tests must pass
- Run `uv run ruff check packages/isotope-core/`
- Run `uv run mypy packages/isotope-core/src/`
- Fix any path-related issues

**Commit** after all checks pass.

### M0.4: Update README and clean up (~100 LOC, S)

- Update root `README.md` with mono-repo structure, package descriptions, quickstart
- Remove old `docs/PRD.md` reference to separate isotope-core repo (it's now local)
- Ensure `.gitignore` covers Python artifacts (`__pycache__`, `*.egg-info`, `.venv`, etc.)

**Commit**, then open PR to main.

## Notes

- The isotope-core standalone repo archival is handled separately (not part of this PR)
- The `tui/` code stays in isotope-core temporarily — M1 will lift it into isotope-agents
- No functional changes — this is purely a structural migration
