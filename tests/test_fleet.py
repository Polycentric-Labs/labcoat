# tests/test_fleet.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import fleet

def test_reasoning_models_get_min_8000_max_tokens():
    # reasoning models burn hidden tokens; <8000 truncates/zeros them (proven this session)
    assert fleet.effective_max_tokens(2200, is_reasoning=True) == 8000
    assert fleet.effective_max_tokens(12000, is_reasoning=True) == 12000
    assert fleet.effective_max_tokens(2200, is_reasoning=False) == 2200

def test_resolve_model_id_falls_back_on_known_bad_alias():
    # ~google/gemini-pro-latest 400s; fall back to a resolved id (proven this session)
    avail = ["google/gemini-2.5-pro", "openai/gpt-5.5"]
    assert fleet.resolve_model_id("~google/gemini-pro-latest", avail) == "google/gemini-2.5-pro"
    assert fleet.resolve_model_id("openai/gpt-5.5", avail) == "openai/gpt-5.5"

def test_resolve_model_id_returns_none_when_unavailable():
    assert fleet.resolve_model_id("nonexistent/model", ["openai/gpt-5.5"]) is None
    # alias recognized, but fallback target not in available -> None
    assert fleet.resolve_model_id("~google/gemini-pro-latest", ["openai/gpt-5.5"]) is None

def test_estimate_cost_uses_per_million_pricing():
    # cost = in_tokens/1e6*in_price + out_tokens/1e6*out_price
    c = fleet.estimate_cost(in_tokens=1_000_000, out_tokens=1_000_000,
                            in_price=5.0, out_price=15.0)
    assert abs(c - 20.0) < 1e-9

def test_estimate_cost_asymmetric_in_out():
    # asymmetric in/out: 500k in @ $3 + 100k out @ $15 = 1.5 + 1.5 = 3.0
    c = fleet.estimate_cost(in_tokens=500_000, out_tokens=100_000, in_price=3.0, out_price=15.0)
    assert abs(c - 3.0) < 1e-9

def test_run_fleet_calls_each_model_and_returns_structured_results(monkeypatch):
    calls = []
    def fake_call(model, prompt, max_tokens, temperature, api_key):
        calls.append(model)
        return {"text": f"answer from {model}", "in_tokens": 10, "out_tokens": 20}
    monkeypatch.setattr(fleet, "_call_one", fake_call)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    results = fleet.run_fleet(
        "Q?",
        models=[{"id": "openai/gpt-5.5", "reasoning": False, "in_price": 5.0, "out_price": 15.0}],
        available=["openai/gpt-5.5"],
    )
    assert calls == ["openai/gpt-5.5"]
    r = results[0]
    assert r["ok"] is True and "answer from" in r["text"]
    assert r["model"] == "openai/gpt-5.5" and r["cost_est"] > 0

def test_run_fleet_marks_unavailable_model_as_skipped(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    results = fleet.run_fleet("Q?", models=[{"id": "ghost/model", "reasoning": False}], available=["openai/gpt-5.5"])
    assert results[0]["ok"] is False and "unavailable" in results[0]["error"].lower()

def test_run_fleet_captures_per_model_error(monkeypatch):
    def boom(*a, **k): raise RuntimeError("timeout")
    monkeypatch.setattr(fleet, "_call_one", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert results[0]["ok"] is False and "timeout" in results[0]["error"]

def test_run_fleet_never_includes_api_key_in_results(monkeypatch):
    monkeypatch.setattr(fleet, "_call_one", lambda *a, **k: {"text": "ok", "in_tokens": 1, "out_tokens": 1})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-SECRET-DONOTLEAK")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert "SECRET-DONOTLEAK" not in repr(results)

def test_run_fleet_scrubs_api_key_from_error_message(monkeypatch):
    def leaky(model, prompt, max_tokens, temperature, api_key):
        raise RuntimeError(f"401 Unauthorized key={api_key}")
    monkeypatch.setattr(fleet, "_call_one", leaky)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-LEAKYKEY123456")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert results[0]["ok"] is False
    assert "LEAKYKEY123456" not in results[0]["error"]
    assert "LEAKYKEY123456" not in repr(results)

def test_run_fleet_scrubs_api_key_reflected_in_model_text(monkeypatch):
    # Defense-in-depth: if an upstream ever reflected the bearer token into completion text,
    # run_fleet must not pass it through verbatim. (SOUNDNESS probe, Phase 4.)
    def reflect(model, prompt, max_tokens, temperature, api_key):
        return {"text": f"you sent {api_key} as your key", "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(fleet, "_call_one", reflect)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-REFLECTEDKEY99999")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert results[0]["ok"] is True
    assert "REFLECTEDKEY99999" not in results[0]["text"]
    assert "REFLECTEDKEY99999" not in repr(results)


def test_run_fleet_no_key_set_raises_before_any_network(monkeypatch):
    # Fail-closed: missing key raises a clear RuntimeError (no key material, no network).
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])


