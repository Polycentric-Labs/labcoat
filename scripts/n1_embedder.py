# scripts/n1_embedder.py
"""labcoat N1 embedder shell — the PINNED citation-aware embedder behind the N1 seam. SPECTER2 (default) uses an
ASYMMETRIC two-adapter setup: short claims/queries -> the adhoc_query adapter; corpus papers -> the proximity
adapter (AllenAI's documented short-query->paper pattern; SPECTER2 = arXiv:2211.13308). SciNCL (arXiv:2202.06671)
is the bake-off alternative. Optional deps (torch/transformers/adapters via `pip install -r requirements-n1.txt`);
the zero-dep core never imports them. License: MIT. Author: Allen Byrd.

HONEST LIMITS: very short input degrades discrimination (give as much claim text as available); the
asymmetric-vs-proximity-only choice has NO published benchmark for 1-2-sentence novelty claims -> A/B before lock;
N1 is ADVISORY. The runtime dep is the MODERN `adapters` package (not the legacy adapter-transformers fork). Pin
canonical ids; never the legacy allenai/specter2_proximity, never bare specter2_base with no adapter active."""
from __future__ import annotations

_INSTALL_HINT = "live N1 embedder requires: pip install -r requirements-n1.txt (torch, transformers, adapters)"


def n1_embedder_available() -> bool:
    """True iff the live embedder deps import. Mirrors redaction_gate.presidio_available()."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import adapters  # noqa: F401
        return True
    except Exception:
        return False


def _l2_normalize(model_output_cls, torch):
    return model_output_cls / model_output_cls.norm(dim=1, keepdim=True).clamp_min(1e-12)


class Specter2Embedder:
    """Pinned SPECTER2 (base + two adapters). embed(texts, role) -> L2-normalized CLS vectors."""
    NAME = "allenai/specter2_base"
    QUERY_ADAPTER = "allenai/specter2_adhoc_query"
    DOC_ADAPTER = "allenai/specter2"           # proximity (current canonical id; NOT the legacy *_proximity)
    DIM = 768

    def __init__(self, *, revision=None, proximity_only: bool = False):
        if not n1_embedder_available():
            raise RuntimeError(_INSTALL_HINT)
        import torch
        from transformers import AutoTokenizer
        from adapters import AutoAdapterModel
        self._torch = torch
        self._revision = revision
        self._proximity_only = bool(proximity_only)
        self._tok = AutoTokenizer.from_pretrained(self.NAME, revision=revision)
        self._model = AutoAdapterModel.from_pretrained(self.NAME, revision=revision)
        self._model.load_adapter(self.QUERY_ADAPTER, source="hf", load_as="query", set_active=False)
        # Activate proximity as the default adapter (so direct model use is never bare-base); embed() still
        # switches per role. NB: the adapters lib emits a benign "none are activated for the forward pass"
        # load-time notice during model construction (before this line) — VERIFIED harmless: each embed() call
        # activates the role-correct adapter, and query vs document roles produce distinct (adapter-applied) vectors.
        self._model.load_adapter(self.DOC_ADAPTER, source="hf", load_as="document", set_active=True)
        self._model.train(False)  # inference mode (no dropout / no grad-tracking side effects)

    def embed(self, texts, *, role: str = "document", batch_size: int = 32):
        adapter = "document" if (self._proximity_only or role == "document") else "query"
        self._model.set_active_adapters(adapter)
        texts = list(texts)
        vecs = []
        for i in range(0, len(texts), batch_size):   # mini-batch so a few-thousand-doc corpus fits CPU memory
            enc = self._tok(texts[i:i + batch_size], padding=True, truncation=True, return_tensors="pt",
                            return_token_type_ids=False, max_length=512)
            with self._torch.no_grad():
                out = self._model(**enc)
            cls = out.last_hidden_state[:, 0, :]
            vecs.extend(_l2_normalize(cls, self._torch).tolist())
        return vecs

    def fingerprint(self) -> dict:
        return {"name": self.NAME,
                "query_adapter": self.DOC_ADAPTER if self._proximity_only else self.QUERY_ADAPTER,
                "doc_adapter": self.DOC_ADAPTER, "revision": self._revision,
                "dim": self.DIM, "normalize": "l2", "metric": "cosine"}


class ScinclEmbedder:
    """SciNCL (single model, no role distinction) for the bake-off. embed(texts, role) -> L2-normalized CLS."""
    NAME = "malteos/scincl"
    DIM = 768

    def __init__(self, *, revision=None):
        if not n1_embedder_available():
            raise RuntimeError(_INSTALL_HINT)
        import torch
        from transformers import AutoTokenizer, AutoModel
        self._torch = torch
        self._revision = revision
        self._tok = AutoTokenizer.from_pretrained(self.NAME, revision=revision)
        self._model = AutoModel.from_pretrained(self.NAME, revision=revision)
        self._model.train(False)  # inference mode

    def embed(self, texts, *, role: str = "document", batch_size: int = 32):
        texts = list(texts)
        vecs = []
        for i in range(0, len(texts), batch_size):   # mini-batch so a few-thousand-doc corpus fits CPU memory
            enc = self._tok(texts[i:i + batch_size], padding=True, truncation=True, return_tensors="pt",
                            return_token_type_ids=False, max_length=512)
            with self._torch.no_grad():
                out = self._model(**enc)
            cls = out.last_hidden_state[:, 0, :]
            vecs.extend(_l2_normalize(cls, self._torch).tolist())
        return vecs

    def fingerprint(self) -> dict:
        return {"name": self.NAME, "query_adapter": self.NAME, "doc_adapter": self.NAME,
                "revision": self._revision, "dim": self.DIM, "normalize": "l2", "metric": "cosine"}


def load_embedder(name: str = "specter2", *, revision=None, proximity_only: bool = False):
    """Factory: 'specter2' (default, asymmetric) or 'scincl' (bake-off). Raises ValueError on unknown name and
    RuntimeError (with the install hint) when the live deps are absent."""
    if name == "specter2":
        return Specter2Embedder(revision=revision, proximity_only=proximity_only)
    if name == "scincl":
        return ScinclEmbedder(revision=revision)
    raise ValueError(f"unknown embedder: {name!r} (expected 'specter2' or 'scincl')")
