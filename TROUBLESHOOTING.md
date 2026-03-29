# Troubleshooting

## Streaming (SSE) issues

### Symptoms
- The log stays stuck on “Connecting to crew stream…”
- No trace messages arrive
- The request completes only at the end (no incremental updates)

### Checks
- **Browser support**: modern Chrome/Firefox/Safari should work. If you’re using an older browser, streaming `ReadableStream` support may be missing.
- **Reverse proxies**: some proxies buffer responses by default. The app sets `X-Accel-Buffering: no`, but you may still need proxy configuration.
- **Timeouts**: long streams can be cut off by hosting platforms. On Render, use a higher Gunicorn timeout (see README).

### What the server emits
`/build/stream` uses spec-compliant SSE frames:
- `event: trace|clarify|complete|error`
- JSON in `data:`
- periodic keepalive comment frames: `: keepalive`

## Missing API keys

### Gemini (CrewAI + ELI5)
If `GEMINI_API_KEY` / `GOOGLE_API_KEY` is missing:
- Intake falls back to heuristics.
- Crew can still return a build via heuristics paths.
- `/explain` returns **503** (ELI5 requires Gemini).

### Pricing
If `RAINFOREST_API_KEY` and/or `SCRAPINGBEE_API_KEY` is missing:
- Live pricing is unavailable.
- The UI uses catalog/list prices from `parts.json` as fallback.

## Render deployment gotchas

- Use Gunicorn (not Flask dev server) with a higher timeout for streaming routes:\n  `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --worker-class gthread --timeout 300`\n- Ensure the service is on a plan that supports long-running connections if you stream long builds.

## “Build finished without a result.”

This indicates the worker thread exited without a payload. Common causes:
- Exceptions during crew execution
- Invalid JSON from a mocked or misconfigured LLM output

Check the terminal trace entries and server logs for the last emitted `error` event.

