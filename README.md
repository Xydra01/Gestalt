# Gestalt

Guardrail-first workspace for **parts compatibility** checks and optional **CrewAI** crews. Python **3.12–3.13** with [uv](https://docs.astral.sh/uv/).

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
├── .env                 # create locally (see .env.example); never commit
└── ...
```

## Quick start

```bash
cd Gestalt
uv sync
cp .env.example .env
# Optional: add LLM keys for CrewAI
uv run gestalt-web
# Open http://127.0.0.1:5000
```

Run the crew (needs provider credentials in `.env`):

```bash
uv run python crew.py
```

## Git remote (SSH)

```text
git@github.com:Xydra01/Gestalt.git
```

## Pull requests (GitHub CLI)

From a feature branch, push then run [`gh pr create`](https://cli.github.com/manual/gh_pr_create). Non-interactive use expects **`GH_TOKEN`** in the environment (for example `export GH_TOKEN=...` in `~/.bash_profile` for login shells).

## Cursor guardrails

See `.cursor/rules/` (`core`, `request`, `refresh`) and root `.cursorrules`.

## License

MIT — see [`LICENSE`](LICENSE).
