# scripts/n1_build.py
"""labcoat N1 build helper (SHELL) — the SHARED embed->build->calibrate->save flow used by BOTH the arXiv
(smoke_n1_live) and OpenAlex (build_openalex_index) builds, so the doc/title-query calibration lives in ONE place.
Source-agnostic: any [{id,title,abstract,date}] records. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import n1_corpus
import n1_index


def build_and_save_index(records, *, embedder, snapshot_path):
    """Embed records (proximity docs + query titles), build the faiss index, compute the query-calibrated gate
    threshold, and save the snapshot. Returns (n, corpus_loo_threshold, gate_threshold). Shell."""
    texts = [n1_corpus.embed_text(r) for r in records]
    vecs = embedder.embed(texts, role="document")
    entries = [{"id": r["id"], "title": r["title"], "date": r["date"], "vec": v}
               for r, v in zip(records, vecs)]
    idx = n1_index.build_index(entries, embedder_fingerprint=embedder.fingerprint())
    # QUERY-regime off-distribution calibration: corpus TITLES embedded with the QUERY adapter are the
    # in-distribution reference (closest proxy to real 1-2 sentence claim queries). The gate threshold is the
    # 95th pct of {title-query -> nearest OTHER corpus doc} distances; corpus->corpus LOO mis-calibrates the gate
    # (it fires for every query) — see the N1 off_distribution finding. Do NOT switch titles->document here.
    qvecs = embedder.embed([r["title"] for r in records], role="query")
    gate_thr = idx.query_calibrated_threshold(qvecs, [r["id"] for r in records])
    corpus_loo = n1_index.save_snapshot(idx, snapshot_path, gate_threshold=gate_thr)
    return len(entries), corpus_loo, gate_thr
