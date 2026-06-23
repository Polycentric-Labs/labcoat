import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import spend

def test_estimate_openrouter_sums_per_model_token_cost():
    specs = [{"in_price": 1.25, "out_price": 10.0}, {"in_price": 5.0, "out_price": 25.0}]
    # default 1500 in / 8000 out tokens per call
    usd = spend.estimate_openrouter(specs)
    # model1: 1500/1e6*1.25 + 8000/1e6*10 = 0.001875 + 0.08 = 0.081875
    # model2: 1500/1e6*5   + 8000/1e6*25 = 0.0075 + 0.20 = 0.2075
    assert abs(usd - (0.001875 + 0.08 + 0.0075 + 0.20)) < 1e-6

def test_estimate_openrouter_empty_is_zero():
    assert spend.estimate_openrouter([]) == 0.0

def test_estimate_claude_orchestration_scales_with_agents():
    one = spend.estimate_claude_orchestration(1)
    ten = spend.estimate_claude_orchestration(10)
    assert ten == round(one * 10, 2) and one > 0

def test_estimate_claude_orchestration_uses_calibration_defaults():
    # 1 agent x (15000/1e6*5 + 8000/1e6*25) = 0.075 + 0.20 = 0.275
    assert abs(spend.estimate_claude_orchestration(1) - 0.275) < 1e-6

def test_two_line_estimate_shape_and_confidence():
    specs = [{"in_price": 1.25, "out_price": 10.0}]
    est = spend.two_line_estimate(specs, n_agents=5, is_loop_cycle=False)
    assert set(est) == {"openrouter_usd", "claude_orchestration_usd", "total_usd", "confidence"}
    assert est["confidence"] == "tight"
    assert abs(est["total_usd"] - round(est["openrouter_usd"] + est["claude_orchestration_usd"], 2)) < 1e-9

def test_two_line_estimate_loop_cycle_is_very_rough():
    est = spend.two_line_estimate([{"in_price": 1.0, "out_price": 2.0}], n_agents=20, is_loop_cycle=True)
    assert est["confidence"] == "very-rough"
    assert est["claude_orchestration_usd"] > est["openrouter_usd"]   # orchestration dominates at scale

def test_tracker_accumulates_both_lines():
    t = spend.Tracker()
    t.add_openrouter(0.25)
    t.add_openrouter(0.14)
    t.add_claude(in_tokens=1_000_000, out_tokens=1_000_000)   # 1*5 + 1*25 = 30.0
    assert t.openrouter() == 0.39
    assert t.claude() == 30.0
    assert t.total() == round(0.39 + 30.0, 2)
    b = t.breakdown()
    assert b["openrouter_usd"] == 0.39 and b["total_usd"] == t.total()

def test_tracker_starts_at_zero():
    assert spend.Tracker().total() == 0.0

def test_tolerance_check_within_and_over():
    within = spend.tolerance_check(projected_total=12.0, tolerance=25.0)
    assert within["within_tolerance"] is True and within["over_by"] == 0.0

    over = spend.tolerance_check(projected_total=30.0, tolerance=25.0)
    assert over["within_tolerance"] is False and over["over_by"] == 5.0
    assert over["tolerance"] == 25.0

def test_tolerance_check_exactly_at_ceiling_is_within():
    r = spend.tolerance_check(projected_total=25.0, tolerance=25.0)
    assert r["within_tolerance"] is True and r["over_by"] == 0.0

def test_would_next_loop_breach_uses_cumulative():
    # current spend + next loop's projection vs tolerance
    r = spend.would_next_loop_breach(spent_so_far=20.0, next_loop_est=8.0, tolerance=25.0)
    assert r["within_tolerance"] is False and r["over_by"] == 3.0

def test_would_next_loop_breach_exact_ceiling_is_within():
    # 20 + 5 == 25 exactly: the hard ceiling is an allowed exact match
    r = spend.would_next_loop_breach(spent_so_far=20.0, next_loop_est=5.0, tolerance=25.0)
    assert r["within_tolerance"] is True and r["over_by"] == 0.0

def test_tracker_reserve_release_and_reserved():
    t = spend.Tracker()
    t.reserve(2.50)
    t.reserve(1.00)
    assert t.reserved() == 3.50
    t.release(1.00)
    assert t.reserved() == 2.50

