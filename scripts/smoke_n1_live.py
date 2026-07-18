# scripts/smoke_n1_live.py
"""labcoat N1 LIVE smoke — NOT unit-tested; downloads SPECTER2 + builds a real faiss index over a small arXiv
corpus. Run AFTER `pip install -r requirements-n1.txt`.

  build : fetch a small arXiv corpus -> embed (proximity) -> build + save a faiss snapshot.
  query : load the snapshot -> embed a claim (adhoc_query) -> external_novelty_capped + cited nearest prior work,
          + the Seam-1 paraphrase-vs-unrelated demo, + the FaissN1Index-vs-InMemoryN1Index oracle agreement.

Usage:
  $env:PYTHONIOENCODING='utf-8'
  python scripts/smoke_n1_live.py build --query "cat:cs.LG" --n 1500
  python scripts/smoke_n1_live.py query --claim "A relative neighbor density metric scores idea novelty."
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import n1_novelty
import n1_embedder
import n1_corpus
import n1_index
import n1_build

_SNAPSHOT = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-index-snapshot"
_CACHE = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-corpus-cache"
_CUTOFF = "2026-06-24"   # date cutoff for the temporal-leakage guard (neighbors must predate this)


def _require_deps():
    if not n1_embedder.n1_embedder_available():
        raise SystemExit("missing embedder deps — run: pip install -r requirements-n1.txt")
    if not n1_index.n1_index_available():
        raise SystemExit("missing faiss/numpy — run: pip install -r requirements-n1.txt")


def cmd_build(args):
    _require_deps()
    emb = n1_embedder.load_embedder("specter2")
    recs = n1_corpus.fetch_arxiv(args.query, max_results=args.n, cache_dir=str(_CACHE))
    print(f"[smoke] fetched {len(recs)} arXiv records for {args.query!r}")
    n, corpus_loo, gate_thr = n1_build.build_and_save_index(recs, embedder=emb, snapshot_path=str(_SNAPSHOT))
    _fmt = lambda x: f"{x:.4f}" if x is not None else "None"
    print(f"[smoke] built faiss index n={n} dim={emb.DIM} "
          f"corpus_loo_threshold={_fmt(corpus_loo)} query_calibrated_gate_threshold={_fmt(gate_thr)} "
          f"-> snapshot {_SNAPSHOT}")


def cmd_query(args):
    _require_deps()
    emb = n1_embedder.load_embedder("specter2")
    idx = n1_index.load_snapshot(str(_SNAPSHOT), active_fingerprint=emb.fingerprint())  # fail-closed on drift
    thr = idx._loaded_threshold
    qvec = emb.embed([args.claim], role="query")[0]                 # claim = adhoc_query adapter
    res = n1_novelty.external_novelty_capped(qvec, idx, k=10, date_cutoff=_CUTOFF,
                                             off_distribution_threshold=thr)
    print(f"[smoke] claim: {args.claim!r}")
    print(f"[smoke] N1 external novelty (vs arXiv as of {_CUTOFF}) = {res['score']:.3f}  "
          f"off_distribution={res['off_distribution']} ({res['reason']})")
    if res["nearest"]:
        print(f"[smoke] nearest prior work: arXiv:{res['nearest']['id']} "
              f"d={res['nearest']['distance']:.3f} — {res['nearest']['title']}")

    # Seam-1 demo: paraphrase vs unrelated, embedding vs Jaccard
    import n1_distance_fn, novelty_gate
    dfn = n1_distance_fn.make_embedding_distance_fn(emb)
    para = "A relative-density measure scores how novel a research idea is."
    unrel = "Tariff schedules shaped nineteenth-century maritime trade."
    print(f"[smoke] Seam-1 embedding distance  paraphrase={dfn(args.claim, para):.3f}  "
          f"unrelated={dfn(args.claim, unrel):.3f}")
    print(f"[smoke] Seam-1 Jaccard   distance  paraphrase={novelty_gate.jaccard_distance(args.claim, para):.3f}  "
          f"unrelated={novelty_gate.jaccard_distance(args.claim, unrel):.3f}  (embedding should separate better)")

    # Oracle: FaissN1Index vs pure InMemoryN1Index on the SAME vectors/dates
    import numpy as np
    entries = [{"id": idx._ids[i], "title": idx._titles[i], "date": idx._dates[i],
                "vec": [float(x) for x in idx._x[i]]} for i in range(idx._x.shape[0])]
    mem = n1_novelty.InMemoryN1Index(entries, distance_fn=n1_novelty.cosine_distance)
    mem_res = n1_novelty.external_novelty_capped(qvec, mem, k=10, date_cutoff=_CUTOFF,
                                                 off_distribution_threshold=thr)
    nearest_match = (res["nearest"] is not None and mem_res["nearest"] is not None
                     and mem_res["nearest"]["id"] == res["nearest"]["id"])
    agree = abs(mem_res["score"] - res["score"]) < 1e-6 and nearest_match
    print(f"[smoke] ORACLE faiss-vs-InMemory: score_faiss={res['score']:.6f} score_mem={mem_res['score']:.6f} "
          f"nearest_match={nearest_match} -> {'OK' if agree else 'MISMATCH'}")
    print("[smoke] DONE.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--query", default="cat:cs.LG"); b.add_argument("--n", type=int, default=1500)
    q = sub.add_parser("query"); q.add_argument("--claim", required=True)
    args = ap.parse_args()
    (cmd_build if args.cmd == "build" else cmd_query)(args)


if __name__ == "__main__":
    main()
