# tests/test_route_integration.py
import sys, pathlib, json, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import route_integration as ri

def test_route_query_returns_sonar_router_verdict(monkeypatch):
    fake = {"recommended_tool": "gh api", "fallback": "perplexity_ask", "score": {}, "rationale": "x"}
    def fake_run(query): return json.dumps(fake)
    monkeypatch.setattr(ri, "_run_route_script", fake_run)
    out = ri.route_query("does repo foo/bar exist")
    assert out["recommended_tool"] == "gh api"

def test_route_query_handles_router_absent(monkeypatch):
    def boom(query): raise FileNotFoundError("route.py not found")
    monkeypatch.setattr(ri, "_run_route_script", boom)
    out = ri.route_query("anything")
    assert out["recommended_tool"] == "perplexity_ask"  # safe default
    assert out.get("degraded") is True

def test_route_query_degrades_on_nonzero_exit_and_surfaces_stdout(monkeypatch):
    def boom(query):
        raise subprocess.CalledProcessError(2, ["python", "route.py"], output='{"error": "empty query"}')
    monkeypatch.setattr(ri, "_run_route_script", boom)
    out = ri.route_query("anything")
    assert out["degraded"] is True
    assert "empty query" in out["rationale"]   # router's own diagnostic surfaced

def test_route_query_degrades_on_malformed_json(monkeypatch):
    monkeypatch.setattr(ri, "_run_route_script", lambda q: "not valid json {")
    out = ri.route_query("anything")
    assert out["degraded"] is True
    assert out["recommended_tool"] == "perplexity_ask"

def test_route_query_degrades_on_wrong_shape(monkeypatch):
    monkeypatch.setattr(ri, "_run_route_script", lambda q: "[1, 2, 3]")  # valid JSON, wrong shape
    out = ri.route_query("anything")
    assert out["degraded"] is True
    assert out["recommended_tool"] == "perplexity_ask"
