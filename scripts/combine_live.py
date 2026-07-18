# scripts/combine_live.py
"""Operator LIVE entrypoint for N3 — the combinatorial / analogical generate-judge-GROUND loop. NOT unit-tested;
`run` spends a few cents on the OpenRouter fleet. Mirrors nuclear.py's gates (estimate-first, tolerance ceiling,
keys in-process from ~/.secrets, never printed). Reuses nuclear.py's brain/fleet/secret helpers + the live N1
adapter (n1_embedder/n1_index) as the novelty judge + the PURE combinatorial core (run_round seam).

Pipeline: --pairs -> partition_fleet (proposer != judge) -> PROPOSE (proposer pool) -> NOVELTY (N1 external)
-> JUDGE utility (judge pool) -> run_round (MAP-Elites archive) -> web-GROUND the elites -> honest report
(coverage + qd_score UPPER BOUND + post-grounding survival SEPARATE + off-distribution count). N3 is ADVISORY;
qd_score is never 'discoveries'; the integrated stack is net-new + UNMEASURED. License: MIT. Author: Allen Byrd.

Usage:
  python scripts/combine_live.py estimate --pairs "immunology:distributed-systems" "cryptography:ecology"
  python scripts/combine_live.py run --pairs "immunology:distributed-systems" --tolerance 0.50 \
        --snapshot _internal/n1-index-snapshot [--models 4] [--n-per-pair 3] [--date-cutoff 2026-06-24]
"""
from __future__ import annotations
import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nuclear
import spend
import combinatorial
import stage_a            # raw_propose_prompt (the matched arm-i* / raw proposal mode)
import n1_embedder
import n1_index
import n1_novelty