def test_run_fleet_runs_multiple_models_and_preserves_order(monkeypatch):
    monkeypatch.setattr(fleet, "_call_one",
                        lambda model, *a, **k: {"text": f"r:{model}", "in_tokens": 1, "out_tokens": 1})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    models = [{"id": "openai/gpt-5.5", "reasoning": False},
              {"id": "google/gemini-2.5-pro", "reasoning": True}]
    results = fleet.run_fleet("Q?", models=models,
                              available=["openai/gpt-5.5", "google/gemini-2.5-pro"], parallel=True)
    assert [r["model"] for r in results] == ["openai/gpt-5.5", "google/gemini-2.5-pro"]
    assert all(r["ok"] for r in results)

def test_run_fleet_result_shape_consistent_across_branches(monkeypatch):
    def boom(*a, **k): raise RuntimeError("x")
    monkeypatch.setattr(fleet, "_call_one", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    results = fleet.run_fleet("Q?",
        models=[{"id": "ghost/model", "reasoning": False},
                {"id": "openai/gpt-5.5", "reasoning": False}],
        available=["openai/gpt-5.5"])
    expected = {"model", "ok", "text", "in_tokens", "out_tokens", "cost_est", "error"}
    for r in results:
        assert expected <= set(r.keys())


def test_call_one_posts_to_openrouter_and_parses_response(monkeypatch):
    captured = {}
    class FakeResp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "hi"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 9}}
        def raise_for_status(self): pass
    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def post(self, url, headers=None, json=None, timeout=None):
            captured["url"] = url; captured["headers"] = headers; captured["json"] = json
            return FakeResp()
    monkeypatch.setattr(fleet.httpx, "Client", FakeClient)
    out = fleet._call_one("openai/gpt-5.5", "Q?", 8000, 0.4, "sk-or-v1-KEY")
    assert out["text"] == "hi" and out["in_tokens"] == 7 and out["out_tokens"] == 9
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer sk-or-v1-KEY"
    assert captured["json"]["model"] == "openai/gpt-5.5"
    assert captured["json"]["max_tokens"] == 8000
    assert captured["json"]["temperature"] == 0.4

def test_list_models_returns_ids(monkeypatch):
    captured = {}
    class FakeResp:
        status_code = 200
        def json(self): return {"data": [{"id": "openai/gpt-5.5"}, {"id": "google/gemini-2.5-pro"}]}
        def raise_for_status(self): pass
    class FakeClient:
        def __init__(self,*a,**k): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def get(self, url, headers=None, timeout=None):
            captured["headers"] = headers
            return FakeResp()
    monkeypatch.setattr(fleet.httpx, "Client", FakeClient)
    ids = fleet.list_models("sk-or-v1-KEY")
    assert "openai/gpt-5.5" in ids and "google/gemini-2.5-pro" in ids
    assert captured["headers"]["Authorization"] == "Bearer sk-or-v1-KEY"
