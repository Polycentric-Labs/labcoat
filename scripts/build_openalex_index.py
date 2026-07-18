# scripts/build_openalex_index.py
"""labcoat N1 OpenAlex deep-corpus build (operator) — NOT unit-tested; downloads SPECTER2 + builds a faiss snapshot
over ~10 OpenAlex concepts. OpenAlex is FREE (no key). Writes a SEPARATE snapshot (does NOT clobber the arXiv one).
Usage:
  $env:PYTHONIOENCODING='utf-8'
  python scripts/build_openalex_index.py [--per-concept 2500] [--from-date 2018-01-01] [--mailto you@example.com]
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import n1_embedder
import n1_index
import n1_build
import n1_corpus_openalex as oa

_SNAPSHOT = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-openalex-snapshot"
_CACHE = pathlib.Path(__file__).resolve().parent.parent / "_internal" / "n1-openalex-cache"
_CONCEPTS = ["Immunology", "Distributed computing", "Machine learning", "Artificial intelligence",
             "Computer vision", "Natural language processing", "Neuroscience", "Genetics", "Statistics", "Physics"]


def main():
    ap = argparse.ArgumentParser(description="Build the OpenAlex deep N1 snapshot.")
    ap.add_argument("--per-concept", type=int, default=2500)
    ap.add_argument("--from-date", default="2018-01-01")
    ap.add_argument("--mailto", default="", help="optional OpenAlex polite-pool email (operator-supplied; not stored)")
    ap.add_argument("--snapshot", default=str(_SNAPSHOT))
    ap.add_argument("--concepts", nargs="+", default=_CONCEPTS)
    args = ap.parse_args()
    if not n1_embedder.n1_embedder_available() or not n1_index.n1_index_available():
        raise SystemExit("missing live deps — run: pip install -r requirements-n1.txt")
    emb = n1_embedder.load_embedder("specter2")
    resolved = oa.resolve_concepts(args.concepts, mailto=args.mailto)
    print("[openalex] resolved concepts:", {r["name"]: r["id"] for r in resolved})
    recs = oa.fetch_openalex([r["id"] for r in resolved], per_concept=args.per_concept, cache_dir=str(_CACHE),
                             mailto=args.mailto, from_date=args.from_date)
    print(f"[openalex] fetched {len(recs)} unique works across {len(resolved)} concepts (deduped)")
    n, corpus_loo, gate = n1_build.build_and_save_index(recs, embedder=emb, snapshot_path=args.snapshot)
    _fmt = lambda x: f"{x:.4f}" if x is not None else "None"
    print(f"[openalex] built faiss index n={n} dim={emb.DIM} corpus_loo_threshold={_fmt(corpus_loo)} "
          f"query_calibrated_gate_threshold={_fmt(gate)} -> snapshot {args.snapshot}")


if __name__ == "__main__":
    main()
