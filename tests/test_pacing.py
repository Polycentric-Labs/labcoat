import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pacing

def test_pacing_hard_stop_on_monthly_cap():
    assert pacing.pacing_decision({"monthly_cap_reached": True})["state"] == "hard-stop"

def test_pacing_hard_stop_on_402_or_credits_exhausted():
    assert pacing.pacing_decision({"http_status": 402})["state"] == "hard-stop"
    assert pacing.pacing_decision({"openrouter_credits_exhausted": True})["state"] == "hard-stop"

def test_pacing_graceful_pause_on_429_carries_retry_after():
    d = pacing.pacing_decision({"http_status": 429, "retry_after_s": 18.0})
    assert d["state"] == "graceful-pause" and d["resume_after_s"] == 18.0

def test_pacing_graceful_pause_when_anthropic_remaining_low():
    assert pacing.pacing_decision({"anthropic_tokens_remaining": 0})["state"] == "graceful-pause"
    assert pacing.pacing_decision({"anthropic_requests_remaining": 1})["state"] == "graceful-pause"

def test_pacing_proceed_when_clear():
    d = pacing.pacing_decision({"http_status": 200, "anthropic_tokens_remaining": 1_000_000})
    assert d["state"] == "proceed" and d["resume_after_s"] is None

def test_ramp_after_idle_zero_right_after_resume():
    assert pacing.ramp_after_idle(0.0) == 0.0

def test_ramp_after_idle_full_after_window_and_clamped():
    assert pacing.ramp_after_idle(300.0) == 1.0
    assert pacing.ramp_after_idle(600.0) == 1.0   # clamped

def test_ramp_after_idle_linear_midpoint():
    assert abs(pacing.ramp_after_idle(150.0, full_after_s=300.0) - 0.5) < 1e-9

def test_ramp_after_idle_nonpositive_window_is_full():
    assert pacing.ramp_after_idle(0.0, full_after_s=0.0) == 1.0

def test_rate_limit_signals_rejected_status_yields_429_with_retry():
    s = pacing.rate_limit_signals({"status": "rejected", "retry_after_s": 30.0})
    assert s["http_status"] == 429 and s["retry_after_s"] == 30.0
    assert pacing.pacing_decision(s)["state"] == "graceful-pause"

def test_rate_limit_signals_full_utilization_is_throttled():
    s = pacing.rate_limit_signals({"status": "allowed", "utilization": 1.0})
    assert s["http_status"] == 429

def test_rate_limit_signals_healthy_is_proceed():
    s = pacing.rate_limit_signals({"status": "allowed", "utilization": 0.4})
    assert s["http_status"] is None
    assert pacing.pacing_decision(s)["state"] == "proceed"

def test_rate_limit_signals_empty_or_none_is_proceed():
    assert pacing.pacing_decision(pacing.rate_limit_signals({}))["state"] == "proceed"
    assert pacing.pacing_decision(pacing.rate_limit_signals(None))["state"] == "proceed"
