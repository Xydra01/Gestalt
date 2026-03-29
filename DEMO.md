# Demo runbook (copy/paste)

This is a short script you can follow live. It is designed to show: intake → streaming trace → validation → pricing → ELI5.

## Setup

1. Start the app:

```bash
uv run gestalt-web
# or: python3 app.py
```

2. Open the UI at `http://127.0.0.1:5000`.

## 1) Happy path (stream + final build)

Paste:

> Build me a gaming PC for $1000

Expected:
- Status badge shows “Working”.
- Terminal shows streaming trace entries (analysis + recommendation + compatibility check).
- Parts table appears with totals and buy links (when pricing keys are configured).

## 2) Clarify path (user didn’t give enough info)

Paste:

> I want a computer

Expected:
- UI shows an “A bit more detail helps” panel with follow-up questions.
- Terminal shows an Intake summary.

## 3) Clarify → “Build anyway” (non-engaging user)

When the clarify panel appears:
- Click **Build anyway (assume ~$1000)** without typing.

Expected:
- The system proceeds and returns a build without the user specifying a budget.

## 4) Validation failure and retry (compatibility check in plain English)

Paste something that increases the chance of a mismatch (the LLM may still pick compatible parts, but when it fails you’ll see the retry behavior):

> Build me a small ITX gaming PC with a huge GPU, keep it cheap

Expected when validation fails:
- Terminal shows **Compatibility check** failure with a plain-English message and a “Fix:” line.
- The system retries (up to the configured number of attempts).

## 5) ELI5 explanation (with and without a key)

After a successful build, click:
- **Explain Like I’m a Beginner**

Expected:
- If `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set: explanation text appears.
- If no key: the UI shows an error (service returns 503) explaining the missing key.

## 6) Pricing: live vs catalog fallback

Run the happy path again with and without pricing keys:

- Without `RAINFOREST_API_KEY` / `SERPAPI_API_KEY`:
  - Prices show as catalog-based; savings rollup still works.
- With keys set:
  - Effective price uses live retailer data when available and includes buy URLs.

