# scripts/nuclear.py
"""Operator LIVE entrypoint for the §5.2 NUCLEAR autonomous multi-loop research engine — NOT unit-tested; the
`run` subcommand spends REAL money (Claude-orchestration brain + OpenRouter fleet). Mirrors smoke_host.py:
loads API keys in-process from ~/.secrets/*.env (NEVER printed), shows the two-line estimate FIRST, enforces
TOLERANCE (hard ceiling) + the R8 burn gate, and keeps runs tiny by default.

Per loop the async Agent-SDK brain drives the proven 6-phase method:
  decompose (brain) -> redact -> fleet fan-out (durable host.run_loop: record-before-call fsync + reservation)
  -> hard-skeptic primary-source VERIFY (brain w/ WebSearch/WebFetch) -> write each CONFIRMED claim_text to the
  ledger -> NOVELTY (CNY + persist seen-set/corpus + yield-collapse, WARN-only) -> PACING (live RateLimitEvent
  / ResultMessage -> pacing_decision) -> per-loop DECISION (continue / pause / stop + option menu) -> loop;
  synthesize over the confirmed corpus on stop.

ALL deciding logic is the unit-tested PURE core (nuclear_core / novelty_gate / novelty_store / spend / pacing /
orchestrator / audit). THIS module is the irreducible async SDK glue + the operator money gates; it is validated
by a tiny live smoke (final hardening), never by unit tests. TOLERANCE stays a hard ceiling; novelty is
WARN-only (never auto-stops -> pause-and-ping).

Usage:
  python scripts/nuclear.py estimate --question "is X novel?" [--models 4] [--max-loops 1]
  python scripts/nuclear.py run --question "is X novel?" --tolerance 5.00 [--max-loops 1]
                                 [--brain-model claude-opus-4-8] [--confirm "yes, burn it"]
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import argparse
import asyncio
import os
import pathlib
import sys
import datetime as _dt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import audit
import fleet
import redaction_gate
import spend
import pacing
import orchestrator
import novelty_gate
import value_axis
import memory_backend
import nuclear_core
import run_scope
import loop_evolution
import orchestrator_host as host
import claude_agent_sdk as sdk

# Cheap, commonly-available defaults for a tiny operator run; resolved against the LIVE catalogue at fire time.
_CHEAP = [
    {"id": "openai/gpt-4o-mini",               "in_price": 0.15, "out_price": 0.60},
    {"id": "google/gemini-2.0-flash-001",      "in_price": 0.10, "out_price": 0.40},
    {"id": "deepseek/deepseek-chat",           "in_price": 0.27, "out_price": 1.10},
    {"id": "meta-llama/llama-3.1-8b-instruct", "in_price": 0.02, "out_price": 0.05},
    {"id": "anthropic/claude-3.5-haiku",       "in_price": 0.80, "out_price": 4.00},
]
_FLEET_MAX_TOKENS = 2000       # raised from 512; gpt-4o-mini/deepseek were truncating at 512
_BRAIN_MODEL = "claude-opus-4-8"   # Opus-class brain (override with --brain-model; e.g. a haiku id for a cheap smoke)
_DEFAULT_BACKOFF_S = 60.0      # graceful-pause sleep when the rate-limit signal carries no Retry-After

# Configurable brain backends: preset -> (transport, default model). The 3 OpenRouter presets bill OpenRouter,
# never the Anthropic Console. --brain-model overrides the model; OR ids are resolved against the live catalogue
# at fire time (the operator passes a confirmed-live id for a real run). More backends are a future roadmap pass.
_BRAIN_PRESETS = {
    "sdk":              ("sdk",        "claude-opus-4-8"),
    "or-claude-strong": ("openrouter", "anthropic/claude-opus-4.1"),
    "or-claude-cheap":  ("openrouter", "anthropic/claude-sonnet-4.5"),
    "or-open":          ("openrouter", "deepseek/deepseek-chat-v3.1"),
}


def brain_spec(backend: str, model_override: str | None = None) -> dict:
    """Pure resolver: brain backend preset -> {transport, model}. --brain-model overrides the model; the
    transport stays the preset's. Unknown backend -> ValueError."""
    if backend not in _BRAIN_PRESETS:
        raise ValueError(f"unknown brain backend {backend!r}; choices: {sorted(_BRAIN_PRESETS)}")
    transport, default_model = _BRAIN_PRESETS[backend]
    return {"transport": transport, "model": (model_override or default_model)}


