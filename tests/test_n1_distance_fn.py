import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_distance_fn

class _StubEmbedder:
    """Deterministic toy embedder: maps known texts to fixed unit vectors; counts embed calls (for cache test)."""
    def __init__(self):
        self.calls = 0
        self._map = {"cats are mammals": [1.0, 0.0],
                     "felines are mammals": [0.96, 0.28],   # ~paraphrase: close to the first
                     "quantum chromodynamics": [0.0, 1.0]}  # unrelated
    def embed(self, texts, *, role="document"):
        self.calls += len(list(texts))
        return [self._map[t] for t in texts]

def test_distance_fn_paraphrase_close_unrelated_far():
    emb = _StubEmbedder()
    dfn = n1_distance_fn.make_embedding_distance_fn(emb)
    d_par = dfn("cats are mammals", "felines are mammals")
    d_unrel = dfn("cats are mammals", "quantum chromodynamics")
    assert d_par < 0.1                # paraphrase -> small cosine distance
    assert d_unrel > 0.5              # unrelated -> large
    assert d_par < d_unrel

def test_distance_fn_caches_embeddings():
    emb = _StubEmbedder()
    dfn = n1_distance_fn.make_embedding_distance_fn(emb)
    dfn("cats are mammals", "felines are mammals")
    before = emb.calls
    dfn("cats are mammals", "felines are mammals")   # same texts -> served from cache
    assert emb.calls == before
