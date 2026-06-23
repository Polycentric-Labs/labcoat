# scripts/gap_channels.py
"""labcoat N2 — gap / whitespace channels: the PURE multi-channel detector that enriches Unit A's single LLM gap
stage. Channels (research synthesis Q-N2): structural ABC-whitespace (Swanson undiscovered-public-knowledge),
future-work mining, structural contradiction, + a RECONCILIATION layer that tags each candidate's evidentiary
status (the integration the field says is unsolved -> N2's differentiator). Then two-axis (novelty + utility)
scoring (never a single LLM-judge self-score). Output converts to loop_evolution's gap-record shape.
HONEST LIMITS: an absent graph edge is a gap ONLY if the two concepts are textually/semantically related (so
abc_whitespace fuses with an injected relatedness_fn — naive ABC has high false positives, synthesis finding 3);
no benchmark exists, so N2 emits scored HYPOTHESES, not validated gaps (the loop is the prospective validation).
The known-but-unaddressed upgrade requires BOTH concepts in a SINGLE future-work sentence (word-boundary match)
— still a heuristic; semantic matching is future work.
The concept-graph / claim extraction that BUILDS the inputs from a corpus is the deferred adapter seam. Inputs
injected; pure stdlib; no network/key/datetime.now(). ADVISORY. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import re

_MAX = 50


def abc_whitespace(edges, *, relatedness_fn=None, min_relatedness: float = 0.0, max_candidates: int = _MAX) -> list:
    """Swanson ABC open-discovery: over an undirected concept CO-OCCURRENCE graph, find concept pairs (A,C) that
    are 2-hop connected through a shared bridge B (A-B and B-C edges) but have ZERO direct A-C edge -> a
    structurally identifiable whitespace. Fuses with text: if relatedness_fn is given, keep (A,C) only when
    relatedness_fn(A,C) >= min_relatedness (drops spurious absent edges). Returns [{a, c, bridges}], a<=c."""
    adj = {}
    for e in (edges or []):
        if not (isinstance(e, (list, tuple)) and len(e) >= 2):
            continue
        a, b = str(e[0]).strip(), str(e[1]).strip()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    out, nodes = [], sorted(adj)
    for i, a in enumerate(nodes):
        for c in nodes[i + 1:]:
            if c in adj.get(a, set()):                       # direct co-mention -> not a gap
                continue
            bridges = adj.get(a, set()) & adj.get(c, set())  # shared neighbours B
            if not bridges:
                continue
            if relatedness_fn is not None and float(relatedness_fn(a, c)) < float(min_relatedness):
                continue
            out.append({"a": a, "c": c, "bridges": sorted(bridges)})
            if len(out) >= int(max_candidates):
                return out
    return out


_FW_PATTERNS = [r"future work", r"in (?:the )?future", r"we (?:will|plan to|leave)\b",
                r"remains? (?:an? )?open", r"could be extended", r"left (?:for|to) future",
                r"promising direction", r"open (?:question|problem)"]


def mine_future_work(text) -> list:
    """Extract author-stated FUTURE-WORK sentences (high recall, tagged LOW-TRUST downstream — they are vague,
    self-promotional, and often already addressed by concurrent work). Pure sentence split + pattern match."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", str(text or "")):
        sl = s.lower()
        if any(re.search(p, sl) for p in _FW_PATTERNS):
            t = s.strip()
            if t:
                out.append(t)
    return out


def find_contradictions(claims) -> list:
    """Structural EXPLICIT contradiction channel: group claim records by subject/key; flag a subject whose claims
    disagree — opposing `polarity` OR distinct `value`s. (Subtle/conditional scientific contradictions need the
    brain seam; this is the cheap structural floor where LLMs are most reliable.) Returns [{subject, claims}]."""
    by_subject = {}
    for c in (claims or []):
        if not isinstance(c, dict):
            continue
        subj = str(c.get("subject") or c.get("key") or "").strip().lower()
        if not subj:
            continue
        by_subject.setdefault(subj, []).append(c)
    out = []
    for subj, items in by_subject.items():
        polarities = {str(c.get("polarity") or "").strip() for c in items if str(c.get("polarity") or "").strip()}
        values = {str(c.get("value") or "").strip().lower() for c in items if str(c.get("value") or "").strip()}
        if len(polarities) > 1 or len(values) > 1:
            out.append({"subject": subj, "claims": items})
    return out


