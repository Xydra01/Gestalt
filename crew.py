"""Gestalt PC build crew — analysis, recommendation (with retries), deterministic validation."""

from __future__ import annotations

import contextvars
import json
import os
import queue
import re
from pathlib import Path
from typing import Any

from crewai import Crew, Process, Task
from dotenv import load_dotenv

from agents import analysis_agent, recommendation_agent, resolve_llm
from compatibility_checker import validate_build
from parts_catalog import load_parts_catalog

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

# Cap LLM TaskOutput payloads embedded in ``agent_trace`` (UI / JSON size).
_TRACE_RAW_MAX = 12_000
_TRACE_MSG_TAIL = 25

# CrewAI ``task_callback`` must be a plain module-level function (pickle-friendly).
_agent_trace_buffer: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "gestalt_agent_trace_buffer", default=None
)
_task_trace_phase: contextvars.ContextVar[str] = contextvars.ContextVar("gestalt_task_trace_phase", default="")
_stream_queue: contextvars.ContextVar[queue.Queue | None] = contextvars.ContextVar(
    "gestalt_stream_queue", default=None
)


def _emit_trace_step(agent_trace: list[dict[str, Any]]) -> None:
    """Push the latest trace entry to the optional SSE queue (same thread as crew)."""
    q = _stream_queue.get()
    if q is None or not agent_trace:
        return
    q.put({"event": "trace", "entry": agent_trace[-1]})


def gestalt_crew_task_trace_handler(output: Any) -> None:
    """Append serialized :class:`~crewai.tasks.task_output.TaskOutput` to the active trace."""
    buf = _agent_trace_buffer.get()
    if buf is None:
        return
    phase = _task_trace_phase.get() or "crew"
    _trace_task_completed(buf, phase, output)

# --- Fallback when the LLM returns prose or invalid JSON ----------------------------

DEFAULT_ANALYSIS: dict[str, Any] = {
    "budget": 1000,
    "use_case": "general productivity",
    "priority": "balanced",
    "constraints": [],
}

# Project plan percentages (gaming / creative / general)
BUDGET_ALLOCATIONS: dict[str, dict[str, float]] = {
    "gaming": {
        "gpu": 0.40,
        "cpu": 0.20,
        "mobo": 0.15,
        "ram": 0.10,
        "psu": 0.10,
        "case": 0.05,
    },
    "creative": {
        "gpu": 0.25,
        "cpu": 0.30,
        "mobo": 0.15,
        "ram": 0.15,
        "psu": 0.10,
        "case": 0.05,
    },
    "general": {
        "gpu": 0.15,
        "cpu": 0.35,
        "mobo": 0.20,
        "ram": 0.15,
        "psu": 0.10,
        "case": 0.05,
    },
}