# ---------------------------------------------------------------------------- secret loaders (never printed)
def _load_env_key(var: str, filename: str) -> None:
    """Load a single KEY=value line from ~/.secrets/<filename> into os.environ[var], in-process, never printed
    (the secret-handling protocol: file -> env, no stdout, no context). No-op if already set in the env."""
    if os.environ.get(var):
        return
    p = pathlib.Path.home() / ".secrets" / filename
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(f"{var}="):
            os.environ[var] = s.split("=", 1)[1].strip().strip('"').strip("'")
            return
    raise SystemExit(f"{var}= line not found in ~/.secrets/{filename}")


def _scrub(s):
    """Remove any loaded API-key value from a string before it is printed (defense-in-depth: an SDK/transport
    error message must never echo a key). Returns the input unchanged when no key is set / present."""
    if not s:
        return s
    for var in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        val = os.environ.get(var)
        if val:
            s = s.replace(val, "<redacted>")
    return s


def _pick_models(n: int, fleet_max_tokens: int = _FLEET_MAX_TOKENS):
    """Pick up to n cheap models present in the live OpenRouter catalogue (free GET /models tests key+egress)."""
    available = fleet.list_models(os.environ["OPENROUTER_API_KEY"])
    specs = []
    for spec in _CHEAP:
        if spec["id"] in available:
            specs.append({**spec, "max_tokens": fleet_max_tokens, "reasoning": False})
        if len(specs) >= n:
            break
    if not specs:
        raise SystemExit("none of the cheap default models are in the live catalogue; edit _CHEAP")
    return specs, available


# ---------------------------------------------------------------------------- the async Agent-SDK brain
def _extract_rate_limit(msg):
    """Best-effort RateLimitInfo -> the plain dict pacing.rate_limit_signals consumes. Defensive: the exact
    RateLimitEvent shape is SDK-versioned, so getattr everything and convert resets_at -> seconds-from-now."""
    info = getattr(msg, "rate_limit", None) or getattr(msg, "info", None) or msg
    status = getattr(info, "status", None)
    util = getattr(info, "utilization", None)
    resets_at = getattr(info, "resets_at", None)
    retry = None
    if isinstance(resets_at, _dt.datetime):
        try:
            retry = max(0.0, (resets_at - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
        except Exception:   # noqa: BLE001 — tz-naive or odd value; leave retry None
            retry = None
    if status is None and util is None:
        return None
    return {"status": str(status) if status is not None else None,
            "utilization": util, "retry_after_s": retry}


def _status_int(api_err):
    """Coerce a ResultMessage.api_error_status into an HTTP int when possible (for quota_signals)."""
    try:
        return int(api_err)
    except (TypeError, ValueError):
        return getattr(api_err, "status_code", None) or getattr(api_err, "status", None)


async def _run_brain(prompt: str, *, model: str, max_budget_usd: float, max_turns: int,
                     allowed_tools=None, cwd=None) -> dict:
    """Run ONE Agent-SDK query to completion. Returns {text, cost_usd, api_error_status, is_error, rate_limit}.
    max_budget_usd caps THIS call's spend (defense-in-depth under TOLERANCE); the brain's text is parsed by the
    pure nuclear_core parsers (which accept a JSON string), so we do not depend on output_format."""
    opts = sdk.ClaudeAgentOptions(
        model=model, max_turns=max_turns, max_budget_usd=max_budget_usd,
        permission_mode="bypassPermissions", allowed_tools=list(allowed_tools or []), cwd=cwd)
    text_parts, cost_usd, api_error, is_error, rate_limit, err = [], 0.0, None, False, False, None
    try:
        async for msg in sdk.query(prompt=prompt, options=opts):
            if isinstance(msg, sdk.AssistantMessage):
                for block in (getattr(msg, "content", None) or []):
                    if isinstance(block, sdk.TextBlock):
                        text_parts.append(block.text)
            elif isinstance(msg, sdk.ResultMessage):
                cost_usd = getattr(msg, "total_cost_usd", None) or cost_usd
                api_error = getattr(msg, "api_error_status", None)
                is_error = bool(getattr(msg, "is_error", False))
                if not text_parts and getattr(msg, "result", None):
                    text_parts.append(str(msg.result))
            elif type(msg).__name__ == "RateLimitEvent":
                rate_limit = _extract_rate_limit(msg)
    except Exception as e:   # noqa: BLE001 — a brain-call failure (budget cap, API/transport error) must DEGRADE
        err, is_error = _scrub(str(e)), True   # scrub keys from the error; keep partial text; never crash here.
        if not cost_usd:               # pessimistic: a budget-cap/error may have spent up to the per-call cap
            cost_usd = max_budget_usd
    return {"text": "".join(text_parts), "cost_usd": cost_usd, "api_error_status": api_error,
            "is_error": is_error, "rate_limit": rate_limit, "error": err}


def _run_brain_openrouter(prompt: str, *, model: str, web: bool = False,
                          max_tokens: int = 4000, temperature: float = 0.4) -> dict:
    """OpenRouter brain transport (sync; the dispatcher wraps it in asyncio.to_thread). Returns the SAME dict
    shape as _run_brain. web=True appends the ':online' web plugin for primary-source grounding. Cost comes from
    OpenRouter's usage.cost (requested via usage.include). Degrades gracefully on any error (never crashes)."""
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"text": "", "cost_usd": 0.0, "api_error_status": None, "is_error": True,
                "rate_limit": None, "error": "OPENROUTER_API_KEY not set"}
    m = f"{model}:online" if web else model
    try:
        with httpx.Client() as c:
            r = c.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={"model": m, "messages": [{"role": "user", "content": prompt}],
                             "max_tokens": max_tokens, "temperature": temperature,
                             "usage": {"include": True}},
                       timeout=300.0)
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices") or []
        text = (choices[0].get("message", {}).get("content") or "") if choices else ""
        cost = float((data.get("usage") or {}).get("cost") or 0.0)
        return {"text": _scrub(text), "cost_usd": cost, "api_error_status": None, "is_error": False,
                "rate_limit": None, "error": None}
    except Exception as e:   # noqa: BLE001 — degrade like the SDK path; scrub keys from the error
        return {"text": "", "cost_usd": 0.0, "api_error_status": None, "is_error": True,
                "rate_limit": None, "error": _scrub(str(e))}


