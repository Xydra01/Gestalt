# Gestalt

Gestalt is a **guardrail-first** Python project for multi-agent workflows built on [CrewAI](https://www.crewai.com/). The goal is to establish strict constraints *before* any execution code is written or extended, so early decisions do not accumulate into uncontrolled technical debt.

## What this repo contains

- **Python runtime**: Managed with [Astral uv](https://github.com/astral-sh/uv) for fast installs and a reproducible virtual environment (see `.python-version`).
- **Crew layout**: Matches the official **`crewai create crew <name> --skip-provider`** structure (`src/<package>/crew.py`, `config/*.yaml`, `tools/`). The scaffold was generated in-repo (rather than via the interactive CLI) so Python stays on **3.12–3.13** and the tree matches CrewAI expectations without an extra nested folder. You can still run the CLI in a throwaway directory anytime for comparison.
- **Cursor guardrails**: Modular AI rules under `.cursor/rules/` (`core`, `request`, `refresh`) plus a root `.cursorrules` pointer file.
- **Debug pipeline**: Templates under `debug/` for structured crash reports you can paste back into the agent (see `.cursor/rules/refresh.mdc`).

## Requirements

- Python **3.12 or 3.13** (3.14+ is not supported by current CrewAI/pydantic native builds).
- [uv](https://docs.astral.sh/uv/) installed.

## Quick start

```bash
cd Gestalt
uv sync
cp .env.example .env
# Edit .env with your model provider API key(s)
uv run gestalt
# or: uv run crewai run
```

Outputs from tasks may be written under `output/` (gitignored) when configured in `tasks.yaml`.

## Configuration

| File | Purpose |
|------|---------|
| `.env` | API keys and provider settings (never commit real secrets). |
| `src/gestalt/config/agents.yaml` | Agent roles, goals, backstories. |
| `src/gestalt/config/tasks.yaml` | Tasks, expected outputs, agent mapping. |
| `src/gestalt/crew.py` | Crew wiring and process definition. |

## Development principles

1. **Tests first** — Add or extend tests before implementation changes (see `.cursor/rules/core.mdc`).
2. **Contracts first** — Define inputs, outputs, and failure modes before new features (see `.cursor/rules/request.mdc`).
3. **Structured debugging** — Use the crash-report template when reporting failures (see `.cursor/rules/refresh.mdc`).

## License

This project is licensed under the MIT License — see [`LICENSE`](LICENSE).