def _parse_json_object_from_llm_text(text: str) -> dict[str, Any] | None:
    """Best-effort JSON object extraction from raw LLM output."""
    if not text or not str(text).strip():
        return None
    t = str(text).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(t[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def parse_analysis_result(raw: str) -> dict[str, Any]:
    """Parse crew kickoff output into an analysis dict; fall back to DEFAULT_ANALYSIS."""
    data = _parse_json_object_from_llm_text(raw)
    if not data:
        return {**DEFAULT_ANALYSIS}
    out = {**DEFAULT_ANALYSIS}
    b = data.get("budget")
    if isinstance(b, (int, float)) and b > 0:
        out["budget"] = int(round(float(b)))
    if isinstance(data.get("use_case"), str) and data["use_case"].strip():
        out["use_case"] = data["use_case"].strip()
    if isinstance(data.get("priority"), str) and data["priority"].strip():
        out["priority"] = data["priority"].strip()
    c = data.get("constraints")
    if isinstance(c, list):
        out["constraints"] = [str(x) for x in c if str(x).strip()]
    elif isinstance(c, str) and c.strip():
        out["constraints"] = [c.strip()]
    return out


def resolve_allocation_category(use_case: str) -> str:
    """Map free-text use_case to gaming | creative | general."""
    s = use_case.lower()
    # "game" alone is not a substring of "gaming"; match whole-word / explicit forms
    if re.search(r"\b(gaming|game)\b", s):
        return "gaming"
    if any(
        k in s
        for k in (
            "creative",
            "edit",
            "video",
            "photo",
            "render",
            "production",
            "stream",
            "3d",
        )
    ):
        return "creative"
    return "general"


def budget_rules_for_analysis(analysis: dict[str, Any]) -> tuple[str, dict[str, float], dict[str, float]]:
    """Return (category_key, percentage_rules, usd_per_category)."""
    category = resolve_allocation_category(str(analysis.get("use_case", "")))
    pct = BUDGET_ALLOCATIONS[category]
    budget = int(analysis.get("budget") or DEFAULT_ANALYSIS["budget"])
    usd = {k: round(budget * v, 2) for k, v in pct.items()}
    return category, pct, usd


def extract_budget_from_prompt(text: str) -> int | None:
    """Heuristic: pull a dollar amount from natural language (e.g. $1500)."""
    if not text:
        return None
    m = re.search(r"\$\s*([\d]{1,3}(?:,\d{3})+|\d+)", text)
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    try:
        n = int(digits)
        return n if n > 0 else None
    except ValueError:
        return None


def infer_use_case_from_prompt(text: str) -> str | None:
    """When no LLM is available, infer use_case from keywords (hackathon fallback)."""
    t = text.lower()
    if any(
        k in t
        for k in (
            "edit",
            "editing",
            "video",
            "photo",
            "render",
            "creative",
            "stream",
            "davinci",
            "premiere",
            "after effects",
        )
    ):
        return "creative work"
    if re.search(r"\b(gaming|game)\b", t):
        return "gaming"
    return None


# --- Parts catalog -------------------------------------------------------------------


def load_parts() -> dict[str, Any]:
    """Backward-compatible: full catalog dict only (see :func:`load_parts_catalog` for source)."""
    data, _src = load_parts_catalog()
    return data


# --- Recommendation: prompt, parse IDs, map to parts ---------------------------------

# Order used when assembling the final build dict (Selector slot name -> catalog category key).
RECOMMENDATION_SLOTS: list[str] = ["cpu", "gpu", "motherboard", "ram", "psu", "case"]
SLOT_TO_PARTS_KEY: dict[str, str] = {
    "cpu": "cpus",
    "gpu": "gpus",
    "motherboard": "motherboards",
    "ram": "ram",
    "psu": "psus",
    "case": "cases",
}


def extract_hard_part_constraints(user_input: str) -> dict[str, str]:
    """
    Extract "hard" constraints from the raw user prompt, keyed by build slot.

    This is intentionally heuristic, but it is deterministic. The goal is to prevent
    the selector from drifting away from explicit user requests like "RTX 4070" or
    "Ryzen 5 7600X".
    """
    t = (user_input or "").strip()
    if not t:
        return {}
    s = t.lower()
    out: dict[str, str] = {}

    # GPU: RTX / RX lines
    m = re.search(r"\b(rtx)\s*([0-9]{3,4})\b", s)
    if m:
        out["gpu"] = f"{m.group(1)} {m.group(2)}"
    m = re.search(r"\b(rx)\s*([0-9]{3,4})\b", s)
    if m:
        out["gpu"] = f"{m.group(1)} {m.group(2)}"

    # CPU: Ryzen family + model, and Intel i5/i7/i9 patterns
    m = re.search(r"\b(ryzen)\s*([3579])\s*([0-9]{4,5}[a-z]?)\b", s)
    if m:
        out["cpu"] = f"{m.group(1)} {m.group(2)} {m.group(3)}"
    m = re.search(r"\b(i[3579])\s*[- ]?\s*([0-9]{4,5}[a-z]?)\b", s)
    if m:
        out["cpu"] = f"{m.group(1)} {m.group(2)}"

    # Motherboard: chipsets that appear in typical prompts (B650 / Z790 / B550 etc)
    m = re.search(r"\b([abxz])\s*([0-9]{3})\b", s)
    if m:
        out["motherboard"] = f"{m.group(1)}{m.group(2)}"

    # RAM: 16GB/32GB/64GB
    m = re.search(r"\b(16|32|64)\s*gb\b", s)
    if m:
        out["ram"] = f"{m.group(1)}gb"

    # PSU: wattage
    m = re.search(r"\b([5-9][0-9]{2,3})\s*w\b", s)
    if m:
        out["psu"] = f"{m.group(1)}w"

    # Case: form factors / size adjectives
    if "itx" in s:
        out["case"] = "itx"
    elif "mid" in s and "tower" in s:
        out["case"] = "mid tower"
    elif "full" in s and "tower" in s:
        out["case"] = "full tower"

    return out


def _tokenize_constraint(q: str) -> list[str]:
    return [x for x in re.split(r"[^a-z0-9]+", (q or "").lower()) if x]


def _best_match_part_for_query(rows: list[Any], query: str) -> dict[str, Any] | None:
    """
    Pick the best matching catalog part for the given free-text query.

    Strategy: score each row by token containment in its name/title/model/id.
    """
    toks = _tokenize_constraint(query)
    if not toks:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    for item in rows:
        if not isinstance(item, dict):
            continue
        blob = " ".join(
            str(item.get(k, "")).lower()
            for k in ("name", "title", "model", "id", "chipset", "series")
        )
        score = sum(1 for tok in toks if tok in blob)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, item)
    return best[1] if best is not None else None


def apply_hard_constraints_to_build(
    build: dict[str, Any], parts_data: dict[str, Any], hard: dict[str, str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Apply extracted hard constraints by overriding selected parts when a strong match exists.

    Returns the updated build and a list of applied overrides for trace/debug.
    """
    if not hard:
        return build, []
    out = {**build}
    applied: list[dict[str, Any]] = []
    # Apply in a compatibility-aware order so later overrides can respect earlier ones.
    order = ["cpu", "gpu", "motherboard", "ram", "psu", "case"]
    for slot in order:
        if slot not in hard:
            continue
        q = hard.get(slot, "")
        if slot not in RECOMMENDATION_SLOTS:
            continue
        key = SLOT_TO_PARTS_KEY[slot]
        rows: list[Any] = parts_data.get(key) if isinstance(parts_data.get(key), list) else []

        # Special-case RAM: if the motherboard has an explicit DDR support, only consider matching RAM.
        if slot == "ram":
            mobo = out.get("motherboard")
            if isinstance(mobo, dict):
                want_ddr = mobo.get("ddr_support")
                if isinstance(want_ddr, str) and want_ddr.strip():
                    filtered: list[Any] = []
                    for r in rows:
                        if not isinstance(r, dict):
                            continue
                        gen = r.get("ddr_gen")
                        if want_ddr == "DDR4/DDR5":
                            if gen in ("DDR4", "DDR5"):
                                filtered.append(r)
                        elif gen == want_ddr:
                            filtered.append(r)
                    if filtered:
                        rows = filtered

        match = _best_match_part_for_query(rows, q)
        if match is None:
            continue
        prev = out.get(slot) if isinstance(out.get(slot), dict) else {}
        if isinstance(prev, dict) and prev.get("id") == match.get("id"):
            continue
        out[slot] = match
        applied.append(
            {
                "slot": slot,
                "constraint": q,
                "picked_id": match.get("id"),
                "picked_name": match.get("name") or match.get("title") or match.get("model"),
                "replaced_id": prev.get("id") if isinstance(prev, dict) else None,
            }
        )
    return out, applied


def add_confidence_scores(
    build: dict[str, Any],
    *,
    hard: dict[str, str],
    rules_usd: dict[str, float],
) -> dict[str, Any]:
    """
    Attach a simple, explainable confidence score per part.

    Score is 0..1 based on:
    - matches explicit hard constraint for that slot
    - stays within the per-slot budget allocation (soft)
    """
    out: dict[str, Any] = {**build}
    for slot in RECOMMENDATION_SLOTS:
        part = out.get(slot)
        if not isinstance(part, dict):
            continue
        score = 0.6
        reasons: list[str] = []

        # Constraint match boosts confidence
        cq = hard.get(slot)
        if cq:
            toks = _tokenize_constraint(cq)
            blob = " ".join(str(part.get(k, "")).lower() for k in ("name", "title", "model", "id"))
            hit = sum(1 for tok in toks if tok in blob)
            if hit >= max(1, len(toks) // 2):
                score += 0.3
                reasons.append(f"Matches your request ({cq}).")
            else:
                score -= 0.25
                reasons.append(f"Does not closely match requested constraint ({cq}).")

        # Budget alignment (soft): within 15% of slot allocation is "good"
        alloc = rules_usd.get("mobo" if slot == "motherboard" else slot)
        price = part.get("price")
        if isinstance(alloc, (int, float)) and isinstance(price, (int, float)) and alloc > 0:
            if float(price) <= float(alloc) * 1.15:
                score += 0.1
                reasons.append("Fits the budget allocation for this slot.")
            else:
                score -= 0.1
                reasons.append("A bit over the budget allocation for this slot.")

        score = max(0.0, min(1.0, round(score, 2)))
        merged = {**part}
        merged["confidence"] = {"score": score, "reasons": reasons}
        out[slot] = merged
    return out


def draft_recommendation_prompt(
    analysis: dict[str, Any],
    error: str | None,
    allocation_category: str,
    rules_pct: dict[str, float],
    rules_usd: dict[str, float],
    parts_data: dict[str, Any],
) -> str:
    """
    Task description for the Selector agent: same intent as agents._RECOMMENDATION_PROMPT,
    with analysis, optional error text, calculated budget rules, and full parts JSON.
    """
    analysis_s = json.dumps(analysis, indent=2)
    err_s = error or ""
    previous_validation_line = ("Previous validation error: " + err_s) if err_s else ""
    rules_pct_s = json.dumps(rules_pct, indent=2)
    rules_usd_s = json.dumps(rules_usd, indent=2)
    parts_s = json.dumps(parts_data, indent=2)
    return f"""You are a PC parts selector. You have access to the full parts catalog below (bundled JSON).
Given this build analysis: {analysis_s}
{previous_validation_line}

Calculated allocation category: {allocation_category}
Budget allocation (USD per slot — keys: gpu, cpu, mobo, ram, psu, case):
{rules_usd_s}
Rule fractions (same keys):
{rules_pct_s}

Full parts catalog (JSON):
{parts_s}

Select one part from each category that:
- Fits within the budget allocation for that slot
- Matches the use case tier
- Does NOT repeat any part that previously caused a validation error

Return ONLY a JSON object with exactly this shape (no markdown, no commentary):
{{"selected_ids": {{"cpu": "<id>", "gpu": "<id>", "motherboard": "<id>", "ram": "<id>", "psu": "<id>", "case": "<id>"}}}}
Each value must be the "id" field of a part from the catalog above. All six keys are required."""


def _find_part_by_id(parts_list: list[Any], part_id: str) -> dict[str, Any] | None:
    for item in parts_list:
        if isinstance(item, dict) and str(item.get("id")) == part_id:
            return item
    return None


def parse_selected_ids(raw: str) -> dict[str, str]:
    """Extract selected_ids from LLM output; returns slot -> part id."""
    data = _parse_json_object_from_llm_text(raw)
    if not data:
        return {}
    inner = data.get("selected_ids")
    if not isinstance(inner, dict):
        return {}
    out: dict[str, str] = {}
    for slot in RECOMMENDATION_SLOTS:
        v = inner.get(slot)
        if isinstance(v, str) and v.strip():
            out[slot] = v.strip()
    return out


def build_dict_from_selected_ids(
    selected_ids: dict[str, str],
    parts_data: dict[str, Any],
) -> dict[str, Any]:
    """
    For each slot in RECOMMENDATION_SLOTS, resolve the chosen id to a full part dict.
    If missing or unknown id, use the first available part in that category.
    """
    build: dict[str, Any] = {}
    for slot in RECOMMENDATION_SLOTS:
        key = SLOT_TO_PARTS_KEY[slot]
        items = parts_data.get(key)
        rows: list[Any] = items if isinstance(items, list) else []
        want = selected_ids.get(slot, "")
        part: dict[str, Any] | None = None
        if want:
            found = _find_part_by_id(rows, want)
            if found is not None:
                part = found
        if part is None and rows:
            first = rows[0]
            part = first if isinstance(first, dict) else None
        build[slot] = part if part is not None else {}
    return build


def total_price_for_build(build: dict[str, Any]) -> float:
    """Sum ``price`` across recommendation slots (missing price treated as 0)."""
    total = 0.0
    for slot in RECOMMENDATION_SLOTS:
        p = build.get(slot)
        if isinstance(p, dict):
            pr = p.get("price")
            if isinstance(pr, (int, float)):
                total += float(pr)
    return round(total, 2)


def _task_output_to_trace_dict(output: Any, crew_phase: str) -> dict[str, Any]:
    """Serialize a CrewAI :class:`TaskOutput` (or fallback) for ``agent_trace``."""
    if hasattr(output, "model_dump"):
        d = output.model_dump()
    else:
        d = {"raw": str(output), "agent": "unknown", "description": ""}
    d["kind"] = "llm_task_output"
    d["crew_phase"] = crew_phase
    raw = d.get("raw")
    if isinstance(raw, str) and len(raw) > _TRACE_RAW_MAX:
        d["raw"] = raw[:_TRACE_RAW_MAX] + "...(truncated)"
    msgs = d.get("messages")
    if isinstance(msgs, list) and msgs:
        slim: list[Any] = []
        for m in msgs[-_TRACE_MSG_TAIL:]:
            if hasattr(m, "model_dump"):
                slim.append(m.model_dump())
            elif isinstance(m, dict):
                slim.append(m)
            else:
                slim.append(str(m))
        d["messages"] = slim
    return d


def _trace_task_completed(
    agent_trace: list[dict[str, Any]],
    crew_phase: str,
    output: Any,
) -> None:
    """Append one task output dict (used by :func:`gestalt_crew_task_trace_handler` and tests)."""
    agent_trace.append(_task_output_to_trace_dict(output, crew_phase))
    _emit_trace_step(agent_trace)


# -------------------------------------------------------------------------------------


def run_build_assistant(user_input: str, stream_queue: queue.Queue | None = None) -> str:
    """
    Analysis (once) → recommendation loop (up to 3) with ``validate_build`` after each
    Proposed build. Collects ``agent_trace`` for UI (task outputs + validation steps).

    If ``stream_queue`` is set, each new trace entry is pushed as
    ``{"event": "trace", "entry": ...}`` for SSE clients.

    Success: ``success``, ``build``, ``total``, ``savings`` (35% of total), ``analysis``, ``agent_trace``.
    Exhausted retries: ``success: false``, ``error``, ``agent_trace``.
    """
    parts_data, parts_catalog_source = load_parts_catalog()
    agent_trace: list[dict[str, Any]] = [
        {
            "kind": "session_start",
            "user_input": user_input,
            "parts_catalog_source": parts_catalog_source,
        }
    ]
    trace_tok = _agent_trace_buffer.set(agent_trace)
    stream_tok = _stream_queue.set(stream_queue) if stream_queue is not None else None

    _emit_trace_step(agent_trace)
    raw_output = ""
    llm_ready = resolve_llm() is not None
    if llm_ready:
        agent_trace.append({"kind": "phase", "phase": "analysis", "status": "started"})
        _emit_trace_step(agent_trace)
        analyst = analysis_agent()
        analysis_task = Task(
            description=(
                f"User request:\n{user_input}\n\n"
                "Your output must be ONLY a single valid JSON object with exactly these keys:\n"
                '  "budget" — number, total budget in USD (integer or float)\n'
                '  "use_case" — string, one of: gaming, creative work, general productivity, development\n'
                '  "priority" — string: max fps, max quality, or balanced\n'
                '  "constraints" — array of strings (use [] if none)\n'
                "Do not wrap in markdown. Do not add commentary. JSON only."
            ),
            expected_output=(
                '{"budget": <number>, "use_case": "<string>", "priority": "<string>", '
                '"constraints": [<strings>]}'
            ),
            agent=analyst,
        )

        phase_tok = _task_trace_phase.set("analysis")
        try:
            crew = Crew(
                agents=[analyst],
                tasks=[analysis_task],
                process=Process.sequential,
                verbose=True,
                task_callback=gestalt_crew_task_trace_handler,
            )
            try:
                raw_output = str(crew.kickoff())
            except Exception as e:
                raw_output = json.dumps({"_crew_error": str(e)})
                agent_trace.append({"kind": "crew_error", "phase": "analysis", "message": str(e)})
                _emit_trace_step(agent_trace)
        finally:
            _task_trace_phase.reset(phase_tok)

    try:
        analysis = parse_analysis_result(raw_output)
    except (json.JSONDecodeError, TypeError, KeyError):
        analysis = {**DEFAULT_ANALYSIS}

    hinted = extract_budget_from_prompt(user_input)
    if hinted is not None:
        analysis["budget"] = hinted

    if not llm_ready:
        inferred_uc = infer_use_case_from_prompt(user_input)
        if inferred_uc:
            analysis["use_case"] = inferred_uc

    agent_trace.append(
        {
            "kind": "analysis_complete",
            "parsed_analysis": analysis,
            "llm_used": llm_ready,
        }
    )
    _emit_trace_step(agent_trace)

    category, rules_pct, rules_usd = budget_rules_for_analysis(analysis)
    hard = extract_hard_part_constraints(user_input)
    if hard:
        agent_trace.append({"kind": "hard_constraints", "constraints": hard})
        _emit_trace_step(agent_trace)

    error: str | None = None
    max_retries = 3

    for attempt in range(max_retries):
        agent_trace.append(
            {
                "kind": "retry_attempt",
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "prior_validation_error": error,
            }
        )
        _emit_trace_step(agent_trace)

        recommendation_result = ""
        if llm_ready:
            recommender = recommendation_agent()
            recommendation_prompt = draft_recommendation_prompt(
                analysis=analysis,
                error=error or "",
                allocation_category=category,
                rules_pct=rules_pct,
                rules_usd=rules_usd,
                parts_data=parts_data,
            )
            recommendation_task = Task(
                description=recommendation_prompt,
                expected_output='{"selected_ids": {"cpu": "...", "gpu": "...", ...}}',
                agent=recommender,
            )
            phase_tok = _task_trace_phase.set(f"recommendation_attempt_{attempt + 1}")
            try:
                rec_crew = Crew(
                    agents=[recommender],
                    tasks=[recommendation_task],
                    process=Process.sequential,
                    verbose=True,
                    task_callback=gestalt_crew_task_trace_handler,
                )
                try:
                    recommendation_result = str(rec_crew.kickoff())
                except Exception as e:
                    recommendation_result = json.dumps({"_crew_error": str(e)})
                    agent_trace.append(
                        {
                            "kind": "crew_error",
                            "phase": "recommendation",
                            "attempt": attempt + 1,
                            "message": str(e),
                        }
                    )
                    _emit_trace_step(agent_trace)
            finally:
                _task_trace_phase.reset(phase_tok)
        else:
            agent_trace.append(
                {
                    "kind": "recommendation_skipped",
                    "reason": "no_llm_configured",
                    "attempt": attempt + 1,
                }
            )
            _emit_trace_step(agent_trace)

        selected_ids: dict[str, str] = {}
        try:
            selected_ids = parse_selected_ids(recommendation_result)
        except (TypeError, ValueError, KeyError):
            selected_ids = {}

        build = build_dict_from_selected_ids(selected_ids, parts_data)
        build, applied = apply_hard_constraints_to_build(build, parts_data, hard)
        if applied:
            agent_trace.append({"kind": "constraints_applied", "applied": applied, "attempt": attempt + 1})
            _emit_trace_step(agent_trace)
        validation = validate_build(build)

        agent_trace.append(
            {
                "kind": "validation",
                "attempt": attempt + 1,
                "passed": validation.get("passed"),
                "errors": validation.get("errors", []),
            }
        )
        _emit_trace_step(agent_trace)

        if validation.get("passed") is True:
            build = add_confidence_scores(build, hard=hard, rules_usd=rules_usd)
            agent_trace.append({"kind": "confidence_scored", "attempt": attempt + 1})
            _emit_trace_step(agent_trace)
            if applied:
                agent_trace.append(
                    {
                        "kind": "assistant_note",
                        "title": "We honored your constraints",
                        "message": "I swapped a few parts to match what you explicitly asked for, while keeping everything compatible.",
                    }
                )
                _emit_trace_step(agent_trace)
            agent_trace.append(
                {
                    "kind": "assistant_note",
                    "title": "Want to tweak anything?",
                    "message": "If you want, ask for quieter, smaller, more RGB, or a different GPU/CPU and I’ll re-balance the build.",
                }
            )
            _emit_trace_step(agent_trace)
            total = total_price_for_build(build)
            savings = round(total * 0.35, 2)
            payload: dict[str, Any] = {
                "success": True,
                "build": build,
                "total": total,
                "savings": savings,
                "analysis": analysis,
                "agent_trace": agent_trace,
                "parts_catalog_source": parts_catalog_source,
            }
            if os.environ.get("GESTALT_DEBUG"):
                payload["raw_llm_output"] = raw_output[:4000]
                payload["allocation_category"] = category
                payload["allocation_rules"] = rules_pct
                payload["allocation_usd"] = rules_usd
                payload["selected_ids"] = selected_ids
                payload["parsed_recommendation_raw"] = recommendation_result[:4000]
            out = json.dumps(payload, indent=2)
            print(out)
            _agent_trace_buffer.reset(trace_tok)
            if stream_tok is not None:
                _stream_queue.reset(stream_tok)
            return out

        errs = validation.get("errors") or []
        if isinstance(errs, list) and errs and isinstance(errs[0], dict):
            fix = errs[0].get("fix")
            if isinstance(fix, str) and fix.strip():
                error = fix.strip()
            else:
                error = "Validation failed; choose different compatible parts."
        else:
            error = "Validation failed; choose different compatible parts."

    fail: dict[str, Any] = {
        "success": False,
        "error": "Could not build compatible PC after 3 attempts",
        "agent_trace": agent_trace,
        "parts_catalog_source": parts_catalog_source,
    }
    out_fail = json.dumps(fail, indent=2)
    print(out_fail)
    _agent_trace_buffer.reset(trace_tok)
    if stream_tok is not None:
        _stream_queue.reset(stream_tok)
    return out_fail


def build_crew(topic: str = "parts compatibility") -> Crew:
    """Minimal two-task crew for LLM smoke tests (analysis + recommendation placeholders)."""
    a = analysis_agent()
    r = recommendation_agent()
    t1 = Task(
        description=f"Topic context: {topic}. Summarize as JSON placeholder.",
        expected_output="Short JSON string",
        agent=a,
    )
    t2 = Task(
        description="Using prior context, output OK.",
        expected_output="OK",
        agent=r,
        context=[t1],
    )
    return Crew(agents=[a, r], tasks=[t1, t2], process=Process.sequential, verbose=True)


def run_crew(topic: str = "parts compatibility") -> str:
    crew = build_crew(topic=topic)
    return str(crew.kickoff())


if __name__ == "__main__":
    run_build_assistant("I want a $1500 editing rig")