async def _brain(prompt: str, *, transport: str, model: str, max_budget_usd: float, max_turns: int,
                 web: bool = False, cwd=None) -> dict:
    """Transport-agnostic brain dispatch. sdk -> the Agent-SDK path (web -> WebSearch/WebFetch tools);
    openrouter -> the OpenRouter caller in a thread (web -> :online). Same result dict either way."""
    if transport == "sdk":
        return await _run_brain(prompt, model=model, max_budget_usd=max_budget_usd, max_turns=max_turns,
                                allowed_tools=(["WebSearch", "WebFetch"] if web else None), cwd=cwd)
    return await asyncio.to_thread(_run_brain_openrouter, prompt, model=model, web=web)


# ---------------------------------------------------------------------------- loop helpers
def _gather_findings(ledger_path: str, loop_id: str, *, max_chars: int = 6000) -> str:
    """Build the verify brain's input from THIS loop's complete fleet rows (sub-question + a capture snippet).
    Bounded so a big capture can't blow the prompt. Excludes the synthetic ::verify rows."""
    rows = [r for r in audit.read_ledger(ledger_path)
            if r.get("loop_id") == loop_id and r.get("completion_status") == "complete"
            and "::verify" not in str(r.get("query_id", ""))]
    parts = []
    for r in rows:
        snippet, cap = "", r.get("raw_capture_path")
        if cap and os.path.exists(cap):
            try:
                snippet = pathlib.Path(cap).read_text(encoding="utf-8")[:1200]
            except OSError:
                snippet = ""
        parts.append(f"- [{r.get('model')}] {r.get('sub_question')}: {snippet}")
    return ("\n".join(parts))[:max_chars] or "(no fleet findings captured this loop)"


