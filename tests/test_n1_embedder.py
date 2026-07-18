import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_embedder

def test_embedder_available_is_bool():
    assert isinstance(n1_embedder.n1_embedder_available(), bool)

def test_load_embedder_unknown_name_raises():
    import pytest
    with pytest.raises(ValueError):
        n1_embedder.load_embedder("not-a-real-embedder")

def test_load_embedder_without_deps_raises_clear_message():
    # On a machine without torch/transformers/adapters, loading must fail closed with an install hint.
    import pytest
    if n1_embedder.n1_embedder_available():
        pytest.skip("live embedder deps ARE installed; graceful-degrade path not exercised here")
    with pytest.raises(RuntimeError) as ei:
        n1_embedder.load_embedder("specter2")
    assert "requirements-n1.txt" in str(ei.value)

def test_fingerprint_fields_present_via_class_constants():
    # The fingerprint contract fields are class-level constants we can assert without loading the model.
    assert n1_embedder.Specter2Embedder.NAME == "allenai/specter2_base"
    assert n1_embedder.Specter2Embedder.QUERY_ADAPTER == "allenai/specter2_adhoc_query"
    assert n1_embedder.Specter2Embedder.DOC_ADAPTER == "allenai/specter2"
    assert n1_embedder.Specter2Embedder.DIM == 768
