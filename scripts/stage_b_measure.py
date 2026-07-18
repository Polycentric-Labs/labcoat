# scripts/stage_b_measure.py
"""Operator LIVE entrypoint for N3 Stage-B v3 (dual-leg) — the powered, dogfood-hardened machinery measurement. NOT
unit-tested; `run` spends OpenRouter $ (cheap arms + dual prior-art leg + a soundness panel). Mirrors combine_live/
stage_a gates (estimate-first, tolerance ceiling, keys in-process from ~/.secrets, never printed).

Pipeline per pair: arm i (raw-weak) + arm i* (raw-weak -> the engine's IDENTICAL novelty/judge/run_round selection,
combine_live proposal_mode='raw' ground=False) + arm ii (engine structure-mapping, ground=False) + arm iii (raw-STRONG).
Then: blind on ORIGINAL text -> DUAL prior-art leg (Leg A = sonar-pro web; Leg B = deterministic SPECTER2-kNN over the
frozen OpenAlex index) OR-kill (survive iff NEITHER leg finds resolved+confirmed anticipating prior art) -> 2-of-3
soundness panel on survivors + controls -> cluster-robust scoring (CMH + cluster-bootstrap CI + ICC) + control verdict
(binomial VOID + soundness-panel validity) -> the pre-registered CONFIRM/DIRECTIONAL/KILL/VOID/UNTRUSTED report.

PRIMARY contrast = sound_distant_rate delta (arm ii - arm i*). Ceiling: engine-attributable + prior-art-distant +
advisory-sound under protocol P, NOT human-verified non-obvious. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import argparse, asyncio, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nuclear, combinatorial, combine_live, stage_a, stage_b

_WS = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "build4-n3-stageB-design-validation"
_DEFAULT_SNAPSHOT = str(pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-openalex-snapshot")
_DEFAULT_STRONG = "anthropic/claude-opus-4.7"
_DEFAULT_ADJUDICATORS = ["perplexity/sonar-pro"]                           # v3: single sonar (Leg A); Leg B = kNN
_DEFAULT_SOUNDNESS = ["anthropic/claude-opus-4.7", "google/gemini-2.5-pro", "x-ai/grok-4.3"]  # != cheap generator family


_sem = None   # asyncio.Semaphore set in run_stage_b (created inside the event loop) — bounds OpenRouter concurrency so a
              # large run (~thousands of calls) does not flood the API into rate-limit errors that would corrupt the
              # measurement (a 429 -> empty text -> conservative default would bias survival).


async def _brain(prompt, model, *, web, brain_budget):
    async def _call():
        return await nuclear._brain(prompt, transport="openrouter", model=model, max_budget_usd=brain_budget,
                                    max_turns=1, web=web)
    if _sem is None:
        return await _call()
    async with _sem:
        return await _call()


async def _raw_arm(pair, model_id, arm_tag, *, n, brain_budget, web=False):
    """A raw one-line proposer arm (i = weak model, iii = strong model). Unfiltered: every parsed combo is measured."""
    a, b = pair
    res = await _brain(stage_a.raw_propose_prompt(a, b, n=n), model_id, web=web, brain_budget=brain_budget)
    combos = combinatorial.parse_combinations(res.get("text") or "")
    for c in combos:
        c["arm"], c["pair"], c["control"] = arm_tag, f"{a}:{b}", None
    return combos, float(res.get("cost_usd") or 0.0)


def _elites_from(out, pair, arm_tag):
    """The archive elites of a combine_live run (arm ii engine / arm i* matched-raw), tagged."""
    cands = []
    for e in combinatorial.elites(out.get("archive") or {}):
        e = dict(e)
        e["arm"], e["pair"], e["control"] = arm_tag, f"{pair[0]}:{pair[1]}", None
        cands.append(e)
    return cands


def _resolve_id(idstr):
    """Free-API resolve a DOI/arXiv id -> a record dict (OpenAlex work or Crossref message) for stage_b.parse_resolution.
    Network shell (best-effort); any failure -> {} (unresolved -> conservative, does NOT count as prior art)."""
    import httpx, os
    s = str(idstr or "").strip()
    if not s:
        return {}
    # Contact for the OpenAlex/Crossref polite pool, from $NCBI_CONTACT_EMAIL (the one contact var this repo reads).
    # OMIT-when-absent, NOT fail-closed: unlike NCBI E-utilities (see pubmed_adapter._contact_email), a mailto here is
    # OPTIONAL politeness — anonymous callers are served, just from the slower pool. Hard-failing this best-effort
    # resolver on a missing optional hint would turn every id into {} = "unresolved" = "no prior art found", silently
    # biasing the measurement. Never substitute a placeholder address; send none rather than a fake or someone else's.
    _contact = (os.environ.get("NCBI_CONTACT_EMAIL") or "").strip()
    headers = {"User-Agent": f"labcoat-stageB (mailto:{_contact})" if _contact else "labcoat-stageB"}
    try:
        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as c:
            if s.startswith("https://openalex.org/") or (s[:1] in ("W", "w") and s[1:2].isdigit()):
                wid = s.rsplit("/", 1)[-1]
                r = c.get(f"https://api.openalex.org/works/{wid}")
                return r.json() if r.status_code == 200 else {}
            if s.lower().startswith("10."):                       # DOI
                r = c.get(f"https://api.openalex.org/works/https://doi.org/{s}")
                if r.status_code == 200:
                    return r.json()
                r = c.get(f"https://api.crossref.org/works/{s}")
                if r.status_code == 200:
                    return (r.json() or {}).get("message") or {}
                return {}
            # arXiv id (e.g. 2409.04109): OpenAlex indexes arXiv works under the 10.48550 DOI
            r = c.get(f"https://api.openalex.org/works/https://doi.org/10.48550/arxiv.{s}")
            if r.status_code == 200:
                return r.json()
            return {}
    except Exception:
        return {}


_EMBEDDER = None
_INDEX = None


def _load_knn(snapshot_path, embedder_name):
    """Load the SPECTER2 embedder + faiss snapshot ONCE (fail-CLOSED). The v3 dual leg is mandatory — abort with an
    install hint rather than silently fall back to single-sonar (which would re-run the dogfood-killed design)."""
    global _EMBEDDER, _INDEX
    if _INDEX is not None:
        return
    import n1_embedder, n1_index
    if not (n1_embedder.n1_embedder_available() and n1_index.n1_index_available()):
        raise SystemExit("[stage_b] the v3 kNN prior-art leg requires faiss + the SPECTER2 embedder: "
                         "pip install -r requirements-n1.txt  (no single-sonar fallback by design).")
    _EMBEDDER = n1_embedder.load_embedder(embedder_name)
    _INDEX = n1_index.load_snapshot(snapshot_path, active_fingerprint=_EMBEDDER.fingerprint())


async def _knn_leg(claim, mech, confirm_model, *, knn_k, sim_threshold, date_cutoff, brain_budget):
    """Leg B: deterministic SPECTER2-kNN over the frozen OpenAlex index -> resolve+confirm (nearest first, stop at the
    first anticipation). STYLE-ROBUST (semantic). Returns (relevance_shaped, confirm, cost)."""
    if _EMBEDDER is None or _INDEX is None:
        raise RuntimeError("_load_knn must run before _knn_leg")
    qvec = (await asyncio.to_thread(_EMBEDDER.embed, [claim], role="query"))[0]
    neighbors = await asyncio.to_thread(_INDEX.nearest_k, qvec, k=knn_k, date_cutoff=date_cutoff)
    kp = stage_b.knn_prior_art(neighbors, sim_threshold=sim_threshold)
    relevance, confirm, cost = {"has_prior_art": False, "nearest_id": ""}, {"anticipates": False}, 0.0
    for nb in kp["candidates"]:
        resolved = stage_b.parse_resolution(await asyncio.to_thread(_resolve_id, nb["id"]))
        if not resolved["resolved"]:
            continue
        cr = await _brain(stage_b.confirm_prompt(claim, mech, resolved["title"], resolved["abstract"]),
                          confirm_model, web=False, brain_budget=brain_budget)
        cost += float(cr.get("cost_usd") or 0.0)
        c = stage_b.parse_confirm(cr.get("text") or "")
        if c["anticipates"]:
            relevance, confirm = {"has_prior_art": True, "nearest_id": nb["id"]}, c
            break
    return relevance, confirm, cost


async def _adjudicate_one(item, adj_models, confirm_model, *, knn_k, sim_threshold, date_cutoff, brain_budget):
    """DUAL prior-art leg on ORIGINAL text. Leg A = sonar-pro (web, lexical/recency). Leg B = deterministic SPECTER2-kNN
    (semantic, style-robust). survive iff BOTH legs find no resolved-and-confirmed anticipating prior art (OR-kill).
    Returns {id, survived, per_leg:[A,B], leg_a, leg_b, cost}."""
    claim, mech = item["claim"], item.get("mechanism", "")
    cost = 0.0
    # Leg A: sonar (single web adjudicator)
    m = adj_models[0]
    web = not str(m).lower().startswith("perplexity/")     # sonar searches natively (web=False); others need :online
    r = await _brain(stage_a.relevance_prompt(claim, mech), m, web=web, brain_budget=brain_budget)
    cost += float(r.get("cost_usd") or 0.0)
    relA, confA = stage_a.parse_relevance(r.get("text") or ""), {"anticipates": False}
    if relA.get("has_prior_art") and relA.get("nearest_id"):
        resolved = stage_b.parse_resolution(await asyncio.to_thread(_resolve_id, relA["nearest_id"]))
        if resolved["resolved"]:
            cr = await _brain(stage_b.confirm_prompt(claim, mech, resolved["title"], resolved["abstract"]),
                              confirm_model, web=False, brain_budget=brain_budget)
            cost += float(cr.get("cost_usd") or 0.0)
            confA = stage_b.parse_confirm(cr.get("text") or "")
    legA = stage_b.objective_survives(relA, confA)
    # Leg B: kNN (deterministic, style-robust)
    relB, confB, cB = await _knn_leg(claim, mech, confirm_model, knn_k=knn_k, sim_threshold=sim_threshold,
                                     date_cutoff=date_cutoff, brain_budget=brain_budget)
    cost += cB
    legB = stage_b.objective_survives(relB, confB)
    return {"id": item["id"], "survived": stage_b.panel_survives([legA, legB]), "per_leg": [legA, legB],
            "leg_a": {"rel": relA, "confirm": confA}, "leg_b": {"rel": relB, "confirm": confB}, "cost": cost}


async def _soundness_one(item, sound_models, *, brain_budget):
    """2-of-3 different-family soundness panel. Returns {id, sound, votes, cost}."""
    votes, cost = [], 0.0
    for m in sound_models:
        r = await _brain(stage_b.soundness_prompt(item["claim"], item.get("mechanism", "")),
                         m, web=False, brain_budget=brain_budget)
        cost += float(r.get("cost_usd") or 0.0)
        votes.append(stage_b.parse_soundness(r.get("text") or ""))
    v = stage_b.soundness_panel_verdict(votes, threshold=2)
    return {"id": item["id"], "sound": v["sound"], "votes": votes, "cost": cost}


async def _soundness_v2_one(item, sound_models, *, brain_budget):
    """v2 constraint-checking panel for ONE item. Returns the panel verdict (SOUND/UNSOUND/EXCLUDE) + the winning
    unsound_kind (for the scope audit)."""
    votes, cost = [], 0.0
    for m in sound_models:
        r = await _brain(stage_b.soundness_prompt_v2(item["claim"], item.get("mechanism", "")),
                         m, web=False, brain_budget=brain_budget)
        cost += float(r.get("cost_usd") or 0.0)
        votes.append(stage_b.parse_soundness_v2(r.get("text") or ""))
    v = stage_b.soundness_panel_verdict_v2(votes)
    # the unsound_kind for the scope audit = the kind the valid-unsound votes converged on (named_law vs incoherent_mapping)
    kinds = [vt.get("unsound_kind") for vt in votes if stage_b._valid_unsound_v2(vt)]
    kind = "named_law" if kinds.count("named_law") >= kinds.count("incoherent_mapping") and kinds else (kinds[0] if kinds else "none")
    return {"id": item["id"], "sound_verdict": v["verdict"], "unsound_kind": kind, "votes": votes, "cost": cost}


# very-rough per-call $ priors (output-heavy ~1-2k tok): cheap fleet ~ $0.001, sonar-pro/web ~ $0.015, strong panel ~ $0.02
_C_CHEAP, _C_WEB, _C_STRONG = 0.001, 0.015, 0.02
# the v2 constraint-checking panel call (retrieve + decompose + mapping-table + stripped target) is ~2-3x the v4 holistic
# vote -> a separate, higher per-call prior so the soundness estimate-gate does not understate spend (per-call still
# hard-capped by brain_budget).
_C_STRONG_V2 = 0.05


def _staged_estimate(n_pairs, n_per_pair, pool_size, n_sound, *, distant_only=True, n_controls=40):
    """Realistic staged $ estimate for the v4 2x2. arms = raw_weak (1 cheap/pair) + eng_weak (cheap fleet) + eng_strong
    (1 opus propose + ~n_per_pair strong-judge/pair) + raw_strong (1 opus/pair). Soundness = 0 in distant-only mode."""
    approx_items = n_pairs * n_per_pair * 4 + n_controls       # 4 arms (raw_weak/eng_weak/eng_strong/raw_strong) + controls
    arms = n_pairs * (2 * _C_CHEAP                             # raw_weak call + eng_weak propose (cheap)
                      + n_per_pair * _C_CHEAP                  # eng_weak judge fan-out (cheap)
                      + _C_STRONG + n_per_pair * _C_STRONG     # eng_strong: opus propose + strong judge fan-out
                      + _C_STRONG)                             # raw_strong (opus, 1/pair)
    adjud = approx_items * (_C_WEB + 0.6 * _C_CHEAP + 1.0 * _C_CHEAP)   # dual leg: sonar + legA/legB confirms (kNN FREE)
    sound = 0.0 if distant_only else (0.5 * approx_items + n_controls) * n_sound * _C_STRONG
    total = arms + adjud + sound
    return total, {"arms": round(arms, 2), "adjudicate": round(adjud, 2), "soundness": round(sound, 2)}, approx_items


async def _finish(blinded, origin, adjud, *, off_distribution, cost_by_arm, spent, soundness_models, brain_budget,
                  seed, n_pairs, max_pairs, distant_only=True):
    """v4 2x2 distant-only scoring + report from completed adjudications. PRIMARY = distant(eng_strong - raw_strong),
    paired-by-pair. Soundness panel SKIPPED when distant_only (distant != sound)."""
    cost_by_arm = dict(cost_by_arm)
    surv_by_id = {a["id"]: a["survived"] for a in adjud}
    leg_a = [a["per_leg"][0] if len(a.get("per_leg") or []) > 0 else False for a in adjud]
    leg_b = [a["per_leg"][1] if len(a.get("per_leg") or []) > 1 else False for a in adjud]
    kappa = stage_b.cohens_kappa([1 if x else 0 for x in leg_a], [1 if x else 0 for x in leg_b])

    if distant_only:
        sound_runs = []
        sound_by_id = {}
        cost_by_arm["soundness"] = 0.0
    else:
        blinded_by_id = {b["id"]: b for b in blinded}
        sound_ids = {a["id"] for a in adjud if a["survived"]} | {bid for bid, o in origin.items() if o["control"]}
        sound_runs = await asyncio.gather(*[_soundness_one(blinded_by_id[i], soundness_models, brain_budget=brain_budget)
                                            for i in sorted(sound_ids)])
        cost_by_arm["soundness"] = sum(s["cost"] for s in sound_runs); spent += cost_by_arm["soundness"]
        sound_by_id = {s["id"]: s["sound"] for s in sound_runs}

    arms = {"raw_weak": [], "eng_weak": [], "eng_strong": [], "raw_strong": []}
    pair_cells = {}
    for bid, o in origin.items():
        if o["control"] is not None or o["arm"] is None:
            continue
        survived = surv_by_id.get(bid, False)
        genuine = stage_b.genuine_survivor(survived, {"sound": sound_by_id.get(bid, False)})
        if o["arm"] in arms:
            arms[o["arm"]].append({"survived": survived, "genuine": genuine})
        if o["arm"] in ("eng_strong", "raw_strong"):
            d = pair_cells.setdefault(o["pair"], {"eng_strong": {"survived": [], "genuine": []},
                                                  "raw_strong": {"survived": [], "genuine": []}})
            d[o["arm"]]["survived"].append(survived); d[o["arm"]]["genuine"].append(genuine)

    att = stage_b.attribution_2x2(arms)
    ctrl_results = [{"control": o["control"], "survived": surv_by_id.get(bid, False),
                     "sound": sound_by_id.get(bid, False)}
                    for bid, o in origin.items() if o["control"] is not None]
    cv = stage_b.control_verdict_b(ctrl_results)
    metric = "survived"   # distant-only: the primary metric is distant (objective survival)
    strata, pair_records, icc_outcomes = [], [], []
    for p, d in pair_cells.items():
        gt, gb = d["eng_strong"][metric], d["raw_strong"][metric]
        a, b = sum(gt), len(gt) - sum(gt)
        cc, dd = sum(gb), len(gb) - sum(gb)
        strata.append(((a, b), (cc, dd)))
        pair_records.append({"eng_strong": (sum(gt), len(gt)), "raw_strong": (sum(gb), len(gb))})
        if gt:
            icc_outcomes.append([1 if x else 0 for x in gt])
    cmh = stage_b.cochran_mantel_haenszel(strata)
    ci = stage_b.cluster_bootstrap_delta_ci(pair_records, seed=seed, treat_key="eng_strong", base_key="raw_strong")
    icc = stage_b.intraclass_correlation(icc_outcomes)
    report = stage_b.stage_b_report_2x2(att, cmh, ci, cv, off_distribution, kappa, cost_by_arm)
    report["primary_metric_basis"] = "distant"
    report["icc"] = icc
    report["sequential"] = stage_b.sequential_decision(ci, pairs_done=n_pairs, max_pairs=max_pairs)

    _WS.mkdir(parents=True, exist_ok=True)
    pathlib.Path(_WS, "stage_b_adjudications_v4.json").write_text(
        json.dumps({"blinded": blinded, "origin": origin, "adjudications": adjud,
                    "soundness": sound_runs, "report": report, "cost_by_arm": cost_by_arm, "spent_usd": spent},
                   indent=2, default=str),
        encoding="utf-8")
    return {"report": report, "spent_usd": spent}


async def run_calibrate_soundness(*, tolerance, soundness_models, brain_budget, concurrency=8):
    global _sem
    _sem = asyncio.Semaphore(max(1, int(concurrency)))
    controls = json.loads(pathlib.Path(_WS, "controls_b.json").read_text(encoding="utf-8"))
    items = []
    for cls in ("neg", "hard_neg", "fringe", "pos"):
        for i, c in enumerate(controls.get(cls, [])):
            # controls_b.json rows carry NO id (only the v4 blind_candidates path mints ids); assign a stable synthetic
            # one so _soundness_v2_one's return {id:...} and the by_id map below don't KeyError mid-run (after spending).
            items.append({**c, "control": cls, "id": c.get("id") or f"{cls}{i}"})
    proj = len(items) * len(soundness_models) * _C_STRONG_V2
    print(f"[stage_b] calibrate-soundness ESTIMATE ~${proj:.2f} for {len(items)} controls x {len(soundness_models)} judges.")
    if proj > tolerance:
        return {"controls": {"verdict": "ABORTED-TOLERANCE-TOO-LOW", "projected": round(proj, 2)}, "spent_usd": 0.0}
    runs = await asyncio.gather(*[_soundness_v2_one(it, soundness_models, brain_budget=brain_budget) for it in items])
    by_id = {it["id"]: it for it in items}
    cres = [{"control": by_id[r["id"]]["control"], "sound_verdict": r["sound_verdict"], "unsound_kind": r["unsound_kind"]}
            for r in runs]
    cv = stage_b.control_verdict_soundness_v2(cres)
    pathlib.Path(_WS, "soundness_v2_calibration.json").write_text(
        json.dumps({"control_verdict": cv, "runs": runs}, indent=2, default=str), encoding="utf-8")
    return {"controls": cv, "spent_usd": sum(r["cost"] for r in runs)}


async def run_soundness_1b(*, tolerance, soundness_models, brain_budget, seed=0, concurrency=8, dry_run=False):
    """Read the saved v4 28-pair adjudications; run the v2 panel on the distant-survivors + controls; score sound_distant
    (eng_strong - raw_strong) over the adjudicable subset + per-arm exclusion. NO arms / NO prior-art re-adjudication."""
    global _sem
    _sem = asyncio.Semaphore(max(1, int(concurrency)))
    src = pathlib.Path(_WS, "stage_b_adjudications_v4.json")
    if not src.exists():
        raise SystemExit(f"[stage_b] soundness-1b: no v4 record at {src} (run the v4 28-pair run first).")
    data = json.loads(src.read_text(encoding="utf-8"))
    blinded_by_id = {b["id"]: b for b in data["blinded"]}
    origin = data["origin"]
    surv_by_id = {a["id"]: a["survived"] for a in data["adjudications"]}
    # the v2 panel runs on distant-survivors (arms) UNION all controls
    panel_ids = [bid for bid in origin if (surv_by_id.get(bid) and origin[bid].get("arm")) or origin[bid].get("control")]
    if dry_run:
        from collections import Counter
        arm_counts = Counter(origin[bid]["arm"] for bid in origin
                             if surv_by_id.get(bid) and origin[bid].get("arm"))
        print(f"[stage_b] soundness-1b DRY-RUN: {len(panel_ids)} panel items "
              f"(distant survivors by arm: {dict(arm_counts)} + controls). No paid call.")
        return {"report": {"verdict": "DRY-RUN"}, "spent_usd": 0.0}
    proj = len(panel_ids) * len(soundness_models) * _C_STRONG_V2
    print(f"[stage_b] soundness-1b ESTIMATE ~${proj:.2f} for {len(panel_ids)} items x {len(soundness_models)} judges.")
    if proj > tolerance:
        return {"report": {"verdict": "ABORTED-TOLERANCE-TOO-LOW", "projected": round(proj, 2)}, "spent_usd": 0.0}
    runs = await asyncio.gather(*[_soundness_v2_one(blinded_by_id[i], soundness_models, brain_budget=brain_budget)
                                  for i in panel_ids])
    sv = {r["id"]: r for r in runs}
    # controls -> Phase-A-style validity recheck (the gate the report consults)
    cres = [{"control": origin[bid]["control"], "sound_verdict": sv[bid]["sound_verdict"], "unsound_kind": sv[bid]["unsound_kind"]}
            for bid in panel_ids if origin[bid].get("control")]
    cv = stage_b.control_verdict_soundness_v2(cres)
    # build arms + per-pair cells (eng_strong vs raw_strong) over adjudicable sound
    arms = {"raw_weak": [], "eng_weak": [], "eng_strong": [], "raw_strong": []}
    pair_cells = {}
    for bid, o in origin.items():
        if o.get("control") is not None or o.get("arm") not in arms:
            continue
        distant = bool(surv_by_id.get(bid))
        sstate = sv[bid]["sound_verdict"] if (distant and bid in sv) else None
        arms[o["arm"]].append({"distant": distant, "sound_state": sstate})
        if o["arm"] in ("eng_strong", "raw_strong") and distant and sstate in ("SOUND", "UNSOUND"):
            d = pair_cells.setdefault(o["pair"], {"eng_strong": [], "raw_strong": []})
            d[o["arm"]].append(1 if sstate == "SOUND" else 0)
    att = stage_b.attribution_2x2_sound(arms)
    strata, pair_records, icc = [], [], []
    for p, d in pair_cells.items():
        gt, gb = d["eng_strong"], d["raw_strong"]
        strata.append(((sum(gt), len(gt) - sum(gt)), (sum(gb), len(gb) - sum(gb))))
        pair_records.append({"eng_strong": (sum(gt), len(gt)), "raw_strong": (sum(gb), len(gb))})
        if gt:
            icc.append(gt)
    cmh = stage_b.cochran_mantel_haenszel(strata)
    ci = stage_b.cluster_bootstrap_delta_ci(pair_records, seed=seed, treat_key="eng_strong", base_key="raw_strong")
    report = stage_b.stage_b_report_1b(att, cmh, ci, cv)
    report["icc"] = stage_b.intraclass_correlation(icc)
    spent = sum(r["cost"] for r in runs)
    pathlib.Path(_WS, "stage_b_adjudications_1b.json").write_text(
        json.dumps({"soundness_v2": runs, "report": report, "spent_usd": spent}, indent=2, default=str), encoding="utf-8")
    return {"report": report, "spent_usd": spent}


async def run_stage_b_resume(*, tolerance, soundness_models, brain_budget, seed, max_pairs, concurrency=8):
    """Complete a tolerance-aborted run from stage_b_resume.json — runs ONLY the soundness panel + scoring on the SAVED
    adjudications (no re-spend of arms+canon+adjudicate). The resume --tolerance is the ceiling for the soundness stage."""
    global _sem
    _sem = asyncio.Semaphore(max(1, int(concurrency)))
    resume_path = pathlib.Path(_WS, "stage_b_resume.json")
    if not resume_path.exists():
        raise SystemExit(f"[stage_b] resume: no saved record at {resume_path} (only a tolerance-aborted run writes one).")
    data = json.loads(resume_path.read_text(encoding="utf-8"))
    already = float(data.get("spent_usd", 0.0))
    sound_ids = ({a["id"] for a in data["adjudications"] if a["survived"]}
                 | {bid for bid, o in data["origin"].items() if o["control"]})
    proj = len(sound_ids) * len(soundness_models) * _C_STRONG
    print(f"[stage_b] RESUME: {len(data['blinded'])} items; arms+adjudicate ALREADY spent ${already:.2f} (not re-spent); "
          f"projected soundness ~${proj:.2f} for {len(sound_ids)} items x {len(soundness_models)} judges.")
    if proj > tolerance:
        print(f"[stage_b] RESUME ABORT: projected soundness ~${proj:.2f} > --tolerance ${tolerance}. Raise --tolerance.")
        return {"report": {"verdict": "RESUME-ABORTED-TOLERANCE-TOO-LOW", "projected_soundness": round(proj, 2)},
                "spent_usd": already}
    # resume exists ONLY to complete the deferred soundness leg of a --no-distant-only run (the resume record is written
    # exclusively from the `if not distant_only:` pre-soundness gate), so force distant_only=False here — else _finish's
    # new default (=True) would silently skip the very soundness panel resume was re-invoked to run.
    return await _finish(data["blinded"], data["origin"], data["adjudications"],
                         off_distribution=int(data.get("off_distribution", 0)), cost_by_arm=data.get("cost_by_arm", {}),
                         spent=already, soundness_models=soundness_models, brain_budget=brain_budget, seed=seed,
                         n_pairs=int(data.get("n_pairs", 0)), max_pairs=max_pairs, distant_only=False)


async def run_stage_b(pairs, *, tolerance, model_specs, brain_budget, snapshot_path, n_per_pair, pool_size,
                      strong_model, engine_strong_models, adjudicator_models, soundness_models, confirm_model,
                      knn_k, sim_threshold, knn_embedder, date_cutoff="2026-06-24", max_pairs, seed=0, concurrency=8,
                      controls_only=False, distant_only=True):
    global _sem
    _sem = asyncio.Semaphore(max(1, int(concurrency)))   # bound OpenRouter concurrency (created inside the loop)
    _load_knn(snapshot_path, knn_embedder)               # fail-closed: aborts if faiss/SPECTER2 absent
    proposer = model_specs[0]["id"]                      # cheap raw proposer (raw_weak) + cheap engine fleet (eng_weak)
    strong_specs = [{"id": m} for m in engine_strong_models]   # eng_strong fleet: [opus-4.7 (proposer), strong judge]
    spent = 0.0
    cost_by_arm = {"raw_weak": 0.0, "eng_weak": 0.0, "eng_strong": 0.0, "raw_strong": 0.0,
                   "adjudicate": 0.0, "soundness": 0.0}
    all_cands, off_distribution = [], 0

    if not controls_only:
        for idx, pair in enumerate(pairs):
            if tolerance - spent <= 0:
                print(f"[stage_b] WARNING: tolerance ${tolerance} exhausted after {idx}/{len(pairs)} pairs; "
                      "stopping early (partial, honest).")
                break
            # raw_weak (cheap raw, unfiltered)
            rw, c = await _raw_arm(pair, proposer, "raw_weak", n=n_per_pair, brain_budget=brain_budget)
            spent += c; cost_by_arm["raw_weak"] += c; all_cands.extend(rw)
            # eng_weak (engine on the cheap fleet, grounding OFF)
            out_ew = await combine_live.run_combine([pair], tolerance=tolerance - spent, model_specs=model_specs,
                                                    brain_budget=brain_budget, snapshot_path=snapshot_path,
                                                    date_cutoff="2026-06-24", n_per_pair=n_per_pair,
                                                    proposal_mode="engine", ground=False)
            spent += float(out_ew.get("spent_usd") or 0.0); cost_by_arm["eng_weak"] += float(out_ew.get("spent_usd") or 0.0)
            off_distribution += int(out_ew.get("off_distribution_count") or 0)
            all_cands.extend(_elites_from(out_ew, pair, "eng_weak"))
            # eng_strong (engine on the STRONG single-proposer fleet, grounding OFF) — the new arm
            out_es = await combine_live.run_combine([pair], tolerance=tolerance - spent, model_specs=strong_specs,
                                                    brain_budget=brain_budget, snapshot_path=snapshot_path,
                                                    date_cutoff="2026-06-24", n_per_pair=n_per_pair,
                                                    proposal_mode="engine", ground=False)
            spent += float(out_es.get("spent_usd") or 0.0); cost_by_arm["eng_strong"] += float(out_es.get("spent_usd") or 0.0)
            off_distribution += int(out_es.get("off_distribution_count") or 0)
            all_cands.extend(_elites_from(out_es, pair, "eng_strong"))
            # raw_strong (opus-4.7 raw, unfiltered)
            rs, c = await _raw_arm(pair, strong_model, "raw_strong", n=n_per_pair, brain_budget=brain_budget)
            spent += c; cost_by_arm["raw_strong"] += c; all_cands.extend(rs)

    # controls (4 classes) -> tagged candidates (loaded here so --controls-only can use them early)
    controls = json.loads(pathlib.Path(_WS, "controls_b.json").read_text(encoding="utf-8"))
    ctrl_cands = []
    for cls in ("neg", "pos", "fringe", "hard_neg"):
        for c in controls.get(cls, []):
            ctrl_cands.append({**c, "arm": None, "pair": f"{c.get('domain_a','')}:{c.get('domain_b','')}"})

    # --controls-only calibration mode: skip the arms, dual-leg adjudicate ONLY the controls (cheap threshold sweep)
    if controls_only:
        proj = len(ctrl_cands) * (_C_WEB + 0.6 * _C_CHEAP + 1.0 * _C_CHEAP)
        if proj > tolerance:
            print(f"[stage_b] CONTROLS-ONLY ABORT: projected ~${proj:.2f} > --tolerance ${tolerance}. Raise --tolerance.")
            return {"report": {"verdict": "CONTROLS-ONLY-ABORTED-TOLERANCE-TOO-LOW", "projected": round(proj, 2)},
                    "spent_usd": 0.0}
        blinded, origin = stage_a.blind_candidates(ctrl_cands, seed=seed)
        adj = await asyncio.gather(*[_adjudicate_one(b, adjudicator_models, confirm_model, knn_k=knn_k,
                                     sim_threshold=sim_threshold, date_cutoff=date_cutoff, brain_budget=brain_budget)
                                     for b in blinded])
        surv = {a["id"]: a["survived"] for a in adj}
        cres = [{"control": o["control"], "survived": surv.get(bid, False), "sound": False}
                for bid, o in origin.items() if o["control"] is not None]
        cv = stage_b.control_verdict_b(cres)
        print(f"[stage_b] CONTROLS-ONLY (kNN thr={sim_threshold}): {cv}")
        return {"report": {"verdict": "CONTROLS-ONLY", "controls": cv, "knn_sim_threshold": sim_threshold},
                "spent_usd": sum(a["cost"] for a in adj)}

    items = all_cands + ctrl_cands
    # MONEY-SAFETY: the back-half (dual-leg adjudicate + soundness) is the cost bulk and is NOT pair-gated.
    # Project it for the ACTUAL item count; if it would breach tolerance, ABORT before spending (a partial adjudication
    # would be a BIASED measurement) and tell the operator to raise --tolerance or reduce --pairs. (tolerance = ceiling.)
    n_items = len(items)
    _ADJ_PER_ITEM = _C_WEB + 0.6 * _C_CHEAP + 1.0 * _C_CHEAP          # sonar + legA-confirm + legB-confirm(s)
    proj_back = n_items * _ADJ_PER_ITEM + (0.0 if distant_only else
                                           (0.5 * n_items + len(ctrl_cands)) * len(soundness_models) * _C_STRONG)
    if spent + proj_back > tolerance:
        msg = (f"[stage_b] ABORT (tolerance ${tolerance} too low): arms spent ${spent:.2f}, projected back-half "
               f"~${proj_back:.2f} for {n_items} items. Raise --tolerance to ~${spent + proj_back:.0f} or reduce "
               "--pairs. NOT running a partial (biased) adjudication.")
        print(msg)
        return {"report": {"verdict": "ABORTED-TOLERANCE-TOO-LOW", "projected_total": round(spent + proj_back, 2),
                           "items": n_items, "arms_spent": round(spent, 2)}, "spent_usd": spent}
    # MONEY-SAFETY backstop: gate the (pricey, ~web-panel) adjudication stage on actual spend so far.
    proj_adjud = n_items * _ADJ_PER_ITEM
    if spent + proj_adjud > tolerance:
        print(f"[stage_b] ABORT pre-adjudication (tolerance ${tolerance}): spent ${spent:.2f} + projected adjudication "
              f"~${proj_adjud:.2f} for {n_items} items. Raise --tolerance to ~${spent + proj_adjud:.0f}.")
        return {"report": {"verdict": "ABORTED-TOLERANCE-TOO-LOW (pre-adjudication)",
                           "projected_total": round(spent + proj_adjud, 2), "arms_spent": round(spent, 2),
                           "items": n_items}, "spent_usd": spent}

    blinded, origin = stage_a.blind_candidates(items, seed=seed)
    adjud = await asyncio.gather(*[_adjudicate_one(b, adjudicator_models, confirm_model, knn_k=knn_k,
                                   sim_threshold=sim_threshold, date_cutoff=date_cutoff, brain_budget=brain_budget)
                                   for b in blinded])
    cost_by_arm["adjudicate"] = sum(a["cost"] for a in adjud); spent += cost_by_arm["adjudicate"]
    surv_by_id = {a["id"]: a["survived"] for a in adjud}
    if not distant_only:
        sound_ids = {a["id"] for a in adjud if a["survived"]} | {bid for bid, o in origin.items() if o["control"]}
        proj_sound = len(sound_ids) * len(soundness_models) * _C_STRONG
        if spent + proj_sound > tolerance:
            _WS.mkdir(parents=True, exist_ok=True)
            pathlib.Path(_WS, "stage_b_resume.json").write_text(json.dumps(
                {"blinded": blinded, "origin": origin, "adjudications": adjud, "off_distribution": off_distribution,
                 "cost_by_arm": cost_by_arm, "spent_usd": spent, "n_pairs": len(pairs)}, indent=2, default=str),
                encoding="utf-8")
            print(f"[stage_b] ABORT pre-soundness (tolerance ${tolerance}): spent ${spent:.2f} + projected soundness "
                  f"~${proj_sound:.2f}. Adjudication record SAVED to stage_b_resume.json -> `resume`.")
            return {"report": {"verdict": "ABORTED-TOLERANCE-TOO-LOW (pre-soundness)",
                               "projected_total": round(spent + proj_sound, 2), "arms_adjud_spent": round(spent, 2),
                               "survivors_plus_controls": len(sound_ids), "resume_saved": True}, "spent_usd": spent}
    return await _finish(blinded, origin, adjud, off_distribution=off_distribution, cost_by_arm=cost_by_arm,
                         spent=spent, soundness_models=soundness_models, brain_budget=brain_budget, seed=seed,
                         n_pairs=len(pairs), max_pairs=max_pairs, distant_only=distant_only)


def _parse_pairs(pairs):
    out = []
    for p in (pairs or []):
        parts = str(p).split(":")
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            out.append((parts[0].strip(), parts[1].strip()))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="labcoat N3 Stage-B measurement (operator).")
    sub = ap.add_subparsers(dest="mode")
    for name in ("estimate", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--pairs", nargs="+", required=True)
        sp.add_argument("--models", type=int, default=4)
        sp.add_argument("--n-per-pair", type=int, default=10)
        sp.add_argument("--pool-size", type=int, default=50,
                        help="arm i* raw pool size (LARGER than n-per-pair so the matched selector has material; spec ~50)")
        sp.add_argument("--snapshot", default=_DEFAULT_SNAPSHOT)
        sp.add_argument("--strong-model", default=_DEFAULT_STRONG)
        sp.add_argument("--adjudicator-models", nargs="+", default=_DEFAULT_ADJUDICATORS)
        sp.add_argument("--soundness-models", nargs="+", default=_DEFAULT_SOUNDNESS)
        sp.add_argument("--confirm-model", default="openai/gpt-4o-mini")
        sp.add_argument("--knn-k", type=int, default=5)
        sp.add_argument("--knn-sim-threshold", type=float, default=0.20,
                        help="cosine-DISTANCE cutoff for the kNN prior-art leg (CALIBRATE on controls; spec default 0.20)")
        sp.add_argument("--knn-embedder", default="specter2")
        sp.add_argument("--engine-strong-models", nargs="+",
                        default=["anthropic/claude-opus-4.7", "google/gemini-2.5-pro"],
                        help="eng_strong fleet: [opus-4.7 (proposer), strong judge]; partition puts ms[:1] as proposer")
        sp.add_argument("--distant-only", action=argparse.BooleanOptionalAction, default=True,
                        help="v4: skip the soundness panel, PRIMARY=distant(eng_strong-raw_strong) (pass --no-distant-only to restore soundness)")
        sp.add_argument("--controls-only", action="store_true",
                        help="calibration mode: skip the arms, dual-leg adjudicate ONLY the controls (cheap threshold sweep)")
        sp.add_argument("--max-pairs", type=int, default=28)
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--concurrency", type=int, default=8, help="max concurrent OpenRouter calls (rate-limit guard)")
        if name == "run":
            sp.add_argument("--tolerance", type=float, required=True)
            sp.add_argument("--brain-budget", type=float, default=0.20)
    rp = sub.add_parser("resume", help="finish a tolerance-aborted run from stage_b_resume.json (soundness-only).")
    rp.add_argument("--tolerance", type=float, required=True)
    rp.add_argument("--brain-budget", type=float, default=0.20)
    rp.add_argument("--soundness-models", nargs="+", default=_DEFAULT_SOUNDNESS)
    rp.add_argument("--seed", type=int, default=0)
    rp.add_argument("--max-pairs", type=int, default=28)
    rp.add_argument("--concurrency", type=int, default=8)
    cp = sub.add_parser("calibrate-soundness", help="Phase-A: run the v2 panel on controls -> validity gate (PAID, cheap).")
    cp.add_argument("--tolerance", type=float, required=True)
    cp.add_argument("--soundness-models", nargs="+", default=_DEFAULT_SOUNDNESS)
    cp.add_argument("--brain-budget", type=float, default=0.20)
    cp.add_argument("--concurrency", type=int, default=8)
    s1 = sub.add_parser("soundness-1b", help="Phase-B: run the validated v2 panel on the saved v4 survivors -> sound_distant (PAID).")
    s1.add_argument("--tolerance", type=float, required=True)
    s1.add_argument("--soundness-models", nargs="+", default=_DEFAULT_SOUNDNESS)
    s1.add_argument("--brain-budget", type=float, default=0.20)
    s1.add_argument("--seed", type=int, default=0)
    s1.add_argument("--concurrency", type=int, default=8)
    s1.add_argument("--dry-run", action="store_true", help="FREE: load v4 survivors, print per-arm counts, no paid call.")
    args = ap.parse_args()
    if not args.mode:
        ap.print_help(); return
    if args.mode == "resume":
        nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")
        out = asyncio.run(run_stage_b_resume(tolerance=args.tolerance, soundness_models=args.soundness_models,
                                             brain_budget=args.brain_budget, seed=args.seed, max_pairs=args.max_pairs,
                                             concurrency=args.concurrency))
        _print_report(out, args.tolerance); return
    if args.mode == "calibrate-soundness":
        nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")
        out = asyncio.run(run_calibrate_soundness(tolerance=args.tolerance, soundness_models=args.soundness_models,
                                                  brain_budget=args.brain_budget, concurrency=args.concurrency))
        print(f"[stage_b] CALIBRATE-SOUNDNESS v2: {out['controls']}  spent=${out['spent_usd']:.4f}")
        return
    if args.mode == "soundness-1b":
        out = asyncio.run(run_soundness_1b(tolerance=args.tolerance, soundness_models=args.soundness_models,
                                           brain_budget=args.brain_budget, seed=args.seed, concurrency=args.concurrency,
                                           dry_run=args.dry_run))
        print(f"\n[stage_b] === N3 STAGE-B 1b REPORT ===\n  {out['report'].get('verdict')}")
        for k in ("primary_delta", "cmh_p_one_sided", "ci", "eng_strong_sound_survivors", "exclusion_by_arm"):
            if k in out["report"]:
                print(f"  {k}={out['report'][k]}")
        print(f"  spent=${out['spent_usd']:.4f}")
        return
    pairs = _parse_pairs(args.pairs)
    if not pairs:
        raise SystemExit('[stage_b] no valid --pairs (use "DomainA:DomainB")')
    nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")
    specs, _ = nuclear._pick_models(args.models)
    if len(specs) < 2:
        raise SystemExit("[stage_b] need >= 2 cheap fleet models (proposer != judge)")
    # REALISTIC staged estimate — the back-half (dual-leg adjudicate + strong soundness panel) dominates and is NOT
    # priced by spend.two_line_estimate (cheap-fleet rates only). Set --tolerance >= the total below.
    total, brk, approx_cands = _staged_estimate(len(pairs), args.n_per_pair, args.pool_size,
                                                len(args.soundness_models), distant_only=args.distant_only)
    print(f"[stage_b] ESTIMATE (rough, v4 2x2, distant_only={args.distant_only}): OpenRouter ~${total:.2f} total "
          f"[arms ${brk['arms']} + adjudicate(dual-leg) ${brk['adjudicate']} + soundness ${brk['soundness']}]; "
          f"pairs={len(pairs)}; ~candidates={approx_cands}; cheap-fleet={[s['id'] for s in specs]}; "
          f"raw_strong={args.strong_model}; eng_strong_fleet={args.engine_strong_models}; "
          f"adjudicator(Leg-A)={args.adjudicator_models}; knn-k={args.knn_k}; "
          f"knn-sim-threshold={args.knn_sim_threshold}.  >> set --tolerance >= ${total:.0f}.")
    if args.mode == "estimate":
        print("[stage_b] estimate-only; re-run with `run --tolerance <usd>` to fire."); return
    out = asyncio.run(run_stage_b(pairs, tolerance=args.tolerance, model_specs=specs, brain_budget=args.brain_budget,
                                  snapshot_path=args.snapshot, n_per_pair=args.n_per_pair, pool_size=args.pool_size,
                                  strong_model=args.strong_model, engine_strong_models=args.engine_strong_models,
                                  adjudicator_models=args.adjudicator_models, soundness_models=args.soundness_models,
                                  confirm_model=args.confirm_model, knn_k=args.knn_k, sim_threshold=args.knn_sim_threshold,
                                  knn_embedder=args.knn_embedder, controls_only=args.controls_only,
                                  max_pairs=args.max_pairs, seed=args.seed, concurrency=args.concurrency,
                                  distant_only=args.distant_only))
    _print_report(out, args.tolerance)


def _print_report(out, tolerance):
    rep = out["report"]
    print("\n[stage_b] === N3 STAGE-B REPORT (ADVISORY) ===")
    print(f"  VERDICT: {rep['verdict']}")
    if str(rep.get("verdict", "")).startswith(("ABORTED", "RESUME-ABORTED", "CONTROLS-ONLY")):  # tolerance/controls stub
        for k, v in rep.items():
            if k != "verdict":
                print(f"  {k}={v}")
        print(f"  spent=${out['spent_usd']:.4f} (tol ${tolerance}); raise --tolerance and re-run/resume.")
        return
    if "eng_strong_distant_survivors" in rep:    # v4 2x2 distant-only report
        print(f"  primary_metric={rep['primary_metric']}  basis={rep.get('primary_metric_basis')}")
        print(f"  PRIMARY delta (eng_strong - raw_strong) = {rep['primary_delta']}  "
              f"CMH p_one_sided={rep['cmh_p_one_sided']:.4f}  CI={rep['ci']}  "
              f"eng_strong_distant_survivors={rep['eng_strong_distant_survivors']}")
        print(f"  ablation(2x2): {rep['ablation']}")
        print(f"  controls: {rep['controls']}")
        print(f"  ICC={rep.get('icc')}  adjudicator_kappa={rep['adjudicator_kappa']:.3f}  "
              f"off_distribution={rep['off_distribution']}")
        print(f"  sequential: {rep['sequential']}")
        print(f"  spent=${out['spent_usd']:.4f} (tol ${tolerance})  cost_by_arm={rep['cost_by_arm']}")
        print(f"  CEILING: {rep['ceiling_caveat']}")
        return
    print(f"  primary_metric={rep['primary_metric']}  soundness_untrusted={rep['soundness_untrusted']}  "
          f"primary_metric_basis={rep.get('primary_metric_basis')}")
    print(f"  PRIMARY delta (ii - i*) = {rep['primary_delta']}  CMH p_one_sided={rep['cmh_p_one_sided']:.4f}  "
          f"CI={rep['ci']}  ii_genuine_survivors={rep['ii_genuine_survivors']}")
    print(f"  ablation: {rep['ablation']}")
    print(f"  controls: {rep['controls']}")
    print(f"  ICC={rep.get('icc')}  adjudicator_kappa={rep['adjudicator_kappa']:.3f}  off_distribution={rep['off_distribution']}")
    print(f"  sequential: {rep['sequential']}")
    print(f"  spent=${out['spent_usd']:.4f} (tol ${tolerance})  cost_by_arm={rep['cost_by_arm']}")
    print(f"  CEILING: {rep['ceiling_caveat']}")


if __name__ == "__main__":
    main()
