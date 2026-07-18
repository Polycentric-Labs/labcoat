import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_redteam

class _StubEmbedder:
    def __init__(self, mapping):
        self._m = mapping
    def embed(self, texts, *, role="document"):
        return [self._m[t] for t in texts]

def test_run_bakeoff_table_shape_and_jaccard_column():
    anchor = "neural networks approximate functions"
    para = "neural nets approximate functions"
    jarg = "deep neural architectures approximate arbitrary functions"
    unrel = "medieval european trade routes"
    cases = [(anchor, para, jarg, unrel)]
    vecs = {anchor: [1.0, 0.0], para: [0.99, 0.14], jarg: [0.95, 0.31], unrel: [0.0, 1.0]}
    emb = {"stub": _StubEmbedder(vecs)}
    table = n1_redteam.run_bakeoff(emb, fixture=cases)
    # one row per (embedder, pair_type); pair types: paraphrase, jargon, unrelated; +1 jaccard baseline set
    kinds = {r["pair_type"] for r in table}
    assert {"paraphrase", "jargon", "unrelated"}.issubset(kinds)
    embedders = {r["embedder"] for r in table}
    assert "stub" in embedders and "jaccard" in embedders   # jaccard contrast always included
    # for the stub embedder, paraphrase distance < unrelated distance
    sd = {r["pair_type"]: r["distance"] for r in table if r["embedder"] == "stub"}
    assert sd["paraphrase"] < sd["unrelated"]
