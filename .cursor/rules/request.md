# Request (feature contracts)

## When this applies
Before generating **new** user-facing behaviour, agents, tasks, tools, APIs, or config surfaces.

## Required upfront (in natural language + schemas where it helps)
1. **Inputs**: names, types, validation rules, defaults, and what is *invalid*.
2. **Outputs**: shape and semantics (e.g. JSON fields, file paths, Crew task `expected_output`).
3. **Errors / edge cases**: what can fail, how callers know, and what must **not** happen silently.
4. **Side effects**: network I/O, filesystem, env vars, external APIs.
5. **Acceptance**: bullet list of checks that prove the feature is done (maps 1:1 to tests where possible).

## Process
- Present the contract **first** in the assistant reply; only then propose file-level edits.
- If the user’s request is ambiguous, list **assumptions** explicitly and ask one concise clarifying question if a wrong assumption would materially change the contract.

## Anti-patterns
- Diving into `crew.py` / `tools/` / integrations without the contract block above.
- “I’ll figure out the API while coding” for anything beyond trivial refactors.
