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

## Git remote (SSH)

`git@github.com:Xydra01/Gestalt.git`

## Pull requests

[`gh pr create`](https://cli.github.com/manual/gh_pr_create) after pushing a branch; set **`GH_TOKEN`** (e.g. in `~/.bash_profile`) for non-interactive use.

## License

MIT — [`LICENSE`](LICENSE).