def test_tracker_breakdown_includes_reserved_and_total_with_reserved():
    t = spend.Tracker()
    t.add_openrouter(0.40)            # committed
    t.reserve(5.00)                   # reserved (in-flight intent)
    b = t.breakdown()
    assert b["reserved_usd"] == 5.00
    assert b["total_with_reserved_usd"] == round(t.total() + 5.00, 2)
    assert t.total() == 0.40          # total() stays committed-only (back-compat)

def test_tracker_reserve_then_commit_replaces_reservation():
    # intent flow: reserve(est); on completion: release(est) + add_openrouter(actual)
    t = spend.Tracker()
    t.reserve(0.50)
    t.release(0.50); t.add_openrouter(0.42)
    assert t.reserved() == 0.0 and t.total() == 0.42

def test_tracker_release_never_goes_negative():
    # an unpaired / double release must NOT drive reserved below 0 (would under-count -> defeats the backstop)
    t = spend.Tracker()
    t.reserve(0.50)
    t.release(0.50)
    t.release(0.50)   # double release (e.g. a retry path) -> clamp, never negative
    assert t.reserved() == 0.0
    t.add_openrouter(0.40)
    assert t.breakdown()["total_with_reserved_usd"] >= t.total()   # never under-counts

import pacing  # for the composition assertions below

def test_quota_signals_monthly_cap_reached_when_mtd_at_or_over_cap():
    s = spend.quota_signals(mtd_total_usd=200.0, monthly_cap_usd=200.0)
    assert s["monthly_cap_reached"] is True
    s2 = spend.quota_signals(mtd_total_usd=150.0, monthly_cap_usd=200.0)
    assert s2["monthly_cap_reached"] is False

def test_quota_signals_openrouter_credits_exhausted_flag_or_zero_remaining():
    assert spend.quota_signals(openrouter_credits_exhausted=True)["openrouter_credits_exhausted"] is True
    assert spend.quota_signals(openrouter_limit_remaining=0)["openrouter_credits_exhausted"] is True
    assert spend.quota_signals(openrouter_limit_remaining=5)["openrouter_credits_exhausted"] is False

def test_quota_signals_passes_through_rate_limit_fields():
    s = spend.quota_signals(http_status=429, retry_after_s=12.0, anthropic_tokens_remaining=0)
    assert s["http_status"] == 429 and s["retry_after_s"] == 12.0
    assert s["anthropic_tokens_remaining"] == 0

def test_quota_signals_compose_with_pacing_decision():
    # monthly cap -> pacing hard-stop; a 429 -> graceful-pause (the detector feeds the classifier)
    assert pacing.pacing_decision(spend.quota_signals(mtd_total_usd=500.0, monthly_cap_usd=500.0))["state"] == "hard-stop"
    d = pacing.pacing_decision(spend.quota_signals(http_status=429, retry_after_s=9.0))
    assert d["state"] == "graceful-pause" and d["resume_after_s"] == 9.0

def test_quota_signals_all_none_is_proceed():
    assert pacing.pacing_decision(spend.quota_signals())["state"] == "proceed"

def test_add_claude_cost_folds_direct_usd_into_claude_line():
    tr = spend.Tracker()
    tr.add_claude_cost(0.12)
    tr.add_claude_cost(0.03)
    assert tr.claude() == 0.15
    assert tr.total() == 0.15

def test_add_claude_cost_ignores_none_and_clamps_negative():
    tr = spend.Tracker()
    tr.add_claude_cost(None)      # ignored
    tr.add_claude_cost(-5.0)      # clamped to 0 (never reduces the line)
    tr.add_claude_cost(0.10)
    assert tr.claude() == 0.10

def test_requires_explicit_burn_r8_threshold():
    assert spend.requires_explicit_burn(25.01) is True
    assert spend.requires_explicit_burn(25.0) is False     # at threshold is OK (strictly greater fires)
    assert spend.requires_explicit_burn(0.5) is False
    assert spend.requires_explicit_burn(None) is False     # no estimate -> predicate does not fire
    assert spend.requires_explicit_burn(60.0, threshold=50.0) is True

def test_tracker_reserve_and_add_openrouter_clamp_negative():
    tr = spend.Tracker()
    tr.add_openrouter(10.0); tr.add_openrouter(-10.0)   # negative ignored, not subtracted
    assert tr.openrouter() == 10.0
    tr.reserve(-1000.0)                                 # negative reservation can't go below 0
    assert tr.reserved() == 0.0
