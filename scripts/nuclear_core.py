# scripts/nuclear_core.py
"""labcoat Tier-2 Nuclear — the PURE brain-output control core. Everything the async Agent-SDK shell
(scripts/nuclear.py) needs that is NOT the query() call itself: defensive parsers for the brain's structured
output, the confirmed-finding -> ledger-record construction, the per-loop decision-state composition, the
operator-surface trigger, and the (pure) brain prompt builders. No SDK/network/key/datetime.now() — the shell
injects the clock + makes the live calls. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import re
import audit

_MAX_SUBQUESTIONS = 50            # defensive cap so a runaway brain can't fan out unbounded
_VERDICTS = {"confirmed", "fabricated", "unverifiable"}


def _extract_json(s: str):
    """Pull a JSON value out of a brain text response that may be wrapped in markdown code fences or prose
    (real models do this despite a 'STRICT JSON only' instruction). Tries the raw string, then a fence-stripped
    string, then the outermost [...] / {...} substring embedded in prose. Returns None if all fail."""
    s = (s or "").strip()
    candidates = [s]
    if s.startswith("```"):
        body = re.sub(r"^```[A-Za-z0-9]*\s*", "", s)
        body = re.sub(r"\s*```$", "", body).strip()
        candidates.append(body)
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
    src = candidates[-1]
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        i, j = src.find(open_ch), src.rfind(close_ch)
        if 0 <= i < j:
            try:
                return json.loads(src[i:j + 1])
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _coerce(obj) -> list:
    """A brain structured_output may arrive as a JSON string (possibly fenced/prose-wrapped), a bare list, or
    an enveloped dict. Return a list of item dicts (defensive): a string is JSON-extracted (fences/prose
    tolerated); a dict with a known list key is unwrapped; a bare list is returned as-is; anything else -> []."""
    if isinstance(obj, str):
        obj = _extract_json(obj)
        if obj is None:
            return []
    if isinstance(obj, dict):
        for key in ("sub_questions", "subquestions", "items", "verifications", "findings", "results"):
            if isinstance(obj.get(key), list):
                return obj[key]
        return []
    if isinstance(obj, list):
        return obj
    return []


def parse_decomposition(obj) -> list:
    """Normalize the decompose brain's structured output into [{id, sub_question, prompt}]. Assigns stable ids
    sq1..sqN when absent; prompt falls back to the sub_question; drops entries with no text; caps at
    _MAX_SUBQUESTIONS."""
    out = []
    for item in _coerce(obj):
        if not isinstance(item, dict):
            continue
        sub_q = str(item.get("sub_question") or item.get("question") or "").strip()
        prompt = str(item.get("prompt") or sub_q).strip()
        if not sub_q and not prompt:
            continue
        sub_q = sub_q or prompt
        out.append({"id": str(item.get("id") or f"sq{len(out) + 1}"), "sub_question": sub_q, "prompt": prompt})
        if len(out) >= _MAX_SUBQUESTIONS:
            break
    return out


def parse_verifications(obj) -> list:
    """Normalize the verify brain's output into [{claim_text, verdict, evidence}]. verdict in
    {confirmed, fabricated, unverifiable}; an unknown/missing verdict -> 'unverifiable' (the fail-safe, so a
    malformed row can never become confirmed). Drops entries with empty claim_text."""
    out = []
    for item in _coerce(obj):
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim_text") or item.get("claim") or "").strip()
        if not claim:
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in _VERDICTS:
            verdict = "unverifiable"
        raw_sources = item.get("sources")
        sources = ([str(s).strip() for s in raw_sources if str(s).strip()]
                   if isinstance(raw_sources, (list, tuple)) else [])
        out.append({"claim_text": claim, "verdict": verdict,
                    "evidence": str(item.get("evidence") or "").strip(), "sources": sources})
    return out


def confirmed_to_ledger_records(*, verifications, loop_id, query_id, sub_question, model, clock) -> list:
    """Build append-ready ledger records for the CONFIRMED findings only (verdict=='confirmed'), each with
    completion_status='complete' + validation_verdict='confirmed' + the claim_text (the honesty invariant
    holds — confirmed requires complete, enforced by audit.make_ledger_record). clock is an injected
    () -> iso_str. The caller appends them (audit.append_ledger). This IS '§5.2 writes each confirmed
    finding's claim_text into the ledger' — construction here, the append is the shell's."""
    out = []
    for v in (verifications or []):
        if not isinstance(v, dict) or v.get("verdict") != "confirmed":
            continue
        claim = str(v.get("claim_text") or "").strip()
        if not claim:                       # defense-in-depth: never emit an empty confirmed finding
            continue
        out.append(audit.make_ledger_record(
            timestamp=clock(), loop_id=loop_id, query_id=query_id, sub_question=sub_question,
            model=model, redaction_applied=True, raw_capture_path=None,
            completion_status="complete", validation_verdict="confirmed",
            claim_text=claim))
    return out


def compose_loop_state(*, pacing_state="proceed", pacing_resume_after_s=None, would_breach=False,
                       novelty_collapsed=False, novelty_enforcing=False) -> dict:
    """Assemble the exact dict orchestrator.loop_decision consumes — the single place the four control signals
    (pacing / budget / novelty-collapse / novelty-enforcing) compose. Defaults are the safe 'continue' path;
    the three flags are coerced to bool."""
    return {"pacing_state": pacing_state, "pacing_resume_after_s": pacing_resume_after_s,
            "would_breach": bool(would_breach), "novelty_collapsed": bool(novelty_collapsed),
            "novelty_enforcing": bool(novelty_enforcing)}


