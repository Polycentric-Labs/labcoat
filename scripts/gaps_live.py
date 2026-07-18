# scripts/gaps_live.py
"""Operator entrypoint for N2 — the gap/whitespace channels over a real arXiv corpus. FREE (local: stdlib
extraction + FREE PPMI-context relatedness + free arXiv; NO OpenRouter / NO Console spend for the stdlib path).
Builds the deferred concept-graph/claim-extraction adapter from text, fuses the ABC channel with PPMI-context
concept relatedness + hub-degree bridge exclusion, and prints the reconciled, evidentiary-status-tagged gap
candidates (the loop_evolution feed). N2 is ADVISORY.

Pipeline: fetch corpus -> stdlib or LLM extract (cooccurrence edges + claims) ->
  abc_whitespace[PPMI relatedness + hub_bridge_threshold] + mine_future_work + find_contradictions
  -> reconcile_channels -> to_next_question_candidates.

HONEST FINDING (2026-06-26 dense-corpus characterization; fixed 2026-06-26): the ABC whitespace channel was
NOISE-DOMINATED via TWO compounding failures: (1) HUB-FLOOD — the corpus topic-term co-occurs with everything,
becoming the trivial bridge B that floods spurious gaps; (2) INERT SPECTER2 relatedness — SPECTER2 (paper-
similarity model) gave ~uniform 0.86-0.95 to ALL short concept terms, so no threshold discriminated. FIXED via:
(1) hub_bridge_threshold — drops bridges whose degree exceeds the 90th-percentile degree cap (Swanson B-term
exclusion); (2) pmi_context_relatedness — PPMI-context distributional cosine (Church-Hanks 1990) replaces
SPECTER2 for concept-concept relatedness (correct tool: short terms need distributional context, not paper
embeddings). SPECTER2 stays for N1 novelty scoring (correct there: paper-to-paper distance). The future-work +
CONTRADICTION channels remain the more reliable N2 signals; treat ABC `whitespace` output as ADVISORY until
re-characterization smoke confirms noise reduction.

Usage:
  python scripts/gaps_live.py gaps --query "cat:cs.LG" --n 200 [--min-relatedness 0.30]
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gap_channels
import n1_corpus
import n2_extract_llm

_CACHE = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-corpus-cache"


def run_gaps(query, *, max_results, cache_dir, min_relatedness=0.30, max_terms_per_doc=12, max_gaps=500,
             llm=False, brain_fn=None) -> dict:
    """Run the full N2 pipeline over an arXiv corpus. FREE (local) unless llm=True (LLM extraction path).
    When llm=True, concept_lists + claims come from n2_extract_llm (brain_fn required); otherwise uses the stdlib
    path. Uses FREE PPMI-context relatedness + hub-degree bridge exclusion for the ABC channel (no SPECTER2 for
    concepts). Returns the channel counts + candidates + extractor metadata."""
    recs = n1_corpus.fetch_arxiv(query, max_results=max_results, cache_dir=str(cache_dir))
    texts = [f"{r.get('title', '')}. {r.get('abstract', '')}" for r in recs]
    if llm and brain_fn is not None:
        concept_lists, claims = n2_extract_llm.extract_llm(recs, brain_fn=brain_fn)
        extractor = "llm"
    else:
        concept_lists = [gap_channels.extract_concepts(t, max_terms=max_terms_per_doc) for t in texts]
        claims = [c for t in texts for c in gap_channels.extract_claims(t)]
        extractor = "stdlib"
    edges = gap_channels.cooccurrence_edges_from_concepts(concept_lists)
    # N2-ABC fix: FREE PPMI-context concept relatedness (Church-Hanks) + hub-degree bridge exclusion (Swanson).
    # SPECTER2 is the WRONG tool for short concept terms (uniform ~0.9) -> dropped here (it stays for N1/3a).
    rel = gap_channels.pmi_context_relatedness(concept_lists)
    hub_thr = gap_channels.hub_bridge_threshold(edges)
    structural_unfiltered = gap_channels.abc_whitespace(edges, max_candidates=max_gaps)
    structural = gap_channels.abc_whitespace(edges, relatedness_fn=rel, min_relatedness=min_relatedness,
                                             max_candidates=max_gaps, max_bridge_degree=hub_thr)
    fw = [s for t in texts for s in gap_channels.mine_future_work(t)]
    contradictions = gap_channels.find_contradictions(claims)
    reconciled = gap_channels.reconcile_channels(structural=structural, future_work=fw,
                                                 contradictions=contradictions)
    candidates = gap_channels.to_next_question_candidates(reconciled)
    by_status = {}
    for g in reconciled:
        st = g.get("evidentiary_status", "?")
        by_status[st] = by_status.get(st, 0) + 1
    return {"n_docs": len(texts), "n_concept_edges": len(edges),
            "n_structural_filtered": len(structural), "n_structural_unfiltered": len(structural_unfiltered),
            "n_future_work": len(fw), "n_contradictions": len(contradictions),
            "by_status": by_status, "candidates": candidates, "n1_used": False,
            "hub_threshold": hub_thr, "extractor": extractor}


def main() -> None:
    ap = argparse.ArgumentParser(description="labcoat N2 gap/whitespace channels over arXiv (FREE; local).")
    sub = ap.add_subparsers(dest="mode")
    gp = sub.add_parser("gaps", help="run the N2 pipeline over an arXiv corpus and print gap candidates")
    gp.add_argument("--query", default="cat:cs.LG")
    gp.add_argument("--n", type=int, default=200)
    gp.add_argument("--min-relatedness", type=float, default=0.30)
    gp.add_argument("--max-gaps", type=int, default=500,
                    help="cap on structural gap candidates (also the filtered-vs-unfiltered comparison size)")
    gp.add_argument("--llm", action="store_true",
                    help="use LLM-tagged extraction (concepts+claims+context; costs ~$0.01-0.10 via OpenRouter). "
                         "Default (no flag): FREE stdlib path unchanged.")
    args = ap.parse_args()
    if args.mode != "gaps":
        ap.print_help(); return

    brain_fn = None
    spend_usd = 0.0
    if args.llm:
        import nuclear as _nuclear
        _nuclear._load_env_key("OPENROUTER_API_KEY", "openrouter.env")
        specs, _ = _nuclear._pick_models(1)
        model = specs[0]["id"]
        est_per_doc = 0.0003   # rough: ~300 tokens in + 150 out at cheap-model rates
        est_total = est_per_doc * args.n
        print(f"[gaps --llm] extractor=LLM model={model} n={args.n} "
              f"spend_estimate≈${est_total:.3f} (rough; actual billed after run)")
        print(f"[gaps --llm] NOTE: --min-relatedness={args.min_relatedness} is the PRECISION LEVER "
              f"(Peng et al. PMC6481912: higher threshold → fewer but higher-precision structural gaps). "
              f"Try 0.2–0.5 to tune filtered-vs-unfiltered ratio.")

        def brain_fn(prompt):
            nonlocal spend_usd
            result = _nuclear._run_brain_openrouter(prompt, model=model, web=False, max_tokens=512, temperature=0.1)
            spend_usd += result.get("cost_usd") or 0.0
            if result.get("is_error"):
                return ""
            return result.get("text") or ""

    out = run_gaps(args.query, max_results=args.n, cache_dir=_CACHE, min_relatedness=args.min_relatedness,
                   max_gaps=args.max_gaps, llm=args.llm, brain_fn=brain_fn)

    extractor_note = f"extractor={out['extractor']}"
    if args.llm:
        extractor_note += f" spend=${spend_usd:.4f}"
    print(f"[gaps] docs={out['n_docs']} concept_edges={out['n_concept_edges']} "
          f"structural_gaps: {out['n_structural_filtered']} (PPMI-filtered, min_rel={args.min_relatedness}, "
          f"hub_thr={out['hub_threshold']}) vs {out['n_structural_unfiltered']} (unfiltered) | {extractor_note}")
    print(f"[gaps] future_work={out['n_future_work']} contradictions={out['n_contradictions']} "
          f"by_status={out['by_status']}")
    cand_note = "ADVISORY; stdlib extraction is crude" if out['extractor'] == "stdlib" else "ADVISORY; LLM extraction (verbatim+context grounded)"
    print(f"[gaps] {len(out['candidates'])} next-question candidates ({cand_note}):")
    for c in out["candidates"][:15]:
        print(f"  - [{c['kind']}] {c['text']}")
    if out['extractor'] == "stdlib":
        print("[gaps] DONE. stdlib path is FREE; run with --llm for LLM-tagged concepts+claims+context (costs ~$0.01-0.10). "
              "--min-relatedness is the ABC precision lever.")
    else:
        print(f"[gaps] DONE. LLM path: actual spend=${spend_usd:.4f}. "
              f"Tune --min-relatedness (current={args.min_relatedness}) to adjust filtered gap count.")


if __name__ == "__main__":
    main()
