# Gestalt

**Parts compatibility** UI (Flask) and optional **CrewAI** workflows. Python **3.12–3.13** with [uv](https://docs.astral.sh/uv/).

## Layout

```text
gestalt/
├── parts.json
├── compatibility_checker.py
├── agents.py
├── crew.py
├── app.py
├── templates/
│   └── index.html
├── static/
│   └── style.css
└── .env                 # local only — copy from .env.example; never commit
```

Versioned alongside the app: `README.md`, `LICENSE`, `pyproject.toml`, `uv.lock`, `.env.example`, `.gitignore`, `.python-version`.

## Quick start

```bash
cd Gestalt
uv sync
cp .env.example .env
# Add GEMINI_API_KEY (Google AI Studio) for CrewAI agents — see .env.example
uv run gestalt-web
# http://127.0.0.1:5000
```

```bash
uv run python crew.py
```

### Verify Gemini API key (optional)

With **`GEMINI_API_KEY`** set in `.env`, run a single minimal API call (skipped if the key is missing):

```bash
uv run pytest tests/test_gemini_smoke.py -v
```

Override the model for this check only: **`GESTALT_GEMINI_SMOKE_MODEL`** (e.g. `gemini-2.0-flash`). Otherwise it uses the same base model as **`GESTALT_LLM_MODEL`** (without the `gemini/` prefix for the native client).

## Git remote (SSH)

`git@github.com:Xydra01/Gestalt.git`

## Pull requests

[`gh pr create`](https://cli.github.com/manual/gh_pr_create) after pushing a branch; set **`GH_TOKEN`** (e.g. in `~/.bash_profile`) for non-interactive use.

## License

MIT — [`LICENSE`](LICENSE).