def _pair_key(a, c) -> str:
    return " | ".join(sorted([str(a).strip().lower(), str(c).strip().lower()]))


def reconcile_channels(*, structural=None, future_work=None, contradictions=None, addressed=None) -> list:
    """The RECONCILIATION layer: merge the channels into unified candidate-gap records, tagging each with an
    evidentiary status — 'whitespace' (structural only), 'known-but-unaddressed' (structural AND future-work),
    'speculative' (future-work only), 'contradiction' (contradiction channel). Drops any structural gap whose
    pair-key is in `addressed` (already explored/solved). Pure; provenance preserved per record."""
    _addressed = set(addressed or ())
    fw = [str(s).strip() for s in (future_work or []) if str(s).strip()]
    fw_lower = [s.lower() for s in fw]
    matched_fw = set()                      # indices of fw sentences that corroborated a structural gap
    out = []
    for g in (structural or []):
        a, c = g.get("a"), g.get("c")
        key = _pair_key(a, c)
        if key in _addressed:
            continue
        a_l, c_l = str(a or "").strip().lower(), str(c or "").strip().lower()
        in_fw, hit_idx = False, None
        if a_l and c_l:
            ra, rc = r"\b" + re.escape(a_l) + r"\b", r"\b" + re.escape(c_l) + r"\b"
            for idx, s in enumerate(fw_lower):
                if re.search(ra, s) and re.search(rc, s):
                    in_fw, hit_idx = True, idx
                    break
        status = "known-but-unaddressed" if in_fw else "whitespace"
        if in_fw:
            matched_fw.add(hit_idx)
        out.append({"text": f"the unexplored link between {a} and {c} (bridged by {', '.join(g.get('bridges') or [])})",
                    "gap_type": "structural", "evidentiary_status": status,
                    "channels": ["structural"] + (["future_work"] if in_fw else []),
                    "provenance": {"bridges": g.get("bridges"), "pair_key": key}})
    # future-work statements not matched to a structural pair -> speculative
    for idx, s in enumerate(fw):
        if idx in matched_fw:
            continue
        out.append({"text": s, "gap_type": "future_work", "evidentiary_status": "speculative",
                    "channels": ["future_work"], "provenance": {}})
    for con in (contradictions or []):
        out.append({"text": f"contradiction on: {con.get('subject')}", "gap_type": "contradiction",
                    "evidentiary_status": "contradiction", "channels": ["contradiction"],
                    "provenance": {"claims": con.get("claims")}})
    return out


def score_gap(gap, *, novelty: float, utility: float) -> dict:
    """Two-axis scoring: attach novelty_score AND utility_score (clamped [0,1]) to the gap record — N2 must NOT
    collapse to a single novelty scalar (the loop optimizes the joint frontier). `priority` = novelty*utility is
    an ADVISORY rank hint only (multiplicative, like N3 creativity: novel-but-useless or trivial -> low). Pure."""
    n = min(1.0, max(0.0, float(novelty)))
    u = min(1.0, max(0.0, float(utility)))
    out = dict(gap or {})
    out.update({"novelty_score": n, "utility_score": u, "priority": n * u})
    return out


_STATUS_TO_KIND = {"contradiction": "contradiction", "known-but-unaddressed": "future_work",
                   "speculative": "future_work", "whitespace": "gap"}


def to_next_question_candidates(reconciled_gaps) -> list:
    """Convert reconciled N2 gaps into loop_evolution's gap-record shape {kind, text, seed_evidence} so the
    multi-channel output feeds the existing rank_gaps / select_evolved_questions (contradictions rank first there).
    The evidentiary_status maps to the loop_evolution kind; provenance becomes seed_evidence. Pure.
    The 4 loop_evolution kinds are a COARSE first-pass bucket; the precise evidentiary tier (whitespace /
    known-but-unaddressed / speculative / contradiction) is carried in seed_evidence so the loop brain can
    re-rank — the kind projection is intentionally lossy."""
    out = []
    for g in (reconciled_gaps or []):
        text = str(g.get("text") or "").strip()
        if not text:
            continue
        status = str(g.get("evidentiary_status") or "")
        kind = _STATUS_TO_KIND.get(status, "gap")
        prov = g.get("provenance") or ""
        seed = (f"[{status}] {prov}").strip()
        out.append({"kind": kind, "text": text, "seed_evidence": seed})
    return out
