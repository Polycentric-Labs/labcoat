# scripts/n2_extract_llm.py
"""labcoat N2 — LLM-tagged extraction: pure extraction_prompt / parse_extraction / ground_extraction +
injected-brain shell extract_llm. The pure functions are stdlib + deterministic (no network/key); the
brain is ONLY via the injected brain_fn (tests inject fakes; the live path injects nuclear._brain via
gaps_live.py --llm). Research tweaks A (context field for conditional contradictions) + D (span-
verification hallucination guard) baked in.
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import re


def extraction_prompt(title, abstract) -> str:
    """Deterministic extraction prompt -> strict-JSON {concepts, claims[{subject,polarity,value,context}]}. Pure.
    Asks ONLY for terms appearing verbatim in the text (anti-hallucination) + the CONDITION each claim holds under
    (tweak A/D from the research pass)."""
    return (
        "Extract the key scientific concepts and directional claims from this paper.\n"
        "Return STRICT JSON ONLY (no prose, no markdown), exactly:\n"
        '{"concepts": ["..."], "claims": [{"subject": "...", "polarity": "+" or "-", "value": "...", "context": "..."}]}\n'
        "Rules:\n"
        "- concepts: 5-12 SHORT noun-phrase concepts/methods/entities that appear VERBATIM in the title or abstract "
        "below (do NOT invent or paraphrase). Lowercase ok; NO sentence fragments; NO generic words ('method'/'results').\n"
        "- claims: ONLY a DIRECTIONAL finding (X improves/increases -> '+'; X reduces/degrades -> '-'). subject = the "
        "thing affected (must appear verbatim). value = the metric/target if stated else \"\". context = the CONDITION "
        "the finding holds under (population/dataset/dosage/setting/in-vitro-vs-in-vivo) if stated else \"\".\n"
        "- If no clear claim, return an empty claims list. Do NOT fabricate.\n\n"
        f"Title: {title}\nAbstract: {abstract}\n"
    )


def _first_json_object(text: str) -> str:
    """Extract the first {...} block from text (handles fenced code blocks and surrounding prose)."""
    # strip markdown fences first
    fenced = re.sub(r"^```[a-z]*\n?", "", text.strip(), flags=re.MULTILINE)
    fenced = re.sub(r"\n?```$", "", fenced.strip(), flags=re.MULTILINE)
    # find the first {...} span
    start = fenced.find("{")
    if start == -1:
        return ""
    depth = 0
    for i, ch in enumerate(fenced[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return fenced[start:i + 1]
    return ""


def parse_extraction(text) -> dict:
    """Parse the LLM's raw response into {concepts: list[str], claims: list[dict]}. Handles fenced JSON,
    prose-wrapped JSON, and malformed/partial output (fail-soft: bad claims dropped, garbage -> empty).
    Carries context/value when non-empty (tweak A). Case-dedupes concepts. Pure."""
    raw = _first_json_object(str(text or ""))
    if not raw:
        return {"concepts": [], "claims": []}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {"concepts": [], "claims": []}

    # --- concepts: dedupe case-insensitively, preserve first surface form ---
    concepts = []
    seen_lower = set()
    for c in (obj.get("concepts") or []):
        s = str(c).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        concepts.append(s)

    # --- claims: drop missing subject or bad polarity; carry value/context when non-empty ---
    claims = []
    for c in (obj.get("claims") or []):
        if not isinstance(c, dict):
            continue
        subj = str(c.get("subject") or "").strip()
        pol = str(c.get("polarity") or "").strip()
        if not subj or pol not in ("+", "-"):
            continue
        rec = {"subject": subj, "polarity": pol}
        val = str(c.get("value") or "").strip()
        if val:
            rec["value"] = val
        ctx = str(c.get("context") or "").strip()
        if ctx:
            rec["context"] = ctx
        claims.append(rec)

    return {"concepts": concepts, "claims": claims}


def ground_extraction(parsed, source_text) -> dict:
    """Span-verification hallucination guard (research tweak D): drop any concept or claim whose key term does NOT
    appear (case-insensitive substring) in source_text. The LLM-extraction research flagged this as a cheap, effective
    anti-fabrication guard (~15-25% hallucinated-relation rate without it). Pure.
    NOTE: matching is substring (not word-boundary) — intentional for multi-word scientific noun phrases; a 1-2 char
    concept could false-keep inside a longer word, but the prompt's verbatim + no-generic-words rule suppresses that.
    Only a claim's SUBJECT is span-verified, NOT its `context`: stripping a paraphrased context ("in mice" vs source
    "murine model") would merge claims back into the unconditioned bucket and re-introduce false contradictions
    (defeating tweak A), so an unverified context is left as-is — erring toward FEWER false contradictions, the safe
    direction for an advisory detector."""
    src = str(source_text or "").lower()
    concepts = [c for c in (parsed.get("concepts") or []) if str(c).strip() and str(c).strip().lower() in src]
    claims = [c for c in (parsed.get("claims") or [])
              if isinstance(c, dict) and str(c.get("subject") or "").strip().lower() in src and str(c.get("subject") or "").strip()]
    return {"concepts": concepts, "claims": claims}


def extract_llm(docs, *, brain_fn, max_concepts: int = 12) -> tuple:
    """Shell: per doc, call brain_fn(extraction_prompt(title, abstract)) -> parse_extraction ->
    ground_extraction(parsed, title + ' ' + abstract). Returns (concept_lists, all_claims) where
    concept_lists[i] is the grounded concept list for docs[i], and all_claims is the flat list of all
    grounded claims across all docs. Fail-soft: a bad LLM response for one doc contributes nothing."""
    concept_lists = []
    all_claims = []
    for doc in (docs or []):
        title = str(doc.get("title") or "").strip()
        abstract = str(doc.get("abstract") or "").strip()
        prompt = extraction_prompt(title, abstract)
        try:
            reply = brain_fn(prompt)
        except Exception:
            concept_lists.append([])
            continue
        parsed = parse_extraction(reply)
        grounded = ground_extraction(parsed, title + " " + abstract)
        capped = grounded["concepts"][:int(max_concepts)]
        concept_lists.append(capped)
        all_claims.extend(grounded["claims"])
    return concept_lists, all_claims
