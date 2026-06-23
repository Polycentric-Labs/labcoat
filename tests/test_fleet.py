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
    def fake_stream(model, prompt, max_tokens, temperature, api_key, *, capture_path=None, timeout=None):
        calls.append(model)
        return {"text": f"answer from {model}", "finish_reason": "stop", "in_tokens": 10, "out_tokens": 20}
    monkeypatch.setattr(fleet, "_call_one_streaming", fake_stream)
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
    monkeypatch.setattr(fleet, "_call_one_streaming", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert results[0]["ok"] is False and "timeout" in results[0]["error"]

def test_run_fleet_never_includes_api_key_in_results(monkeypatch):
    monkeypatch.setattr(fleet, "_call_one_streaming",
                        lambda *a, **k: {"text": "ok", "finish_reason": "stop", "in_tokens": 1, "out_tokens": 1})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-SECRET-DONOTLEAK")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert "SECRET-DONOTLEAK" not in repr(results)

def test_run_fleet_scrubs_api_key_from_error_message(monkeypatch):
    def leaky(*a, **k):
        api_key = a[4] if len(a) > 4 else k.get("api_key", "")
        raise RuntimeError(f"401 Unauthorized key={api_key}")
    monkeypatch.setattr(fleet, "_call_one_streaming", leaky)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-LEAKYKEY123456")
    results = fleet.run_fleet("Q?", models=[{"id": "openai/gpt-5.5", "reasoning": False}], available=["openai/gpt-5.5"])
    assert results[0]["ok"] is False
    assert "LEAKYKEY123456" not in results[0]["error"]
    assert "LEAKYKEY123456" not in repr(results)

def test_run_fleet_scrubs_api_key_reflected_in_model_text(monkeypatch):
    # Defense-in-depth: if an upstream ever reflected the bearer token into completion text,
    # run_fleet must not pass it through verbatim. (SOUNDNESS probe, Phase 4.)
    def reflect(*a, **k):
        api_key = a[4] if len(a) > 4 else ""
        return {"text": f"you sent {api_key} as your key", "finish_reason": "stop", "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(fleet, "_call_one_streaming", reflect)
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
    monkeypatch.setattr(fleet, "_call_one_streaming",
                        lambda model, *a, **k: {"text": f"r:{model}", "finish_reason": "stop", "in_tokens": 1, "out_tokens": 1})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    models = [{"id": "openai/gpt-5.5", "reasoning": False},
              {"id": "google/gemini-2.5-pro", "reasoning": True}]
    results = fleet.run_fleet("Q?", models=models,
                              available=["openai/gpt-5.5", "google/gemini-2.5-pro"], parallel=True)
    assert [r["model"] for r in results] == ["openai/gpt-5.5", "google/gemini-2.5-pro"]
    assert all(r["ok"] for r in results)

def test_run_fleet_result_shape_consistent_across_branches(monkeypatch):
    def boom(*a, **k): raise RuntimeError("x")
    monkeypatch.setattr(fleet, "_call_one_streaming", boom)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    results = fleet.run_fleet("Q?",
        models=[{"id": "ghost/model", "reasoning": False},
                {"id": "openai/gpt-5.5", "reasoning": False}],
        available=["openai/gpt-5.5"])
    expected = {"model", "ok", "text", "in_tokens", "out_tokens", "cost_est", "error"}
    for r in results:
        assert expected <= set(r.keys())


import httpx

def _status_error(code):
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return httpx.HTTPStatusError("e", request=req, response=httpx.Response(code, request=req))

def test_classify_failure_transient_cases():
    assert fleet.classify_failure(httpx.TimeoutException("t")) == "transient"
    assert fleet.classify_failure(_status_error(429)) == "transient"
    assert fleet.classify_failure(_status_error(503)) == "transient"

def test_classify_failure_deterministic_cases():
    assert fleet.classify_failure(_status_error(400)) == "deterministic"
    assert fleet.classify_failure(_status_error(403)) == "deterministic"
    assert fleet.classify_failure(_status_error(422)) == "deterministic"

def test_run_fleet_uses_streaming_retry_and_reports_completion(monkeypatch, tmp_path):
    def fake_stream(model, prompt, mt, temp, key, *, capture_path=None, timeout=None):
        if capture_path:
            with open(capture_path, "w", encoding="utf-8") as f:
                f.write("answer")
        return {"text": "answer", "finish_reason": "stop", "in_tokens": 10, "out_tokens": 20}
    monkeypatch.setattr(fleet, "_call_one_streaming", fake_stream)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    results = fleet.run_fleet("Q?", [{"id": "openai/gpt-5.2", "reasoning": False,
                              "in_price": 5.0, "out_price": 15.0}],
                              available=["openai/gpt-5.2"], capture_dir=str(tmp_path))
    r = results[0]
    assert r["ok"] is True and r["completion_status"] == "complete" and r["rerun_count"] == 1
    assert r["capture_path"] and r["cost_est"] > 0
    # the original 7 keys are still present (backward compatible)
    assert set(r) >= {"model", "ok", "text", "in_tokens", "out_tokens", "cost_est", "error"}

def test_run_fleet_marks_known_incomplete_not_ok(monkeypatch):
    monkeypatch.setattr(fleet, "_call_one_streaming",
                        lambda *a, **k: {"text": "partial", "finish_reason": "length",
                                         "in_tokens": 3, "out_tokens": 4})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    results = fleet.run_fleet("Q?", [{"id": "openai/gpt-5.2", "reasoning": False}],
                              available=["openai/gpt-5.2"], parallel=False)
    r = results[0]
    assert r["completion_status"] == "known-incomplete" and r["ok"] is False
    assert r["text"] == "partial"        # partial preserved, never silently "complete"

def test_run_with_retry_complete_on_stop():
    r = fleet.run_with_retry(lambda: {"finish_reason": "stop", "text": "ok"}, max_attempts=3)
    assert r["completion_status"] == "complete" and r["attempts"] == 1

def test_run_with_retry_reruns_transient_then_succeeds():
    seq = [httpx.TimeoutException("t"), {"finish_reason": "stop", "text": "ok"}]
    def mk():
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    r = fleet.run_with_retry(mk, max_attempts=3)
    assert r["completion_status"] == "complete" and r["attempts"] == 2

def test_run_with_retry_stops_on_deterministic_without_burning_attempts():
    def mk():
        raise _status_error(403)
    r = fleet.run_with_retry(mk, max_attempts=5)
    assert r["completion_status"] == "deterministic-fail" and r["attempts"] == 1

def test_run_with_retry_flags_known_incomplete_on_persistent_truncation():
    r = fleet.run_with_retry(lambda: {"finish_reason": "length", "text": "partial"}, max_attempts=2)
    assert r["completion_status"] == "known-incomplete" and r["attempts"] == 2
    assert r["result"]["text"] == "partial"        # partial preserved, never promoted to complete

def test_run_with_retry_stops_when_should_continue_false():
    r = fleet.run_with_retry(lambda: {"finish_reason": "length"}, max_attempts=9,
                             should_continue=lambda: False)
    assert r["completion_status"] == "known-incomplete"

def test_call_one_streaming_accumulates_parses_and_captures(monkeypatch, tmp_path):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":2}}',
        'data: [DONE]',
    ]
    class FakeStream:
        def raise_for_status(self): pass
        def iter_lines(self): return iter(lines)
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def stream(self, method, url, **k): return FakeStream()
    monkeypatch.setattr(fleet.httpx, "Client", FakeClient)
    cap = tmp_path / "q.partial"
    out = fleet._call_one_streaming("openai/gpt-5.2", "Q?", 100, 0.4, "sk-or-v1-KEY",
                                    capture_path=str(cap), timeout=600.0)
    assert out["text"] == "Hello" and out["finish_reason"] == "stop"
    assert out["in_tokens"] == 5 and out["out_tokens"] == 2
    assert cap.read_text(encoding="utf-8") == "Hello"     # captured to disk AS it streamed

def test_is_complete_only_trusts_explicit_stop():
    assert fleet.is_complete("stop") is True
    assert fleet.is_complete("end_turn") is True

def test_is_complete_rejects_truncation_and_unknown():
    assert fleet.is_complete("length") is False        # truncated -> rerun
    assert fleet.is_complete("content_filter") is False
    assert fleet.is_complete(None) is False

def test_timeout_for_model_caps_gemini_under_vertex_300s():
    assert fleet.timeout_for_model("google/gemini-2.5-pro") == 270.0
    assert fleet.timeout_for_model("google/gemini-3.1-pro-preview") == 270.0

def test_timeout_for_model_defaults_high_for_no_server_wall():
    # OpenRouter has no hard server wall (verified) -> generous client ceiling
    assert fleet.timeout_for_model("openai/gpt-5.2") == 600.0
    assert fleet.timeout_for_model("deepseek/deepseek-v3.2") == 600.0

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


# ── FIX A: missing capture_dir should be created, not cause wasted retries ──────

def test_run_fleet_creates_capture_dir_if_missing(monkeypatch, tmp_path):
    """capture_dir that doesn't exist must be created on first call (not waste retries on FileNotFoundError)."""
    def fake_stream(model, prompt, mt, temp, key, *, capture_path=None, timeout=None):
        # write to the path so the test can verify file creation too
        if capture_path:
            with open(capture_path, "w", encoding="utf-8") as f:
                f.write("answer")
        return {"text": "answer", "finish_reason": "stop", "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(fleet, "_call_one_streaming", fake_stream)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    missing_dir = str(tmp_path / "does" / "not" / "exist")
    results = fleet.run_fleet(
        "Q?",
        models=[{"id": "openai/gpt-5.5", "reasoning": False}],
        available=["openai/gpt-5.5"],
        capture_dir=missing_dir,
    )
    r = results[0]
    # Must succeed on exactly ONE attempt — no retry waste
    assert r["completion_status"] == "complete", f"expected complete, got: {r}"
    assert r["rerun_count"] == 1, f"expected 1 attempt, got: {r['rerun_count']}"
    # The directory must have been created
    import os
    assert os.path.isdir(missing_dir), "capture_dir was not created"
    # The capture file must exist
    assert r["capture_path"] is not None
    assert os.path.isfile(r["capture_path"]), "capture file was not written"


# ── FIX B: unavailable model must report completion_status=="unavailable" ────────

def test_run_fleet_unavailable_model_sets_completion_status(monkeypatch):
    """Model not in available list: ok==False AND completion_status=='unavailable'."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    results = fleet.run_fleet(
        "Q?",
        models=[{"id": "ghost/model", "reasoning": False}],
        available=["openai/gpt-5.5"],
    )
    r = results[0]
    assert r["ok"] is False
    assert r["completion_status"] == "unavailable", f"expected 'unavailable', got: {r['completion_status']!r}"


# ── FIX C: capture file must not contain raw api_key ─────────────────────────────

def test_call_one_streaming_scrubs_key_from_capture_file(monkeypatch, tmp_path):
    """If streamed content contains the api_key, the capture file must have <redacted>, not the raw key."""
    SECRET = "sk-or-v1-SECRET-INCAPTURE"
    lines = [
        f'data: {{"choices":[{{"delta":{{"content":"key={SECRET}"}}, "finish_reason":null}}]}}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}',
        'data: [DONE]',
    ]
    class FakeStream:
        def raise_for_status(self): pass
        def iter_lines(self): return iter(lines)
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def stream(self, method, url, **k): return FakeStream()
    monkeypatch.setattr(fleet.httpx, "Client", FakeClient)
    cap = tmp_path / "secret_test.partial"
    out = fleet._call_one_streaming("openai/gpt-5.5", "Q?", 100, 0.4, SECRET,
                                    capture_path=str(cap), timeout=600.0)
    file_content = cap.read_text(encoding="utf-8")
    assert SECRET not in file_content, "raw api_key found in capture file"
    assert "<redacted>" in file_content, "capture file missing <redacted>"
    # returned text must also be scrubbed (consistency with file)
    assert SECRET not in out["text"], "raw api_key found in returned text"
    assert "<redacted>" in out["text"]


# ── FIX D: run_fleet-level retry on transient error ──────────────────────────────

def test_run_fleet_retries_on_timeout_then_succeeds(monkeypatch):
    """A transient TimeoutException on attempt 1 should trigger a retry; attempt 2 succeeds -> complete + rerun_count==2."""
    import httpx as _httpx
    call_count = [0]
    def flaky_stream(model, prompt, mt, temp, key, *, capture_path=None, timeout=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise _httpx.TimeoutException("timed out")
        return {"text": "ok", "finish_reason": "stop", "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(fleet, "_call_one_streaming", flaky_stream)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    results = fleet.run_fleet(
        "Q?",
        models=[{"id": "openai/gpt-5.5", "reasoning": False}],
        available=["openai/gpt-5.5"],
        max_attempts=3,
    )
    r = results[0]
    assert r["completion_status"] == "complete", f"expected complete, got: {r['completion_status']!r}"
    assert r["rerun_count"] == 2, f"expected 2 attempts (1 fail + 1 success), got: {r['rerun_count']}"
