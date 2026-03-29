# Our Project

## Problem

PC buyers juggle incompatible parts, opaque pricing, and dozens of retailer tabs. A “good” parts list on paper can fail in the real world (wrong CPU socket, RAM generation, PSU headroom, or GPU too long for the case), and the cheapest total rarely lives on a single store. Builders need **fast, explainable compatibility checks** and a **fair sense of where to buy**—without manually searching Amazon and eBay for every component.

## Solution

**Gestalt** is a PC builder assistant that:

1. **Understands a natural-language build request** (budget, use case, priorities) via **CrewAI** agents backed by a **Gemini** LLM.
2. **Selects parts from a curated catalog** (`parts.json`) with budget allocation rules (gaming / creative / general).
3. **Validates the build deterministically** (`compatibility_checker.py`)—socket, DDR generation, PSU wattage margin, GPU vs case clearance—so recommendations are mechanically sound.
4. **Surfaces live market prices** by comparing **Amazon** (Rainforest API) and **eBay** (ScrapingBee + HTML parse), merging them with list prices in **`price_comparison.py`** so the UI can show per-part and rollup savings when API keys are set in **`.env`**.

The stack is a small **Flask** app (`app.py`) with a modern front end: users submit a prompt, get a validated build JSON (and optional streaming agent trace), with pricing enrichment applied safely so a failed retailer API never breaks the response.

---

## Architecture

**How it works technically**

- **Web layer:** Flask serves `templates/index.html` and static assets; `POST /build` and `POST /build/stream` invoke `crew.run_build_assistant`, parse JSON, then optionally call `price_comparison.enrich_crew_payload_with_pricing` (wrapped so errors never crash the handler).

- **Agent layer:** `agents.py` defines analysis and recommendation agents; `crew.py` orchestrates a sequential Crew: extract budget/use case → recommend part IDs from the injected catalog → map IDs to full part dicts → `validate_build` → retry on validation errors with the error message fed back. Traces can stream over SSE for transparency.

- **Data & rules:** `parts_catalog.load_parts_catalog()` reads bundled `parts.json` (or a tiny embedded fallback). `compatibility_checker` implements pure-Python checks; no LLM in the validation path.

- **Live pricing:** `amazon_api.search_amazon` / `get_amazon_price` call Rainforest’s `type=search` endpoint; `ebay_api.scrape_ebay_price` / `get_ebay_price` route eBay search URLs through ScrapingBee (`render_js=false`, short timeout) and parse results with **BeautifulSoup**. `get_all_prices` and `enrich_build_with_prices` normalize success/failure per retailer; `rollup_pricing` aggregates catalog vs live totals and savings for the payload the UI consumes.

- **Configuration:** Secrets (`GEMINI_API_KEY`, `RAINFOREST_API_KEY`, `SCRAPINGBEE_API_KEY`, etc.) live in **`.env`** (see `.env.example`); `python-dotenv` loads them in `app.py` and `crew.py`.

```text
Browser → Flask → CrewAI + catalog + compatibility_checker → JSON
                    ↓
              (optional) Rainforest + ScrapingBee → price_comparison → enriched JSON
```

---

## Features

- **Natural-language build analysis** — Budget, use case, and constraints from free-form text.
- **Catalog-grounded recommendations** — Parts chosen by ID from `parts.json`, not hallucinated SKUs.
- **Deterministic compatibility validation** — CPU/socket, RAM/DDR, PSU headroom, GPU length vs case; structured errors with codes and suggested fixes.
- **Retry loop on validation failure** — Recommendation task can revise picks using the validator’s error message.
- **Live dual-retailer pricing** — Amazon via Rainforest; eBay via ScrapingBee (proxies/CAPTCHAs handled by ScrapingBee); graceful degradation if one side or both fail.
- **Pricing rollups** — Per-slot `price_comparison`, totals, and savings estimates for the UI when keys are present.
- **Streaming build option** — `/build/stream` for progressive agent trace (where wired in the UI).
- **Hackathon-friendly ops** — `uv` + `pyproject.toml`, pytest tests for core modules, `.env.example` for onboarding.

---

## Team Plan

*Who is doing what — adjust names and split to match your squad.*

| Area | Owner(s) | Notes |
|------|-----------|--------|
| **LLM prompts & Crew flow** | *TBD* | `agents.py`, `crew.py` — analysis/recommendation wording, retry behavior, trace size limits |
| **Compatibility & catalog** | *TBD* | `compatibility_checker.py`, `parts.json` / `parts_catalog.py` — data quality and edge cases |
| **Amazon + Rainforest** | *TBD* | `amazon_api.py` — search params, parsing first result, error handling |
| **eBay + ScrapingBee** | *TBD* | `ebay_api.py` — URL shape, BS4 selectors, BIN vs auction heuristics |
| **Price comparison & rollups** | *TBD* | `price_comparison.py` — `get_all_prices`, enrich payload, rollup math, env keys |
| **Flask API & front end** | *TBD* | `app.py`, `templates/`, `static/` — `/build`, streaming, UX polish |
| **Demo & README** | *TBD* | Record demo, fill hackathon submission, verify `.env` for judges |

**Milestone sketch:** (1) End-to-end happy path with catalog-only pricing → (2) Wire Rainforest + ScrapingBee keys → (3) Polish UI and demo script → (4) Freeze `parts.json` and run regression tests.
