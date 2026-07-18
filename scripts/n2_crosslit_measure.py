"""labcoat N2 Phase 3 — the Swanson known-answer measurement. PURE measure_case (builds the answer-blind pipeline,
scores the target vs injected hard-negatives + the empirical distractor↔distractor null, returns a VOID/KILL/PASS
verdict) under a chosen priority. Both cases x both priorities driven by the _internal operator run. FREE. License: MIT."""
from __future__ import annotations
import itertools
import math
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gap_channels as gc
import n2_crosslit as nx


def _nonhub_degrees(edges, hub) -> dict:
    """deg(X) = number of distinct non-hub bridge-neighbours of X. Pure."""
    hubs = set(hub or ())
    adj = {}
    for e in (edges or []):
        if not (isinstance(e, (list, tuple)) and len(e) >= 2):
            continue
        a, b = str(e[0]).strip(), str(e[1]).strip()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    degrees = {}
    for c, nbrs in adj.items():
        degrees[c] = len({n for n in nbrs if n not in hubs})
    return degrees


def measure_case(records_by_topic, target_a_terms, target_c_terms, distractor_topics, hardneg_topic_pairs,
                 topic_anchor_terms, *, priority="raw", hub_percentile=0.90, min_pool=30, null_pct=95.0,
                 max_edges=200000, min_support=3, alpha=0.01, hub_override=None, return_internals=False, max_gaps=100000) -> dict:
    """Answer-blind Swanson measurement under a chosen priority. max_edges MUST match run_pipeline (200000) so the
    real headline graph is NOT silently truncated at the 2000 default. priority in {"raw","specificity",
    "association_strength","salton_cosine"}. For association_strength, gaps are additionally gated by a
    hypergeometric significance test (min_support, alpha) BEFORE target/null/verdict scoring; ranking stays by AS
    effect size, never by p-value. Pure."""
    cl, ids, topic = nx.build_concept_inputs(records_by_topic)
    edges = gc.cooccurrence_edges_from_concepts(cl, max_edges=max_edges)
    prov = gc.cooccurrence_provenance(cl, ids)
    hub = gc.topic_aware_hub_bridges(edges, nx.topic_degree_map(cl, ids, topic), percentile=hub_percentile)
    if hub_override is not None:
        hub = frozenset(hub_override)   # target-neutral: lets C3 run with NO hub exclusion (percentile cannot reach ∅)
    nconc = len({c for l in cl for c in l})
    nonhub_degrees = _nonhub_degrees(edges, hub)
    hubs_set = set(hub or ())
    nc = sum(1 for c in nonhub_degrees if c not in hubs_set)
    if priority == "association_strength":
        sfn = gc.association_strength_fn(nonhub_degrees)
    elif priority == "salton_cosine":
        sfn = gc.salton_cosine_fn(nonhub_degrees)
    elif priority == "specificity":
        sfn = gc.specificity_strength_fn(gc.concept_degrees(edges), nconc)
    else:
        sfn = None
    # AS/cosine produce FRACTIONAL strengths (<1); the ranker's default integer min_strength=1 would filter them all
    # out. Use min_strength=0 for those (the hypergeometric gate below is AS's real floor; cosine keeps all gaps).
    _mins = 0 if priority in ("association_strength", "salton_cosine") else 1
    ranked = gc.cross_paper_gaps_ranked(edges, prov, hub_bridges=hub, strength_fn=sfn, min_strength=_mins, max_gaps=int(max_gaps))
    if priority == "association_strength":
        gated = []
        for g in ranked:
            c_ac = gc.pair_bridge_count(g, prov, hub_bridges=hub)
            if c_ac < int(min_support):
                continue
            deg_a = nonhub_degrees.get(g.get("a"), 0)
            deg_c = nonhub_degrees.get(g.get("c"), 0)
            if gc.hypergeom_sf(c_ac, nc, deg_a, deg_c) < alpha:
                gated.append(g)
        ranked = gated
    target = gc.pair_rank(ranked, target_a_terms, target_c_terms)
    # empirical null = ALL distractor<->distractor pair strengths (a pair surfacing NO gap is a true-negative
    # competitor at strength 0.0, not dropped); hard-negatives = the named subset, likewise 0.0 if no gap. Frozen
    # pre-run so absent pairs are counted answer-blind.
    dist_terms = {t: topic_anchor_terms[t] for t in distractor_topics if t in topic_anchor_terms}
    null_map = gc.pool_pair_strengths(ranked, dist_terms)
    dist_list = list(dist_terms)
    null_strengths = [null_map.get(frozenset({a, b}), 0.0) for a, b in itertools.combinations(dist_list, 2)]
    hardneg_strengths = [null_map.get(frozenset({x, y}), 0.0) for (x, y) in hardneg_topic_pairs]
    verdict = gc.crosslit_verdict(target, hardneg_strengths, null_strengths,
                                  pool_size=len(ranked), min_pool=min_pool, null_pct=null_pct)
    hub_deg_q = gc._percentile(list(nonhub_degrees.values()), 90.0) or 0.0
    target_hub_share, pmi_of_target, target_c_ac, target_hypergeom_p = None, None, None, None
    if target is not None:
        target_gap = next((g for g in ranked if g.get("a") == target.get("a") and g.get("c") == target.get("c")),
                          None)
        if target_gap is not None:
            target_hub_share = gc.hub_share_fraction(target_gap, prov, nonhub_degrees, hub_bridges=hub,
                                                      hub_degree_quantile_value=hub_deg_q)
            asv = float(target["strength"])
            pmi_of_target = math.log2(asv * nc) if asv > 0 and nc > 0 else None
            target_c_ac = gc.pair_bridge_count(target_gap, prov, hub_bridges=hub)
            target_hypergeom_p = gc.hypergeom_sf(target_c_ac, nc, nonhub_degrees.get(target.get("a"), 0),
                                                 nonhub_degrees.get(target.get("c"), 0))
    result = {"priority": priority, "target": target, "verdict": verdict, "n_gaps": len(ranked),
              "n_hub": len(hub), "n_null": len(null_strengths), "n_hardneg": len(hardneg_strengths),
              "n_concepts": nconc, "n_edges": len(edges), "target_hub_share": target_hub_share,
              "pmi_of_target": pmi_of_target, "target_c_ac": target_c_ac, "target_hypergeom_p": target_hypergeom_p}
    if return_internals:
        result["_internals"] = {"ranked": ranked, "prov": prov, "hub": hub, "nonhub_degrees": nonhub_degrees,
                                "nc": nc, "hub_deg_q": hub_deg_q}
    return result