def _surface(trigger, decision) -> None:
    """Print the operator surface a non-continue decision raises (the menu/ping TEXT; nuclear_core.menu_trigger
    names which). Novelty pause-and-pings; tolerance surfaces the scope-dial option menu — never auto-stops."""
    if trigger == "tolerance-menu":
        print("[nuclear] >>> OVER-TOLERANCE option menu: 1) raise tolerance  2) reduce variants  "
              "3) cheap wrap-up  4) free validate+save  5) other. (the SKILL.md scope-dial menu)")
    elif trigger == "novelty-ping":
        print("[nuclear] >>> NOVELTY YIELD-COLLAPSE — pausing and PINGING the operator (enforcing; pause-and-ping, never auto-stops).")
    elif trigger == "pacing-pause":
        print(f"[nuclear] >>> PACING PAUSE — resume after {decision.get('resume_after_s')}s (ramp on resume).")


async def run_loops(question: str, *, tolerance: float, max_loops: int, model_specs, available, brain_model: str,
                    brain_budget: float, workspace: str, client_terms, tau: float, floor: int, window: int,
                    max_subq: int, backend_kind: str = "sqlite", brain_backend: str = "or-claude-strong",
                    run_id: str | None = None, novelty_store_dir: str | None = None,
                    novelty_enforcing: bool = True) -> dict:
    """The autonomous multi-loop cycle (async). Returns the final spend breakdown. Stops on the composed
    per-loop decision (continue / pause / stop) — TOLERANCE is the hard ceiling; novelty is WARN-only.
    The Tier-3 value-axis (independent-source quality) is computed + REPORTED each loop but NEVER consumed by
    the decision (advisory until calibrated)."""
    audit_dir = pathlib.Path(workspace) / "_internal" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    nov_dir = pathlib.Path(novelty_store_dir) if novelty_store_dir else audit_dir
    nov_dir.mkdir(parents=True, exist_ok=True)
    led = str(audit_dir / "SESSION-LEDGER.jsonl")
    questions_p = str(audit_dir / "QUESTIONS-IDEAS.md")
    # the pluggable MemoryBackend seam: SQLite append-only bi-temporal+provenance default; flat-file fallback.
    # The NOVELTY STORE (memory.db / flat files) roots at nov_dir (separate from audit_dir when --novelty-store
    # is given, enabling a shared cross-invocation novelty store alongside a per-question ledger).
    backend = (memory_backend.SqliteBackend(str(nov_dir / "memory.db")) if backend_kind == "sqlite"
               else memory_backend.FileBackend(str(nov_dir)))
    clock = lambda: _dt.datetime.now(_dt.timezone.utc).isoformat()   # the live shell's REAL clock
    tracker = spend.Tracker()
    weighted_history = []   # in-process advisory weighted-CNY history for the degeneracy detector (this run)
    started_at = clock()                        # injected clock -> C1 run-id seed (no datetime.now() in pure modules)
    rid = run_id or run_scope.derive_run_id(question, started_at)
    prior_gaps = None                           # evolves across loops (gap-evolution)
    prior_questions = []                        # question archive (C1: per-run, not shared across invocations)
    _bspec = brain_spec(brain_backend, brain_model)
    bt, bm = _bspec["transport"], _bspec["model"]
    print(f"[nuclear] brain backend={brain_backend} transport={bt} model={bm}")
    # Redaction gate on the operator's QUESTION before it reaches the brain (the fleet path separately re-redacts
    # each derived sub-question in host.run_loop): a Class-A secret HALTS; Class-B terms -> typed placeholders.
    rq = redaction_gate.redact(question, client_terms=client_terms)
    if rq.get("hard_block"):
        print("[nuclear] QUESTION contains a Class-A secret — HALT + ROTATE; nothing was sent.")
        return tracker.breakdown()
    if rq.get("signal") and rq["signal"].get("recommend_stop"):
        print("[nuclear] QUESTION is heavily redacted (recommend_stop) — halting to avoid a gutted run; "
              "re-scope the question and retry.")
        return tracker.breakdown()
    question = rq["clean_text"]
    fleet_est = spend.estimate_openrouter(model_specs)
    # the per-loop tolerance gate must account for the next loop's TWO brain calls (decompose + verify),
    # capped at brain_budget each, not just the fleet cost (else the gate is systematically optimistic).
    next_loop_est = fleet_est + 2 * brain_budget
    per_query_est = fleet_est / max(1, len(model_specs))
    loop_id = "L0"

    for loop_i in range(1, max_loops + 1):
        loop_id = run_scope.make_loop_id(rid, loop_i)
        print(f"\n[nuclear] === loop {loop_i}/{max_loops} ({loop_id}) ===")

        # 1. DECOMPOSE (brain) — loop 0: original decomposition; loop N+1: gap-evolution (prior_gaps != None)
        dec = await _brain(nuclear_core.decompose_prompt(question, prior_gaps=prior_gaps, max_subquestions=max_subq),
                           transport=bt, model=bm, max_budget_usd=brain_budget, max_turns=4, web=False, cwd=workspace)
        tracker.add_claude_cost(dec["cost_usd"])
        if dec.get("error"):
            print(f"[nuclear] decompose brain degraded ({dec['error']}); continuing if any sub-questions parsed.")
        (audit_dir / f"brain-decompose-{loop_id}.txt").write_text(dec["text"] or "", encoding="utf-8")
        subqs = nuclear_core.parse_decomposition(dec["text"])
        if not subqs:
            print("[nuclear] decompose produced no sub-questions; stopping."); break
        # extend the question archive (C1: per-run, not shared across invocations)
        prior_questions.extend(sq["sub_question"] for sq in subqs if sq.get("sub_question"))
        print(f"[nuclear] decomposed into {len(subqs)} sub-questions (brain ${tracker.claude():.4f})")

        # 2+3. FLEET fan-out (host redacts each prompt + durable record-before-call + per-loop tolerance gate)
        work = host.expand_fleet_work(subqs, model_specs, loop_id=loop_id)   # loop-scope query_ids so evolved loops fan out
        fleet_out = host.run_loop(work, ledger_path=led, loop_id=loop_id, clock=clock,
                                  fleet_runner=fleet.run_fleet, redactor=redaction_gate.redact,
                                  available=available, tracker=tracker, est_per_query=per_query_est,
                                  tolerance=tolerance, next_loop_est=next_loop_est, client_terms=client_terms)
        if fleet_out["halted"]:
            print(f"[nuclear] fleet HALTED: {fleet_out['error'] or 'redaction hard-block'}. "
                  "If a Class-A secret triggered this, ROTATE it. Stopping."); break
        print(f"[nuclear] fleet drove {fleet_out['driven']} queries (spend ${tracker.breakdown()['total_usd']:.4f})")

        # 4. VERIFY (hard-skeptic, primary-source tools) -> CONFIRMED claim_text into the ledger
        ver = await _brain(nuclear_core.verify_prompt(_gather_findings(led, loop_id)), transport=bt, model=bm,
                           max_budget_usd=brain_budget, max_turns=12, web=True, cwd=workspace)
        tracker.add_claude_cost(ver["cost_usd"])
        if ver.get("error"):
            print(f"[nuclear] verify brain degraded ({ver['error']}); continuing with partial/empty verify.")
        (audit_dir / f"brain-verify-{loop_id}.txt").write_text(ver["text"] or "", encoding="utf-8")
        verifs = nuclear_core.parse_verifications(ver["text"])
        confirmed = nuclear_core.confirmed_to_ledger_records(
            verifications=verifs, loop_id=loop_id, query_id=f"{loop_id}::verify",
            sub_question=question, model=bm, clock=clock)
        for rec in confirmed:
            audit.append_ledger(led, rec)
        print(f"[nuclear] verify: {len(verifs)} claims judged, {len(confirmed)} confirmed -> ledger")

        # 4b. GAP STAGE (advisory loop-evolution) — surface contradictions/gaps from this loop's confirmed
        # findings, rank them (contradictions first), filter vs established corpus + prior questions, seed next loop.
        confirmed_now = novelty_gate.confirmed_claim_texts(
            [r for r in audit.read_ledger(led) if r.get("loop_id") == loop_id])
        gaps_raw = await _brain(nuclear_core.gap_prompt(confirmed_now, prior_questions), transport=bt, model=bm,
                                max_budget_usd=brain_budget, max_turns=4, web=False, cwd=workspace)
        tracker.add_claude_cost(gaps_raw["cost_usd"])
        if gaps_raw.get("error"):
            print(f"[nuclear] gap brain degraded ({gaps_raw['error']}); skipping gap-evolution this loop.")
        (audit_dir / f"brain-gaps-{loop_id}.txt").write_text(gaps_raw["text"] or "", encoding="utf-8")
        ranked = loop_evolution.rank_gaps(loop_evolution.parse_gaps(gaps_raw["text"]))
        established = list(confirmed_now) + backend.read_corpus()
        prior_gaps = loop_evolution.select_evolved_questions(ranked, prior_questions, established,
                                                             max_select=max_subq)
        print(f"[nuclear] gap-evolution: {len(prior_gaps)} next-loop seed(s) "
              f"(of {len(ranked)} surfaced); next loop targets the gaps")
        if ranked and not prior_gaps:
            print("[nuclear] gap-evolution: all gap candidates filtered (too similar to established/prior questions); "
                  "next loop reverts to the original decomposition")

        # 5. NOVELTY (CNY over CONFIRMED only; persist via the MemoryBackend; yield-collapse) — WARN-only
        seen = backend.read_seen_keys()
        corpus = backend.read_corpus()
        cny_res = novelty_gate.cny(confirmed, seen, corpus, tau=tau)
        ts = clock()
        backend.append_seen_keys(cny_res["new_keys"], tx_time=ts)
        backend.append_corpus(cny_res["new_corpus"], valid_time=ts, tx_time=ts)
        backend.append_cny(cny_res["cny"], tx_time=ts)
        collapse = novelty_gate.yield_collapse(backend.read_cny_history(), floor=floor, window=window)
        print(f"[nuclear] CNY={cny_res['cny']} new-confirmed; yield_collapse={collapse['collapsed']} "
              f"[{'ENFORCING: pause-and-ping' if novelty_enforcing else 'WARN-only'}]")

        # 5b. VALUE-AXIS (Tier-3) — ADVISORY ONLY: reported, NEVER consumed by the loop decision. Quality =
        # capped count of INDEPENDENT primary sources per confirmed finding; MAP-Elites-lite archive + provenance.
        confirmed_verifs = [v for v in verifs if v.get("verdict") == "confirmed"]
        weighted_history.append(value_axis.weighted_cny([value_axis.source_count(v) for v in confirmed_verifs]))
        wcollapse = value_axis.weighted_yield_collapse(weighted_history, floor=float(floor), window=window)
        cpvf = value_axis.cost_per_verified_finding(tracker.breakdown()["total_usd"], len(confirmed))
        for v in confirmed_verifs:
            q = value_axis.quality_weight(value_axis.source_count(v))
            cell = str(round(novelty_gate.novelty_distance(v["claim_text"], corpus), 1))   # coarse novelty cell
            backend.upsert_elite(cell, q, v["claim_text"], tx_time=ts)
            backend.record_provenance(v["claim_text"], v.get("sources", []), loop_id=loop_id,
                                      valid_time=ts, tx_time=ts, evidence=v.get("evidence", ""))
        print(f"[nuclear][advisory] weighted-CNY={weighted_history[-1]:.2f}; "
              f"weighted_collapse={wcollapse['collapsed']}; "
              f"cost/verified={('$%.4f' % cpvf) if cpvf is not None else 'n/a'}; "
              f"archive cells={len(backend.read_archive())} (value features ADVISORY — not in the decision)")

        # 6. PACING (live RateLimitEvent / ResultMessage.api_error -> signals -> decision)
        rl = ver["rate_limit"] or dec["rate_limit"]
        pacing_sig = pacing.rate_limit_signals(rl) if rl else {}
        api_err = ver["api_error_status"] or dec["api_error_status"]
        if api_err is not None:
            for k, v in spend.quota_signals(http_status=_status_int(api_err)).items():
                if v:
                    pacing_sig[k] = v
        pacing_dec = pacing.pacing_decision(pacing_sig)

        # 7. DECISION (budget + pacing + novelty). novelty_enforcing default True (calibrated 2026-06-23:
        # tau=0.30/floor=0/window=3 validated on 3 diverse curves) -> pause-and-ping on collapse (corrigible,
        # never auto-stops); --no-novelty-enforcing restores WARN-only.
        spent_reserved = tracker.breakdown()["total_with_reserved_usd"]
        breach_check = spend.would_next_loop_breach(spent_reserved, next_loop_est, tolerance)
        would_breach = not breach_check["within_tolerance"]
        st = nuclear_core.compose_loop_state(
            pacing_state=pacing_dec["state"], pacing_resume_after_s=pacing_dec["resume_after_s"],
            would_breach=would_breach, novelty_collapsed=collapse["collapsed"], novelty_enforcing=novelty_enforcing)
        decision = orchestrator.loop_decision(st)
        trigger = nuclear_core.menu_trigger(decision)
        print(f"[nuclear] decision={decision['action']} :: {decision['reason']}")
        if decision["action"] == "pause" and trigger == "pacing-pause":
            _surface(trigger, decision)                       # transient rate-limit -> auto-sleep + resume
            wait = decision.get("resume_after_s") or _DEFAULT_BACKOFF_S
            print(f"[nuclear] pacing pause: sleeping {wait:.0f}s, then resuming the loop "
                  "(pacing.ramp_after_idle is available for a future fleet-throttle ramp)...")
            await asyncio.sleep(wait)
            continue
        if decision["action"] != "continue":                 # stop (tolerance) OR novelty pause-and-ping -> halt for the operator
            _surface(trigger, decision)
            break

    # 8. SYNTHESIZE over the confirmed corpus + close the audit cycle.
    # TOLERANCE is a hard ceiling: skip the (paid) synth brain call if it would breach — the confirmed corpus
    # is already persisted, so the operator can raise tolerance + re-run to synthesize it.
    final_corpus = backend.read_corpus()
    if tracker.breakdown()["total_usd"] + brain_budget > tolerance:
        synth_text = ("(synthesis skipped: another brain call would breach TOLERANCE — the confirmed corpus is "
                      "persisted; raise --tolerance and re-run to synthesize it)")
        print("[nuclear] synth SKIPPED — would breach TOLERANCE; confirmed corpus persisted, synthesis deferred.")
    else:
        synth = await _brain(nuclear_core.synth_prompt(final_corpus), transport=bt, model=bm,
                             max_budget_usd=brain_budget, max_turns=6, web=False, cwd=workspace)
        tracker.add_claude_cost(synth["cost_usd"])
        if synth.get("error"):
            print(f"[nuclear] synth brain degraded ({synth['error']}).")
        synth_text = synth["text"] or "(no synthesis produced)"
        (audit_dir / f"brain-synth-{loop_id}.txt").write_text(synth_text, encoding="utf-8")
    research_dir = pathlib.Path(workspace) / "_internal" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / f"nuclear-synthesis-{loop_id}.md").write_text(synth_text, encoding="utf-8")
    (audit_dir / "RESURFACE.md").write_text(
        audit.generate_resurface(audit.read_ledger(led), audit.read_questions(questions_p), timestamp=clock()),
        encoding="utf-8")
    print(f"\n[nuclear] DONE. confirmed corpus={len(final_corpus)}; synthesis -> "
          f"{research_dir / ('nuclear-synthesis-' + loop_id + '.md')}")
    print(f"[nuclear] FINAL SPEND: {tracker.breakdown()}")
    return tracker.breakdown()


