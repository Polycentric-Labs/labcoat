# N1 OpenAlex deep-corpus runbook (operator)

A deeper, multi-field, bio/med-inclusive N1 corpus via **OpenAlex** (FREE, no API key). Complements the arXiv
snapshot (which is a shallow recency slice). The live N1 deps are OPTIONAL; the pure core + the rest of labcoat run
without them. N1 is **ADVISORY**.

## Prereqs
- `pip install -r requirements.txt` then `pip install -r requirements-n1.txt` (torch + transformers + adapters +
  faiss-cpu + numpy). OpenAlex needs no key; `httpx` is already a base dep.

## Build the deep snapshot
    $env:PYTHONIOENCODING='utf-8'
    python scripts/build_openalex_index.py --per-concept 3000 [--from-date 2018-01-01] [--mailto you@example.com]

- Resolves ~10 OpenAlex concepts (Immunology, Distributed computing, Machine learning, Artificial intelligence,
  Computer vision, Natural language processing, Neuroscience, Genetics, Statistics, Physics), **verifying each
  concept's `display_name` (fail-closed on mismatch)**, fetches `--per-concept` works each (cursor pagination,
  `has_abstract:true`, raw-JSON cache, dedupe by id across concepts), embeds docs (proximity) + titles (query),
  builds a faiss index + the query-calibrated off_distribution gate, and writes a **separate** snapshot
  `_internal/n1-openalex-snapshot` (does NOT clobber the arXiv one). `--mailto` is optional (OpenAlex polite pool);
  it is never stored — supply your own email or omit.

**Reference build (2026-06-25):** n=**24,868** unique works, dim 768, date range **2018-01-01 → 2026-05-16**, gate
(query-calibrated `off_distribution_threshold`) **0.2350**, diagnostic `corpus_loo_threshold` 0.0765.

### ⚠ The embed is long, monolithic, and not yet resumable
The ~25k-work SPECTER2 CPU embed takes ~60–75 min, prints no progress, and checkpoints nothing — and a **long-running
background task can be reaped by the harness (~10-min cap)**. Run it as a **detached OS process**, not a tool
background task:
    $env:PYTHONIOENCODING='utf-8'
    Start-Process python -ArgumentList "-u","scripts/build_openalex_index.py","--per-concept","3000" `
      -WorkingDirectory <repo> -RedirectStandardOutput build.out -RedirectStandardError build.err -WindowStyle Hidden
Then poll for `_internal/n1-openalex-snapshot/meta.json` (written only at the end). The raw-JSON fetch cache makes a
re-run skip the fetch, but the embed restarts from scratch if killed (resumable/checkpointed embed is a tracked
follow-on). Query the snapshot via `combine_live.py … --snapshot _internal/n1-openalex-snapshot`.

## What it adds (HONEST — verify-to-kill, no overclaim)
- **Immunology / bio-med coverage is now PRESENT** (the arXiv slice had none): hand-picked immunology claims find
  on-topic immunology papers at small distance (~0.14–0.15). Demonstrated on a handful of probes, **not recall-measured**.
- The **off_distribution gate is an anti-OUT-OF-CORPUS guard, NOT a novelty signal.** It provably fires on genuinely
  out-of-corpus claims (cooking / legal / sports / nonsense / a random vector all read off, 0.27–0.89 > 0.235), and
  correctly passes coherent in-corpus claims — including ones in fields the broad corpus happens to cover (e.g. a
  maritime-trade claim reads in-distribution because OpenAlex genuinely has maritime papers; that is correct, not a
  miss). The in-corpus-vs-near-OOD margin is **modest** (~0.04–0.06); the gate is **meaningful-not-strong** and
  probe-validated, not ROC-measured.
- A broader corpus correctly makes FEWER claims out-of-corpus — this reflects real coverage, **not** a stronger gate.
  Validate the gate with a held-out OOD probe set, never by adding corpus.
- N3 combine signals on the deep corpus are **off the degenerate extremes** the arXiv slice was pinned at
  (off_distribution 1/3, post-grounding survival 2/3 on one n=3 pair) — a **single-run observation, not a measured
  discrimination rate**; multi-pair / larger-n runs are required before claiming the signals discriminate.

## Honest limits / deferred
Concept coverage is **NOT balanced** — first-seen-wins dedupe keeps immunology ~100% but drops ~20–40% of the
overlapping ML-family concepts. The SciNCL bake-off is unrun (all results conditional on SPECTER2 — "A/B before
lock"). HNSW + date-rolling refresh are deferred (flat-exact is fine at this scale; the snapshot is a static slice
that ages). A committed real-data integration test + a per-record malformed-work guard + a resumable/checkpointed
embed are tracked follow-ons.