def menu_trigger(decision: dict) -> "str | None":
    """Map a loop_decision result to the operator surface the shell must raise (the menu/ping TEXT stays
    SKILL.md prose). stop -> 'tolerance-menu'; a novelty pause -> 'novelty-ping'; any other pause ->
    'pacing-pause'; continue / unknown -> None."""
    decision = decision or {}
    action = decision.get("action")
    reason = str(decision.get("reason") or "").lower()
    if action == "stop":
        return "tolerance-menu"
    if action == "pause":
        return "novelty-ping" if "novelty" in reason else "pacing-pause"
    return None


def decompose_prompt(question: str, *, prior_gaps=None, max_subquestions: int = 6) -> str:
    """Pure builder: the decompose brain prompt. With no prior_gaps (loop 0) -> the original non-overlapping
    decomposition. With prior_gaps (a ranked list of {kind,text} from loop_evolution) -> EVOLVE: generate the
    next sub-questions that TARGET the gaps, contradictions first, without re-asking what is already confirmed."""
    if prior_gaps:
        lines = "\n".join(f"- [{str(g.get('kind') or 'gap')}] {str(g.get('text') or '').strip()}"
                          for g in prior_gaps if str(g.get('text') or '').strip())
        return (
            "You are the EVOLUTION stage of a rigorous research engine. The investigation below has run prior "
            "loops; here are the open GAPS and CONTRADICTIONS it surfaced, already ranked (contradictions first). "
            f"Generate at most {max_subquestions} NON-OVERLAPPING sub-questions that TARGET these gaps to advance "
            "the investigation. Prioritise the contradictions: for a contradiction, design a sub-question that "
            "INVESTIGATES it — do NOT explain it away or assume the expected outcome. Do NOT re-ask anything "
            "already confirmed.\n\n"
            f"ORIGINAL QUESTION (context): {question}\n\n"
            f"OPEN GAPS / CONTRADICTIONS (ranked):\n{lines}\n\n"
            "Return STRICT JSON only: a list of objects, each "
            "{\"id\": \"sq1\", \"sub_question\": \"...\", \"prompt\": \"a self-contained research prompt\"}. "
            "No prose.")
    return (
        "You are the decomposition stage of a rigorous research engine. Break the QUESTION into at most "
        f"{max_subquestions} NON-OVERLAPPING sub-questions, each independently investigable.\n\n"
        f"QUESTION: {question}\n\n"
        "Return STRICT JSON only: a list of objects, each "
        "{\"id\": \"sq1\", \"sub_question\": \"...\", \"prompt\": \"a self-contained research prompt\"}. "
        "No prose.")


def gap_prompt(confirmed_texts, prior_questions) -> str:
    """Pure builder: the GAP stage prompt. After verify, ask the brain to surface what is MISSING / under-explored
    / CONTRADICTORY from the confirmed findings (and a follow-up on a winning hypothesis), as strict JSON, so
    loop_evolution can rank them and seed the next loop. The contradiction signal is the highest-value trigger."""
    findings = "\n".join(f"- {t}" for t in (confirmed_texts or [])) or "(no confirmed findings yet)"
    asked = "\n".join(f"- {q}" for q in (prior_questions or [])) or "(none)"
    return (
        "You are the GAP-IDENTIFICATION stage. Given the CONFIRMED findings and the questions ALREADY ASKED, "
        "name what is still MISSING, under-explored, or CONTRADICTORY — the whitespace that should drive the next "
        "loop. Surface, in priority order: (1) CONTRADICTIONS (a confirmed claim that conflicts with another or "
        "with a prior finding), (2) follow-ups on a winning/strong hypothesis, (3) author/source-stated future "
        "work, (4) plain coverage gaps. Do NOT repeat an already-asked question.\n\n"
        f"CONFIRMED FINDINGS:\n{findings}\n\nALREADY ASKED:\n{asked}\n\n"
        "Return STRICT JSON only: a list of objects, each {\"kind\": "
        "\"contradiction|won_followup|future_work|gap\", \"text\": \"the gap as an investigable statement\", "
        "\"seed_evidence\": \"the finding(s) this gap comes from\"}. No prose.")


def verify_prompt(findings: str) -> str:
    """Pure builder: the hard-skeptic Phase-3/4 verify brain prompt. Every proper noun is a claim to DISPROVE
    against a primary source; an unconfirmed claim is 'unverifiable', never 'confirmed'."""
    return (
        "You are the hard-skeptic primary-source verification stage. For EACH claim below, try to DISPROVE it "
        "against primary sources (official repos, arXiv / Semantic Scholar, NVD / vendor advisories, primary "
        "docs). Treat every proper noun (CVE/advisory id, arXiv id, repo, version, citation, tool name, "
        "statistic) as a claim to verify, never a fact. A claim you cannot confirm against a primary source is "
        "'unverifiable', NEVER 'confirmed'.\n\n"
        f"CLAIMS / FLEET FINDINGS:\n{findings}\n\n"
        "Return STRICT JSON only: a list of objects, each {\"claim_text\": \"the canonical verified claim\", "
        "\"verdict\": \"confirmed|fabricated|unverifiable\", \"evidence\": \"primary-source URL/SHA/id\", "
        "\"sources\": [\"primary-source URL or id\", ...]}. "
        "No prose.")


def synth_prompt(confirmed_texts) -> str:
    """Pure builder: the synthesis brain prompt over ONLY the confirmed findings. Bounded claims; no overclaim."""
    body = "\n".join(f"- {t}" for t in confirmed_texts) or "(no confirmed findings this run)"
    return (
        "You are the synthesis stage. Using ONLY the CONFIRMED findings below, write a ruthless, honestly-"
        "bounded synthesis: what is now known, what to do with it, and an explicit SKIP/KILL list. Do not "
        "introduce any claim not present below; do not overclaim beyond what the findings support.\n\n"
        f"CONFIRMED FINDINGS:\n{body}\n")
