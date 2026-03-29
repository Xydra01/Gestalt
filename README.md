# Gestalt

**Gestalt** is a Flask web app for AI-assisted **PC builds**: conversational **intake**, a **CrewAI** analysis + recommendation pipeline with **compatibility validation**, optional **live pricing** (Amazon / eBay), a **Server-Sent Events** log stream, and an **“Explain Like I’m a Beginner”** (ELI5) explainer backed by Google Gemini when configured.

Python **3.12–3.13**. Dependencies are managed with **[uv](https://docs.astral.sh/uv/)** (see `pyproject.toml` / `uv.lock`).

## What it does (scope)

| Area | Behavior |
|------|----------|
| **Web UI** | Single-page UI (`templates/index.html`, `static/hexcore.css`): prompt, crew trace terminal, parts table with buy links and savings rollup, ELI5 panel, responsive layout and motion (see recent UI PRs). |
| **Intake** | `intake.py` — before calling the crew, decides if the user prompt has enough detail (budget + use case, or a long brief). May return **clarification** questions; merges follow-up answers into the build prompt. |
| **Crew** | `crew.py` — analysis task → recommendation loop (up to 3 tries) with `compatibility_checker.validate_build`; builds `agent_trace` for the UI. Uses **Gemini** via CrewAI when `GEMINI_API_KEY` / `GOOGLE_API_KEY` is set; otherwise heuristics-only paths apply. |
| **Catalog** | `parts.json` + `parts_catalog.py` — bundled parts, prices, and compatibility inputs. |
| **Pricing** | `price_comparison.py`, `amazon_api.py`, `ebay_api.py` — optional live checks when API keys exist; otherwise catalog/list pricing. |
| **ELI5** | `eli5.py` + `POST /explain` — plain-English explanation of a completed build (requires Gemini API key). |

## Repository layout

```text
gestalt/
├── app.py                 # Flask: /, /build, /build/stream, /explain
├── crew.py                # Analysis + recommendation + validation trace
├── agents.py              # CrewAI agents / LLM resolution
├── intake.py              # Pre-build clarification
├── compatibility_checker.py
├── parts_catalog.py, parts.json
├── amazon_api.py, ebay_api.py, price_comparison.py
├── eli5.py
├── templates/index.html
├── static/hexcore.css
├── tests/                 # pytest (unit + e2e pipeline)
├── .env.example
├── pyproject.toml
└── README.md
```

Versioned alongside the app: `LICENSE`, `.gitignore`, `.python-version`.

## Quick start

```bash
cd Gestalt
uv sync
cp .env.example .env
# Set GEMINI_API_KEY (Google AI Studio) for CrewAI + ELI5 — see .env.example
uv run gestalt-web
# http://127.0.0.1:5000
```

CLI entrypoint: **`gestalt-web`** → `app:main` (Flask dev server). Defaults to **http://127.0.0.1:5000**; set **`PORT`** and **`HOST=0.0.0.0`** if you need another bind (e.g. container or LAN).

```bash
uv run python crew.py
```

### Deploy on [Render](https://render.com) (Web Service)

Use **Python 3**, branch **`main`**, empty **Root Directory** if this repo is the app root.

**Build Command** (pick one):

- **pip (works without a valid `uv.lock`):**  
  `pip install --upgrade pip && pip install .`
- **uv (if your lockfile syncs cleanly):**  
  `uv sync --frozen --no-dev && uv cache prune --ci`

**Start Command** (production WSGI — do **not** use `flask run` / `gestalt-web` on Render):

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --worker-class gthread --timeout 300
```

Render sets **`PORT`** automatically. Use **`--timeout 300`** (or higher) so long **SSE** `/build/stream` responses are less likely to be cut off.

**Environment variables** in the Render dashboard (mirror `.env.example`):

| Variable | Notes |
|----------|--------|
| **`GEMINI_API_KEY`** or **`GOOGLE_API_KEY`** | Required for full CrewAI + ELI5 behavior. |
| **`GESTALT_LLM_MODEL`** | Optional LiteLLM id for Crew (e.g. `gemini/gemini-2.5-flash`). |
| **`GESTALT_ELI5_MODEL`** | Optional `google.genai` model id for `/explain`. |
| **`RAINFOREST_API_KEY`**, **`SCRAPINGBEE_API_KEY`** | Optional live pricing. |
| **`FLASK_DEBUG`** | Omit or `0` in production. |

Optional: commit **`render.yaml`** and use Render **Blueprint** to provision the service; edit `plan` / `name` as needed.

## Environment variables

Copy **`.env.example`** → **`.env`** (never commit `.env`). Important keys:

- **`GEMINI_API_KEY`** or **`GOOGLE_API_KEY`** — CrewAI agents and ELI5 (`eli5.py`).
- **`GESTALT_LLM_MODEL`** — optional CrewAI / LiteLLM model id (e.g. `gemini/gemini-2.5-flash`).
- **`GESTALT_ELI5_MODEL`**, **`GESTALT_GEMINI_SMOKE_MODEL`** — optional native `google.genai` model ids for ELI5 and smoke tests.
- **`RAINFOREST_API_KEY`**, **`SCRAPINGBEE_API_KEY`** — optional live Amazon / eBay pricing.
- **`GESTALT_PC_BUILD_SERVICE_RATE`** — optional fraction for “build service fee avoided” in savings rollup.

## HTTP API (for the UI and tests)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | Main UI |
| `GET` | `/healthz` | Health + optional metadata (`version`, `commit`) for deploy checks and judge scans. |
| `POST` | `/build` | JSON body: `prompt`, optional `original_prompt` + `clarification_answers`. Returns JSON build result or clarification payload. |
| `POST` | `/build/stream` | Same body; **SSE** (`text/event-stream`) using proper SSE fields: `event: trace|clarify|complete|error` with JSON in `data:`. Includes keepalive comment frames (`: keepalive`). |
| `POST` | `/explain` | JSON: `build` (object), optional `analysis`. Returns `{ "eli5": "..." }` or error (503 if no API key for ELI5). |

### Request validation

Requests to `/build`, `/build/stream`, and `/explain` are validated with **Pydantic** at the HTTP boundary (see `schemas.py`). Unknown fields are ignored; invalid shapes return **400** with a `details` list.

## Testing

**Default (CI-friendly, no network):**

```bash
uv run pytest tests/ -q
```

- **Unit / component tests** — parsing, compatibility, intake, pricing math, crew helpers, mocked CrewAI, ELI5 helpers, etc.
- **End-to-end pipeline** — `tests/test_e2e_pipeline.py` (marker **`e2e`**): Flask test client against **`GET /`**, **`POST /build`**, **`POST /build/stream`**, **`POST /explain`** with **`app.run_build_assistant`** and ELI5 **mocked** (no live LLM, no retailer APIs). Uses the real **parts catalog** to build a deterministic JSON crew payload.

Run only e2e tests:

```bash
uv run pytest tests/test_e2e_pipeline.py -v
# or
uv run pytest -m e2e -v
```

**Optional integration / smoke (needs keys or network):**

```bash
uv run pytest tests/test_gemini_smoke.py -v
```

Mark **`integration`** is reserved for tests that need real API keys or network (see `pyproject.toml` markers).

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
