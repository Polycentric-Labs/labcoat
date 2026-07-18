# scripts/n1_distance_fn.py
"""labcoat N1 Seam-1 adapter — turn a pinned embedder into a (text_a, text_b) -> [0,1] distance_fn for
novelty_gate.novelty_distance / cny. Swapping the default Jaccard for this embedding-cosine distance is what makes
the Stage-2 `tau` gate ENGAGE on paraphrase-robust distances. Within-run claim<->claim is SYMMETRIC, so role
defaults to 'document' (the general-purpose proximity adapter). LRU-cached by text. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import pathlib
import sys
from functools import lru_cache

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import n1_novelty


def make_embedding_distance_fn(embedder, *, role: str = "document", cache_size: int = 4096):
    """Return distance_fn(text_a, text_b) -> cosine_distance in [0,1] using `embedder`, LRU-cached by text."""
    @lru_cache(maxsize=cache_size)
    def _vec(text: str):
        return tuple(embedder.embed([text], role=role)[0])

    def distance_fn(a, b) -> float:
        return n1_novelty.cosine_distance(list(_vec(a)), list(_vec(b)))

    return distance_fn
