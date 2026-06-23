import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import value_axis as va

def test_source_count_dedups_sources_list_case_and_ws_insensitive():
    assert va.source_count({"sources": ["https://a", "https://A", " https://b "]}) == 2

def test_source_count_evidence_fallback_and_empty():
    assert va.source_count({"evidence": "gh api response"}) == 1   # no list -> 1 if evidence present
    assert va.source_count({"evidence": ""}) == 0
    assert va.source_count({}) == 0
    assert va.source_count("not a dict") == 0

def test_source_count_empty_sources_list_falls_back_to_evidence():
    assert va.source_count({"sources": [], "evidence": "x"}) == 1
    assert va.source_count({"sources": ["  "], "evidence": ""}) == 0

def test_quality_weight_capped_and_nonnegative():
    assert va.quality_weight(0) == 0.0
    assert va.quality_weight(2) == 2.0
    assert va.quality_weight(5, cap=3) == 3.0     # capped (weight can't dominate)
    assert va.quality_weight(-4) == 0.0           # negative clamped

def test_weighted_cny_sums_capped_weights():
    assert va.weighted_cny([1, 2, 5], cap=3) == 6.0   # 1 + 2 + 3(capped)
    assert va.weighted_cny([]) == 0.0

def test_cost_per_verified_finding():
    assert va.cost_per_verified_finding(2.40, 8) == 0.3
    assert va.cost_per_verified_finding(1.0, 0) is None   # undefined when no confirmed findings

def test_cost_per_verified_finding_clamps_negative_spend():
    assert va.cost_per_verified_finding(-5.0, 5) == 0.0

def test_qd_archive_update_keeps_higher_quality_elite_per_cell():
    arch = {}
    arch = va.qd_archive_update(arch, behavior_key="cellA", quality=1.0, finding="f1")
    arch = va.qd_archive_update(arch, behavior_key="cellA", quality=3.0, finding="f2")  # higher -> replaces
    arch = va.qd_archive_update(arch, behavior_key="cellA", quality=2.0, finding="f3")  # lower -> ignored
    arch = va.qd_archive_update(arch, behavior_key="cellB", quality=0.5, finding="g1")  # new cell
    assert arch["cellA"] == {"quality": 3.0, "finding": "f2"}
    assert arch["cellB"] == {"quality": 0.5, "finding": "g1"}

def test_qd_archive_update_is_pure_does_not_mutate_input():
    original = {"c": {"quality": 1.0, "finding": "x"}}
    out = va.qd_archive_update(original, behavior_key="c", quality=2.0, finding="y")
    assert original == {"c": {"quality": 1.0, "finding": "x"}}   # input unchanged
    assert out["c"]["finding"] == "y"

def test_weighted_yield_collapse_flags_thinning_quality():
    # all <= floor over the window AND non-increasing -> collapse (the SAME SPC rule as novelty_gate, on floats)
    res = va.weighted_yield_collapse([1.0, 0.0, 0.0, 0.0], floor=0.0, window=3)
    assert res["collapsed"] is True

def test_weighted_yield_collapse_warmup_and_productive():
    assert va.weighted_yield_collapse([2.0], floor=0.0, window=3)["collapsed"] is False        # warm-up
    assert va.weighted_yield_collapse([3.0, 2.0, 4.0], floor=0.0, window=3)["collapsed"] is False  # above floor
