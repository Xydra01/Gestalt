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
# Optional: LLM keys for CrewAI
uv run gestalt-web
# http://127.0.0.1:5000
```

```bash
uv run python crew.py
```

## Git remote (SSH)

`git@github.com:Xydra01/Gestalt.git`

## Pull requests

1. Install the [GitHub CLI](https://cli.github.com/): **`brew install gh`**, then **`gh auth login`** (or set **`GH_TOKEN`** in `~/.bash_profile` for non-interactive use).
2. On macOS, this repo’s **`.vscode/settings.json`** prepends **`/opt/homebrew/bin`** to the integrated terminal **`PATH`** so `gh` is found after a **new terminal** tab.
3. If `gh` is still missing (e.g. agent shells), run it via **`./scripts/gh`** from the repo root, which adds the same Homebrew paths.
4. If **zsh** does not load your token, run PR commands with Bash: **`bash -lc 'cd …/Gestalt && ./scripts/gh pr create …'`**.

See [gh pr create](https://cli.github.com/manual/gh_pr_create) after pushing a branch.

## License

MIT — [`LICENSE`](LICENSE).