# ---------------------------------------------------------------------------- entrypoint
def _add_common(sp) -> None:
    sp.add_argument("--question", required=True)
    sp.add_argument("--models", type=int, default=4, help="fleet size (cheap defaults)")
    sp.add_argument("--max-loops", type=int, default=1)
    sp.add_argument("--brain-model", default=None,
                    help="override the selected brain backend's default model (else the preset default)")
    sp.add_argument("--max-subq", type=int, default=4)
    sp.add_argument("--fleet-max-tokens", type=int, default=_FLEET_MAX_TOKENS,
                    help="max_tokens per fleet model call (default 2000; reasoning models floor at 8000)")


def main() -> None:
    ap = argparse.ArgumentParser(description="labcoat §5.2 Nuclear autonomous multi-loop engine (operator).")
    sub = ap.add_subparsers(dest="mode")
    _add_common(sub.add_parser("estimate", help="FREE: show the two-line estimate; no paid call."))
    rp = sub.add_parser("run", help="PAID: fire a tiny bounded multi-loop run.")
    _add_common(rp)
    rp.add_argument("--tolerance", type=float, required=True, help="hard spend ceiling (USD)")
    rp.add_argument("--brain-budget", type=float, default=1.00,
                    help="max_budget_usd per brain call (decompose/verify/synth); TOLERANCE is the session ceiling")
    rp.add_argument("--confirm", default="", help='must equal "yes, burn it" when the estimate > the R8 threshold')
    rp.add_argument("--tau", type=float, default=0.3, help="novelty distance threshold (calibrated default)")
    rp.add_argument("--floor", type=int, default=0)
    rp.add_argument("--window", type=int, default=3)
    rp.add_argument("--novelty-enforcing", action=argparse.BooleanOptionalAction, default=True,
                    help="ENFORCING (default, calibrated 2026-06-23): pause-and-ping on novelty yield-collapse "
                         "(corrigible — never auto-stops). --no-novelty-enforcing restores WARN-only.")
    rp.add_argument("--client-terms", nargs="*", default=[])
    rp.add_argument("--workspace", default=".")
    rp.add_argument("--run-id", default=None,
                    help="run-scoped ledger prefix (C1); default derived from question+start time")
    rp.add_argument("--novelty-store", default=None,
                    help="path for the cross-loop novelty store (seen/corpus/cny); default = workspace audit dir")
    rp.add_argument("--backend", choices=["sqlite", "file"], default="sqlite",
                    help="MemoryBackend: sqlite (append-only bi-temporal+provenance, default) or file (zero-dep)")
    rp.add_argument("--brain-backend", choices=["sdk", "or-claude-strong", "or-claude-cheap", "or-open"],
                    default="or-claude-strong",
                    help="brain transport: sdk (Anthropic Console) or 3 OpenRouter presets (default or-claude-strong)")
    args = ap.parse_args()
    if not args.mode:
        ap.print_help(); return

    if getattr(args, "max_loops", 1) < 1:
        raise SystemExit("[nuclear] --max-loops must be >= 1")

    _load_env_key("OPENROUTER_API_KEY", "openrouter.env")
    specs, available = _pick_models(args.models, fleet_max_tokens=args.fleet_max_tokens)
    n_agents = args.max_loops * (3 + args.models)   # crude: ~3 brain calls + N fleet calls per loop
    est = spend.two_line_estimate(specs, n_agents=n_agents, is_loop_cycle=True)
    print(f"[nuclear] ESTIMATE (very-rough): OpenRouter ${est['openrouter_usd']} + Claude-orchestration "
          f"${est['claude_orchestration_usd']} = ${est['total_usd']} (confidence {est['confidence']}); "
          f"fleet={[s['id'] for s in specs]}; loops={args.max_loops}")

    if args.mode == "estimate":
        print("[nuclear] estimate-only; NO paid call. Re-run with `run --tolerance <usd>` to fire.")
        return

    # --- paid run: layered money gates ---
    if spend.requires_explicit_burn(est["total_usd"]):
        if args.confirm.strip().lower() != "yes, burn it":
            raise SystemExit(f"[nuclear] R8: estimate ${est['total_usd']} exceeds the burn threshold — "
                             'pass --confirm "yes, burn it" to proceed.')
    if est["total_usd"] > args.tolerance:
        print(f"[nuclear] NOTE: estimate ${est['total_usd']} exceeds your --tolerance ${args.tolerance}; "
              "the per-loop gate will stop early at the ceiling.")
    if args.brain_backend == "sdk":
        _load_env_key("ANTHROPIC_API_KEY", "anthropic.env")   # only the sdk backend uses the Anthropic Console key
    asyncio.run(run_loops(
        args.question, tolerance=args.tolerance, max_loops=args.max_loops, model_specs=specs,
        available=available, brain_model=args.brain_model, brain_budget=args.brain_budget,
        workspace=args.workspace, client_terms=list(args.client_terms), tau=args.tau, floor=args.floor,
        window=args.window, max_subq=args.max_subq, backend_kind=args.backend,
        brain_backend=args.brain_backend, run_id=args.run_id, novelty_store_dir=args.novelty_store,
        novelty_enforcing=args.novelty_enforcing))


if __name__ == "__main__":
    main()
