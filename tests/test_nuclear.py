import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pytest
import nuclear


@pytest.mark.asyncio
async def test_run_brain_degrades_gracefully_on_sdk_exception(monkeypatch):
    """A brain-call failure (budget cap / API / transport error) must DEGRADE — keep any partial text, flag the
    error, and pessimistically count the per-call cap as spent (never under-count) — NOT crash the run."""
    async def _boom(*args, **kwargs):
        raise RuntimeError("Reached maximum budget ($0.5)")
        yield  # noqa — makes this an async generator (unreachable)

    monkeypatch.setattr(nuclear.sdk, "query", _boom)
    out = await nuclear._run_brain("hi", model="m", max_budget_usd=0.5, max_turns=1)
    assert out["is_error"] is True
    assert "budget" in out["error"].lower()
    assert out["cost_usd"] == 0.5   # pessimistic: assume up to the cap was spent
    assert out["text"] == ""        # no partial text here; the caller's defensive parsers handle empty


def test_scrub_removes_loaded_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRETVALUE123456")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-SECRETVALUE123456")
    msg = "error with sk-ant-SECRETVALUE123456 and sk-or-v1-SECRETVALUE123456"
    out = nuclear._scrub(msg)
    assert "SECRETVALUE" not in out and out.count("<redacted>") == 2


def test_scrub_noop_when_no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert nuclear._scrub("plain message") == "plain message"
    assert nuclear._scrub(None) is None


import types

def test_extract_rate_limit_throttled_and_healthy_and_none():
    info = types.SimpleNamespace(status="rejected", utilization=1.0, resets_at=None)
    msg = types.SimpleNamespace(rate_limit=info)
    out = nuclear._extract_rate_limit(msg)
    assert out["status"] == "rejected" and out["utilization"] == 1.0
    none_msg = types.SimpleNamespace(rate_limit=types.SimpleNamespace(status=None, utilization=None, resets_at=None))
    assert nuclear._extract_rate_limit(none_msg) is None

def test_status_int_coercions():
    assert nuclear._status_int(429) == 429
    assert nuclear._status_int("429") == 429
    assert nuclear._status_int(types.SimpleNamespace(status_code=402)) == 402
    assert nuclear._status_int(None) is None

def test_gather_findings_reads_complete_rows_excluding_verify(tmp_path):
    import audit
    led = str(tmp_path / "L.jsonl")
    audit.append_ledger(led, audit.make_ledger_record(timestamp="t", loop_id="L1", query_id="s1::m",
        sub_question="is X novel?", model="m", redaction_applied=True, raw_capture_path=None,
        completion_status="complete"))
    audit.append_ledger(led, audit.make_ledger_record(timestamp="t", loop_id="L1", query_id="L1::verify",
        sub_question="is X novel?", model="brain", redaction_applied=True, raw_capture_path=None,
        completion_status="complete", validation_verdict="confirmed", claim_text="c"))
    out = nuclear._gather_findings(led, "L1")
    assert "is X novel?" in out and "::verify" not in out


def test_brain_spec_presets_and_override():
    assert nuclear.brain_spec("sdk")["transport"] == "sdk"
    s = nuclear.brain_spec("or-claude-strong")
    assert s["transport"] == "openrouter" and s["model"].startswith("anthropic/")
    assert nuclear.brain_spec("or-open")["transport"] == "openrouter"
    # --brain-model override wins, transport stays the preset's
    o = nuclear.brain_spec("or-claude-cheap", "anthropic/claude-3.5-haiku")
    assert o["transport"] == "openrouter" and o["model"] == "anthropic/claude-3.5-haiku"
    import pytest as _pytest
    with _pytest.raises(ValueError):
        nuclear.brain_spec("bogus")


def test_run_brain_openrouter_web_online_cost_and_degrade(monkeypatch):
    import httpx
    captured = {}
    class _Resp:
        def __init__(self, payload): self._p = payload
        def raise_for_status(self): pass
        def json(self): return self._p
    class _FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None, timeout=None):
            captured["model"] = json["model"]
            return _Resp({"choices": [{"message": {"content": "BRAIN OUT"}}], "usage": {"cost": 0.012}})
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-TESTKEY1234567890")
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    out = nuclear._run_brain_openrouter("hi", model="anthropic/claude-opus-4.1", web=True)
    assert captured["model"] == "anthropic/claude-opus-4.1:online"   # web -> :online plugin
    assert out["text"] == "BRAIN OUT" and out["cost_usd"] == 0.012 and out["is_error"] is False
    # non-web omits :online
    out2 = nuclear._run_brain_openrouter("hi", model="x/y", web=False)
    assert captured["model"] == "x/y"
    # degrade on exception (no crash; scrubbed error; is_error True)
    class _BoomClient(_FakeClient):
        def post(self, *a, **k): raise RuntimeError("boom")
    monkeypatch.setattr(httpx, "Client", _BoomClient)
    out3 = nuclear._run_brain_openrouter("hi", model="x/y")
    assert out3["is_error"] is True and out3["text"] == "" and "boom" in out3["error"]


@pytest.mark.asyncio
async def test_brain_dispatch_routes_sdk_and_openrouter(monkeypatch):
    calls = {}
    async def _fake_sdk(prompt, *, model, max_budget_usd, max_turns, allowed_tools=None, cwd=None):
        calls["sdk"] = {"model": model, "allowed_tools": allowed_tools}
        return {"text": "SDK", "cost_usd": 0.0, "api_error_status": None, "is_error": False,
                "rate_limit": None, "error": None}
    def _fake_or(prompt, *, model, web=False, **k):
        calls["or"] = {"model": model, "web": web}
        return {"text": "OR", "cost_usd": 0.0, "api_error_status": None, "is_error": False,
                "rate_limit": None, "error": None}
    monkeypatch.setattr(nuclear, "_run_brain", _fake_sdk)
    monkeypatch.setattr(nuclear, "_run_brain_openrouter", _fake_or)
    # sdk transport + web -> WebSearch/WebFetch tools
    out = await nuclear._brain("p", transport="sdk", model="claude-opus-4-8", max_budget_usd=1.0, max_turns=4, web=True)
    assert out["text"] == "SDK" and "WebSearch" in calls["sdk"]["allowed_tools"]
    # openrouter transport + web -> web flag passed through
    out2 = await nuclear._brain("p", transport="openrouter", model="anthropic/claude-opus-4.1",
                                max_budget_usd=1.0, max_turns=4, web=True)
    assert out2["text"] == "OR" and calls["or"]["web"] is True
