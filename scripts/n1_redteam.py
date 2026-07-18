# scripts/n1_redteam.py
"""labcoat N1 red-team / bake-off harness — measure how an embedder separates paraphrase + jargon-inflated pairs
(want CLOSE) from unrelated pairs (want FAR), with a Jaccard baseline for contrast, across one or more embedders
(the SPECTER2-vs-SciNCL bake-off). Honest: this prints a COMPARISON table; it declares NO winner without a labeled
set. Exercises the honest limit that very short input degrades discrimination. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import n1_novelty
import novelty_gate

# (anchor, paraphrase, jargon_inflated, unrelated)
DEFAULT_FIXTURE = [
    ("transformers use self-attention to model sequences",
     "transformers rely on self-attention for sequence modeling",
     "transformer architectures leverage multi-head self-attention mechanisms for sequence-to-sequence modeling",
     "photosynthesis converts sunlight into chemical energy"),
    ("graph neural networks aggregate neighbor features",
     "GNNs combine features from neighboring nodes",
     "graph neural network message-passing aggregates latent neighbor representations",
     "the treaty was signed in the eighteenth century"),
]


def _embed_distance(embedder, a: str, b: str) -> float:
    """Distance for the ASYMMETRIC bake-off path: the anchor as a short query (adhoc_query role) vs the comparison
    as a document (proximity role) — the short-query->paper scenario, NOT the symmetric Seam-1 claim<->claim path
    (which uses role='document' for both sides via make_embedding_distance_fn)."""
    va = embedder.embed([a], role="query")[0]
    vb = embedder.embed([b], role="document")[0]
    return n1_novelty.cosine_distance(list(va), list(vb))


def run_bakeoff(embedders: dict, fixture=None) -> list:
    """embedders: {name: embedder-with-.embed}. Returns a flat table of rows
    {embedder, pair_type, distance, mean_over_cases=True}. A 'jaccard' pseudo-embedder row set is always included."""
    cases = fixture if fixture is not None else DEFAULT_FIXTURE
    pair_types = ("paraphrase", "jargon", "unrelated")

    def _pair(case, kind):
        anchor, para, jarg, unrel = case
        return (anchor, {"paraphrase": para, "jargon": jarg, "unrelated": unrel}[kind])

    table = []
    for name, emb in embedders.items():
        for kind in pair_types:
            ds = [_embed_distance(emb, *_pair(c, kind)) for c in cases]
            table.append({"embedder": name, "pair_type": kind, "distance": sum(ds) / len(ds)})
    # Jaccard baseline (the public-core floor distance) for contrast
    for kind in pair_types:
        ds = [novelty_gate.jaccard_distance(*_pair(c, kind)) for c in cases]
        table.append({"embedder": "jaccard", "pair_type": kind, "distance": sum(ds) / len(ds)})
    return table


def format_table(table) -> str:
    lines = ["embedder            pair_type    mean_distance",
             "------------------- ------------ -------------"]
    for r in table:
        lines.append(f"{r['embedder']:<19} {r['pair_type']:<12} {r['distance']:.4f}")
    return "\n".join(lines)