_DEFAULT_SNAPSHOT = str(pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-index-snapshot")


def _parse_pairs(pairs):
    """['A:B', ...] -> [(A, B), ...]; skip malformed (need exactly one ':' with both sides non-empty)."""
    out = []
    for p in (pairs or []):
        parts = str(p).split(":")
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            out.append((parts[0].strip(), parts[1].strip()))
        else:
            print(f"[combine] WARNING: skipping malformed pair {p!r} (expected 'DomainA:DomainB')")
    return out


async def run_combine(pairs, *, tolerance, model_specs, brain_budget, snapshot_path, date_cutoff,
                      n_per_pair=3, judge_fraction=0.5, proposal_mode="engine", ground=True) -> dict:
    """The async N3 combine orchestration. Returns {report, archive, off_distribution_count, admitted, spent_usd,
    elites_grounded}. All fleet I/O via nuclear._brain (OpenRouter transport); the pure run_round does the scoring.

    Stage-B ablation seam (the ONLY two knobs that differ between the matched arms; everything else — N1 novelty,
    judge utility, run_round MAP-Elites selection — is held IDENTICAL):
      - proposal_mode="engine" (default): the structure-mapping analogical proposer (combinatorial.propose_prompt).
      - proposal_mode="raw":    the plain raw proposer (stage_a.raw_propose_prompt) — arm i* (matched selection on raw
        proposals). ii vs i* isolates the PROPOSAL prompt with selection held constant.
      - ground=True (default): web-ground the elites (step 5). ground=False: skip grounding (arm-ii grounding-OFF so all
        Stage-B arms are grounding-matched); grounded_survivors stays None (survival rate honestly n/a)."""
    pools = combinatorial.partition_fleet(model_specs, judge_fraction=judge_fraction)
    proposers, judges = pools["proposer_pool"], pools["judge_pool"]
    grounding_model = judges[0]["id"]   # a SINGLE judge model grounds each elite (cost-saving; see step 5)
    print(f"[combine] proposer_pool={[m['id'] for m in proposers]} | judge_pool={[m['id'] for m in judges]}")

    if not n1_embedder.n1_embedder_available() or not n1_index.n1_index_available():
        raise SystemExit("[combine] live N1 deps missing — run: pip install -r requirements-n1.txt")
    emb = n1_embedder.load_embedder("specter2")
    if not pathlib.Path(snapshot_path, "meta.json").exists():
        raise SystemExit(f"[combine] no N1 snapshot at {snapshot_path} — run: python scripts/smoke_n1_live.py build")
    idx = n1_index.load_snapshot(snapshot_path, active_fingerprint=emb.fingerprint())  # fail-closed on drift
    thr = idx._loaded_threshold

    spent = 0.0   # single OpenRouter cost line (sum of per-call cost_usd); no spend.Tracker breakdown needed here

    def _add(results):
        nonlocal spent
        for r in results:
            spent += float(r.get("cost_usd") or 0.0)

    async def _fleet(prompt, model_id, *, web):
        return await nuclear._brain(prompt, transport="openrouter", model=model_id,
                                    max_budget_usd=brain_budget, max_turns=1, web=web)

    # 1. PROPOSE (proposer pool x pairs) — engine (structure-mapping) vs raw (the matched-selection arm i*)
    def _propose_prompt(a, b):
        if proposal_mode == "raw":
            return stage_a.raw_propose_prompt(a, b, n=n_per_pair)
        return combinatorial.propose_prompt(a, b, n=n_per_pair)
    ptasks = [((a, b), m["id"], _fleet(_propose_prompt(a, b), m["id"], web=False))
              for (a, b) in pairs for m in proposers]
    presults = await asyncio.gather(*[t for (_, _, t) in ptasks])
    _add(presults)
    raw = []
    for (_, _, _), res in zip(ptasks, presults):
        raw.extend(combinatorial.parse_combinations(res.get("text") or ""))
    seen, combos = set(), []
    for c in raw:                                   # dedupe by normalized claim; re-id c1..cN
        key = combinatorial._norm(c.get("claim"))
        if key and key not in seen:
            seen.add(key)
            combos.append({**c, "id": f"c{len(combos) + 1}"})
    print(f"[combine] proposed {len(combos)} unique combinations (spent ${spent:.4f})")
    if not combos:
        return {"report": combinatorial.archive_report({}), "archive": {}, "off_distribution_count": 0,
                "admitted": [], "spent_usd": spent, "elites_grounded": [], "grounding_model": None}

    # 2. NOVELTY (N1) + retrieved prior art (sync)
    novelty_map, prior_art, off_dist = {}, {}, 0
    for c in combos:
        qv = emb.embed([c.get("claim") or ""], role="query")[0]
        nv = n1_novelty.external_novelty_capped(qv, idx, k=10, date_cutoff=date_cutoff,
                                                off_distribution_threshold=thr)
        novelty_map[c["id"]] = nv["score"]
        off_dist += 1 if nv["off_distribution"] else 0
        prior_art[c["id"]] = [nv["nearest"]["title"]] if nv.get("nearest") else []
    print(f"[combine] N1 novelty scored; off_distribution={off_dist}/{len(combos)} "
          "(query-calibrated out-of-corpus guard; a low count = coherent/in-corpus claims, NOT proven-novel; "
          "gate is meaningful-not-strong — thin SPECTER2 margin on short claims)")

    # 3. JUDGE utility (judge pool x combos)
    if spent <= tolerance:
        jtasks = [(c["id"], _fleet(combinatorial.judge_prompt(c, prior_art[c["id"]]), m["id"], web=False))
                  for c in combos for m in judges]
        jresults = await asyncio.gather(*[t for (_, t) in jtasks])
        _add(jresults)
        by_combo = {}
        for (cid, _), res in zip(jtasks, jresults):
            by_combo.setdefault(cid, []).append(combinatorial.parse_judge(res.get("text") or ""))
        utility_map = {cid: combinatorial.aggregate_utility(js) for cid, js in by_combo.items()}
    else:
        print(f"[combine] tolerance ${tolerance} reached after propose; skipping judge (honest partial).")
        utility_map = {}

    # 4. run_round (PURE)
    result = combinatorial.run_round(combos, novelty_fn=lambda c: novelty_map.get(c["id"], 0.0),
                                     utility_fn=lambda c: utility_map.get(c["id"], 0.0))
    archive = result["archive"]
    the_elites = combinatorial.elites(archive)
    print(f"[combine] run_round: {len(result['admitted'])} admitted, {len(result['zero_value'])} zero-value, "
          f"{len(result['rejected_incoherent'])} incoherent; {len(the_elites)} elites")

    # 5. GROUND the elites (web=True hard-skeptic) — the only 'real' survival signal. A SINGLE judge model grounds
    # each elite (cost-saving; grounding is a hard-skeptic binary, not a consensus vote) — the model is surfaced.
    survivors = []
    if ground and the_elites and spent <= tolerance:
        gtasks = [(e.get("id"), _fleet(combinatorial.ground_prompt(e), grounding_model, web=True))
                  for e in the_elites]
        gresults = await asyncio.gather(*[t for (_, t) in gtasks])
        _add(gresults)
        for (eid, _), res in zip(gtasks, gresults):
            if combinatorial.parse_grounding(res.get("text") or "")["grounded"]:
                survivors.append(eid)
    # grounded_survivors=None (not []) when there were no elites OR grounding was skipped (ground=False) ->
    # post_grounding_survival_rate stays honestly None (Stage-B runs grounding-OFF; it measures the archive, not survival)
    grounded = (ground and bool(the_elites))
    report = combinatorial.archive_report(archive, grounded_survivors=(survivors if grounded else None))
    return {"report": report, "archive": archive, "off_distribution_count": off_dist, "admitted": result["admitted"],
            "spent_usd": spent, "elites_grounded": survivors, "grounding_model": (grounding_model if grounded else None)}


def _common(sp) -> None:
    sp.add_argument("--pairs", nargs="+", required=True, help='domain pairs, each "DomainA:DomainB"')
    sp.add_argument("--models", type=int, default=4, help="fleet size (split into proposer != judge)")
    sp.add_argument("--n-per-pair", type=int, default=3)
    sp.add_argument("--snapshot", default=_DEFAULT_SNAPSHOT, help="N1 index snapshot dir (from smoke_n1_live build)")
    sp.add_argument("--date-cutoff", default="2026-06-24")


def main() -> None:
    ap = argparse.ArgumentParser(description="labcoat N3 combinatorial generate-judge-ground (operator).")
    sub = ap.add_subparsers(dest="mode")
    _common(sub.add_parser("estimate", help="FREE: pools + rough estimate; no paid call."))
    rp = sub.add_parser("run", help="PAID: tiny bounded combine run.")
    _common(rp)
    rp.add_argument("--tolerance", type=float, required=True, help="hard spend ceiling (USD)")
    rp.add_argument("--brain-budget", type=float, default=0.20)
    rp.add_argument("--confirm", default="", help='must equal "yes, burn it" if the estimate exceeds the R8 threshold')
    args = ap.parse_args()
    if not args.mode:
        ap.print_help(); return
    pairs = _parse_pairs(args.pairs)
    if not pairs:
        raise SystemExit('[combine] no valid --pairs (use "DomainA:DomainB")')

    nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")
    specs, _available = nuclear._pick_models(args.models)
    if len(specs) < 2:
        raise SystemExit("[combine] need >= 2 fleet models (proposer != judge); raise --models or edit nuclear._CHEAP")
    n_calls = len(pairs) * len(specs)   # very-rough lower bound for the estimate line (propose pass)
    est = spend.two_line_estimate(specs, n_agents=max(1, n_calls), is_loop_cycle=False)
    print(f"[combine] ESTIMATE (very-rough): OpenRouter ${est['openrouter_usd']} (confidence {est['confidence']}); "
          f"pairs={pairs}; fleet={[s['id'] for s in specs]}")
    if args.mode == "estimate":
        print("[combine] estimate-only; NO paid call. Re-run with `run --tolerance <usd>` to fire.")
        return
    if spend.requires_explicit_burn(est["total_usd"]) and args.confirm.strip().lower() != "yes, burn it":
        raise SystemExit(f'[combine] R8: estimate ${est["total_usd"]} exceeds the burn threshold — '
                         'pass --confirm "yes, burn it" to proceed.')

    out = asyncio.run(run_combine(pairs, tolerance=args.tolerance, model_specs=specs,
                                  brain_budget=args.brain_budget, snapshot_path=args.snapshot,
                                  date_cutoff=args.date_cutoff, n_per_pair=args.n_per_pair))
    rep = out["report"]
    surv = rep["post_grounding_survival_rate"]
    print("\n[combine] === N3 ARCHIVE REPORT (ADVISORY) ===")
    print(f"  coverage={rep['coverage']:.4f}  qd_score={rep['qd_score']:.3f} (UPPER BOUND, NOT discoveries)  "
          f"n_elites={rep['n_elites']}")
    print(f"  post_grounding_survival_rate={('%.2f' % surv) if surv is not None else 'n/a'}  "
          f"(grounded survivors={len(out['elites_grounded'])}/{rep['n_elites']}; "
          f"grounding_model={out.get('grounding_model')})")
    print(f"  off_distribution={out['off_distribution_count']} (query-calibrated out-of-corpus guard; "
          "anti-garbage, NOT a novelty signal)")
    print(f"  spent=${out['spent_usd']:.4f} (tolerance ${args.tolerance})")
    print("[combine] DONE. qd_score is an UPPER BOUND on diversity+surface-plausibility; only grounded survival is real.")


if __name__ == "__main__":
    main()
