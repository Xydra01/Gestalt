# Gestalt

**Parts compatibility** UI (Flask) and optional **CrewAI** workflows. Python **3.12–3.13** with [uv](https://docs.astral.sh/uv/).

## Layout

```text
gestalt/
├── parts.json           # fallback catalog when no live URL
├── parts_catalog.py     # load live URL → else parts.json → else embedded mock
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

Override the model for this check: **`GESTALT_GEMINI_SMOKE_MODEL`** (google.genai id, default **`gemini-2.5-flash`**). This is separate from **`GESTALT_LLM_MODEL`**, which uses CrewAI/LiteLLM naming.

## Parts catalog

Gestalt prefers a **live** JSON catalog when **`PARTS_CATALOG_URL`** is set in `.env` (HTTP/HTTPS). If the variable is unset, the URL fails, or the payload is not a valid PC catalog shape, the app **falls back** to bundled **`parts.json`**, then to a tiny embedded mock. Check logs (standard logging) to see which source was used; API responses from `run_build_assistant` also include **`parts_catalog_source`**.

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
