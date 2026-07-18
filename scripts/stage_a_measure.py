# scripts/stage_a_measure.py
"""Operator LIVE entrypoint for N3 Stage-A — the cheap, dogfood-hardened machinery-attribution + ruler-validity test.
NOT unit-tested; `run` spends a few cents on OpenRouter (cheap fleet only). Mirrors combine_live.py's gates
(estimate-first, tolerance ceiling, keys in-process, never printed). Pipeline: per pair, arm (i) RAW baseline +
arm (ii) FULL-N3 (combine_live) -> blind (with stratified controls) -> objective cite-or-fail prior-art adjudication
-> attribution (rate delta) + control verdict -> honest report. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import argparse, asyncio, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nuclear, spend, combinatorial, combine_live, stage_a

_WS = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "build4-n3-measurement-design-validation"
_DEFAULT_SNAPSHOT = str(pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-openalex-snapshot")


async def _raw_arm(pair, model_id, *, n, brain_budget):
    a, b = pair
    res = await nuclear._brain(stage_a.raw_propose_prompt(a, b, n=n), transport="openrouter", model=model_id,
                              max_budget_usd=brain_budget, max_turns=1, web=False)
    combos = combinatorial.parse_combinations(res.get("text") or "")
    for c in combos:
        c["arm"], c["pair"], c["control"] = "i", f"{a}:{b}", None
    return combos, float(res.get("cost_usd") or 0.0)


async def _adjudicate(blinded, adjudicator_model, *, brain_budget):
    """Calibrated relevance-gated cite-or-fail adjudication on the BLINDED candidates (web=True).
    Uses relevance_prompt/parse_relevance (not prior_art_prompt/parse_prior_art) so that genuine
    cross-domain novelty survives while routine applications + specific prior transfers are caught."""
    async def one(b):
        # web=False to MATCH the validated v2 probe exactly: sonar-pro searches natively, and web=True would append
        # ":online" to the model id (a different OpenRouter route/price). Reproducibility > a redundant flag.
        r = await nuclear._brain(stage_a.relevance_prompt(b["claim"], b.get("mechanism", "")),
                                 transport="openrouter", model=adjudicator_model, max_budget_usd=brain_budget,
                                 max_turns=1, web=False)
        pa = stage_a.parse_relevance(r.get("text") or "")
        return {"id": b["id"], "survived": stage_a.survives_objective(pa), "prior_art": pa,
                "cost": float(r.get("cost_usd") or 0.0)}
    return await asyncio.gather(*[one(b) for b in blinded])


async def run_stage_a(pairs, *, tolerance, model_specs, brain_budget, snapshot_path, n_per_pair, seed=0,
                      adjudicator_model="perplexity/sonar-pro"):
    proposer = model_specs[0]["id"]                 # cheap raw proposer (arm i)
    # adjudicator_model is a separate real-web model (sonar-pro searches natively); NOT model_specs[-1]
    spent = 0.0
    all_cands = []
    off_distribution = 0
    for idx, pair in enumerate(pairs):
        if tolerance - spent <= 0:   # guard: never start a pair with no budget -> would silently skip arm-ii's
            print(f"[stage_a] WARNING: tolerance ${tolerance} exhausted after {idx}/{len(pairs)} pairs "
                  "(arm-ii judge+grounding would be skipped, biasing attribution); stopping early (partial, honest).")
            break  # judge+grounding inside run_combine, biasing attribution toward a false HONEST-NEGATIVE
        raw, raw_cost = await _raw_arm(pair, proposer, n=n_per_pair, brain_budget=brain_budget); spent += raw_cost
        all_cands.extend(raw)
        out = await combine_live.run_combine([pair], tolerance=tolerance - spent, model_specs=model_specs,
                                             brain_budget=brain_budget, snapshot_path=snapshot_path,
                                             date_cutoff="2026-06-24", n_per_pair=n_per_pair)
        spent += float(out.get("spent_usd") or 0.0)
        off_distribution += int(out.get("off_distribution_count") or 0)
        for c2 in combinatorial.elites(out.get("archive") or {}):
            c2 = dict(c2); c2["arm"], c2["pair"], c2["control"] = "ii", f"{pair[0]}:{pair[1]}", None
            all_cands.append(c2)
    # controls (stratified, style-matched) -> tagged candidates
    controls = json.loads(pathlib.Path(_WS, "controls.json").read_text(encoding="utf-8"))
    ctrl_cands = []
    for c in controls.get("negative", []) + controls.get("positive", []):
        ctrl_cands.append({**c, "arm": None, "pair": c.get("domain_a", "") + ":" + c.get("domain_b", "")})
    blinded, origin = stage_a.blind_candidates(all_cands + ctrl_cands, seed=seed)
    adjud = await _adjudicate(blinded, adjudicator_model, brain_budget=brain_budget)
    spent += sum(a["cost"] for a in adjud)
    # join adjudication back to origin
    by_id = {a["id"]: a for a in adjud}
    arm_i = [{"survived": by_id[i]["survived"]} for i, o in origin.items() if o["arm"] == "i" and i in by_id]
    arm_ii = [{"survived": by_id[i]["survived"]} for i, o in origin.items() if o["arm"] == "ii" and i in by_id]
    ctrl_results = [{"id": i, "control": o["control"], "survived": by_id[i]["survived"]}
                    for i, o in origin.items() if o["control"] in ("neg", "pos") and i in by_id]
    att = stage_a.attribution(arm_i, arm_ii)
    cv = stage_a.control_verdict(ctrl_results)
    report = stage_a.stage_a_report(att, cv, off_distribution)
    # write the blinded adjudications + origin for the later (blinded) operator read
    pathlib.Path(_WS, "stage_a_adjudications.json").write_text(
        json.dumps({"blinded": blinded, "origin": origin, "adjudications": adjud, "report": report}, indent=2),
        encoding="utf-8")
    return {"report": report, "spent_usd": spent}


def _parse_pairs(pairs):
    out = []
    for p in (pairs or []):
        parts = str(p).split(":")
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            out.append((parts[0].strip(), parts[1].strip()))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="labcoat N3 Stage-A measurement (operator).")
    sub = ap.add_subparsers(dest="mode")
    _DEFAULT_ADJUDICATOR = "perplexity/sonar-pro"
    for name in ("estimate", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--pairs", nargs="+", required=True)
        sp.add_argument("--models", type=int, default=3)
        sp.add_argument("--n-per-pair", type=int, default=3)
        sp.add_argument("--snapshot", default=_DEFAULT_SNAPSHOT)
        sp.add_argument("--adjudicator-model", default=_DEFAULT_ADJUDICATOR,
                        help="Model used for the calibrated relevance adjudicator (real-web; default: sonar-pro)")
        if name == "run":
            sp.add_argument("--tolerance", type=float, required=True)
            sp.add_argument("--brain-budget", type=float, default=0.20)
    args = ap.parse_args()
    if not args.mode:
        ap.print_help(); return
    pairs = _parse_pairs(args.pairs)
    if not pairs:
        raise SystemExit('[stage_a] no valid --pairs (use "DomainA:DomainB")')
    nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")
    specs, _ = nuclear._pick_models(args.models)
    if len(specs) < 2:
        raise SystemExit("[stage_a] need >= 2 cheap fleet models")
    # rough estimate: arm i (1) + arm ii fleet + ~ (pairs*n*2 + 10 controls) adjudications
    n_adj = len(pairs) * args.n_per_pair * 2 + 10
    est = spend.two_line_estimate(specs, n_agents=max(1, n_adj), is_loop_cycle=False)
    adj_model = args.adjudicator_model
    print(f"[stage_a] ESTIMATE (very-rough): OpenRouter ${est['openrouter_usd']} (conf {est['confidence']}); "
          f"pairs={pairs}; fleet={[s['id'] for s in specs]}; adjudications~{n_adj}; "
          f"adjudicator-model={adj_model}")
    if args.mode == "estimate":
        print("[stage_a] estimate-only; re-run with `run --tolerance <usd>` to fire."); return
    out = asyncio.run(run_stage_a(pairs, tolerance=args.tolerance, model_specs=specs,
                                  brain_budget=args.brain_budget, snapshot_path=args.snapshot,
                                  n_per_pair=args.n_per_pair, adjudicator_model=adj_model))
    rep = out["report"]
    print("\n[stage_a] === N3 STAGE-A REPORT (ADVISORY) ===")
    print(f"  VERDICT: {rep['verdict']}")
    print(f"  arm_i (raw)  : {rep['attribution']['arm_i']}")
    print(f"  arm_ii (N3)  : {rep['attribution']['arm_ii']}")
    print(f"  machinery_delta_rate={rep['attribution']['machinery_delta_rate']}  ruler_clean={rep['ruler_clean']}")
    print(f"  controls: {rep['controls']}")
    print(f"  off_distribution={rep['off_distribution']}  spent=${out['spent_usd']:.4f} (tol ${args.tolerance})")
    print(f"  CEILING: {rep['ceiling_caveat']}")


if __name__ == "__main__":
    main()
