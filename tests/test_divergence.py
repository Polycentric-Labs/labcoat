import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import divergence as dv


# ---------- Task 1: pure divergence measures ----------
def test_normalize_strips_prefix_case_quotes():
    assert dv.normalize_value("`Anthropic/Claude-3.5-Sonnet`") == "claude-3.5-sonnet"


def test_normalize_plain_lowercases():
    assert dv.normalize_value("Claude 3.5 Sonnet") == "claude 3.5 sonnet"


def test_vendor_of():
    assert dv.vendor_of("anthropic/claude-opus-4.8") == "anthropic"
    assert dv.vendor_of("gpt-5.2") == "gpt-5.2"


def test_collapse_by_vendor_modal():
    mv = {"anthropic/claude-opus-4.8": "claude-3-opus",
          "anthropic/claude-sonnet-4.6": "claude-3-opus",
          "openai/gpt-5.2": "Claude 3.5 Sonnet"}
    assert dv.collapse_by_vendor(mv) == {"anthropic": "claude-3-opus", "openai": "claude 3.5 sonnet"}


def test_collapse_drops_empty_values():
    mv = {"openai/gpt-5.2": "", "anthropic/claude-opus-4.8": None, "google/gemini-2.5-pro": "x"}
    assert dv.collapse_by_vendor(mv) == {"google": "x"}


def test_divergence_consensus_zero_alldiffer_one():
    assert dv.divergence({"a": "x", "b": "x", "c": "x"}) == 0.0
    assert dv.divergence({"a": "x", "b": "y", "c": "z"}) == 1.0
    assert dv.divergence({"a": "x", "b": "x", "c": "y"}) == 0.5  # D=2, V=3 -> (2-1)/(3-1)


def test_divergence_undefined_below_two_vendors():
    assert dv.divergence({"a": "x"}) is None
    assert dv.divergence({}) is None


def test_entropy_divergence_bounds():
    assert dv.entropy_divergence({"a": "x", "b": "x"}) == 0.0
    assert abs(dv.entropy_divergence({"a": "x", "b": "y"}) - 1.0) < 1e-9
    assert dv.entropy_divergence({"a": "x"}) is None


def test_abstention_rate():
    assert dv.abstention_rate(["a", "b", "c", "d"], {"a": "x", "b": "y"}) == 0.5
    assert dv.abstention_rate([], {}) == 0.0


# ---------- Task 2: retrospective study (reuses roc.py) ----------
def _rows(n_fab, n_conf, fab_div, conf_div):
    r = []
    for i in range(n_fab):
        r.append({"slot_id": f"f{i}", "referent": "x", "label": "fabricated",
                  "vendor_values": {"a": "p", "b": "q"} if fab_div else {"a": "p", "b": "p"}})
    for i in range(n_conf):
        r.append({"slot_id": f"c{i}", "referent": "y", "label": "confirmed",
                  "vendor_values": {"a": "p", "b": "q"} if conf_div else {"a": "p", "b": "p"}})
    return r


def test_study_inconclusive_below_kmin():
    out = dv.run_study(_rows(3, 3, True, False), seed=1, k_min=15)
    assert out["primary"]["verdict"] == "INCONCLUSIVE"
    assert out["primary"]["n_pos"] == 3 and out["primary"]["n_neg"] == 3


def test_study_weak_existence_when_divergence_tracks_fabrication():
    out = dv.run_study(_rows(20, 20, True, False), seed=1, k_min=15)
    assert out["primary"]["auc"] == 1.0
    assert out["primary"]["verdict"] == "WEAK_EXISTENCE_PROOF"
    assert abs(out["primary"]["rank_biserial"] - 1.0) < 1e-9


def test_study_honest_negative_when_no_signal():
    out = dv.run_study(_rows(20, 20, True, True), seed=1, k_min=15)
    assert out["primary"]["verdict"] in ("HONEST_NEGATIVE", "INCONCLUSIVE")


def test_study_excludes_v_lt_2():
    rows = [{"slot_id": "s", "referent": "z", "label": "fabricated", "vendor_values": {"a": "p"}}]
    out = dv.run_study(rows, seed=1, k_min=1)
    assert out["excluded_lt2"] == 1


def test_study_normalizes_before_divergence():
    # fabricated slots whose 2 vendors give FORMAT-VARIANTS that canonicalize to the SAME value.
    # If run_study normalizes -> those are consensus (div 0), matching the confirmed consensus slots -> no signal.
    # If it did NOT normalize -> fab looks divergent -> WEAK. So a non-WEAK verdict proves normalization ran.
    rows = []
    for i in range(15):
        rows.append({"slot_id": f"f{i}", "referent": "r", "label": "fabricated",
                     "vendor_values": {"a": "claude-3.5-sonnet", "b": "`Anthropic/Claude-3.5-Sonnet`"}})
    for i in range(15):
        rows.append({"slot_id": f"c{i}", "referent": "r", "label": "confirmed",
                     "vendor_values": {"a": "x", "b": "x"}})
    out = dv.run_study(rows, seed=1, k_min=15)
    assert out["primary"]["verdict"] != "WEAK_EXISTENCE_PROOF"


# ---------- Task 6: prospective instrument (verify-first queue) ----------
def test_score_run_orders_by_divergence_desc():
    ex = [{"proper_noun": "low", "vendor_values": {"a": "x", "b": "x"}},
          {"proper_noun": "high", "vendor_values": {"a": "x", "b": "y"}}]
    out = dv.score_run(ex)
    assert [r["proper_noun"] for r in out] == ["high", "low"]
    assert out[0]["divergence"] == 1.0 and out[1]["divergence"] == 0.0
    assert "entropy" in out[0]


def test_score_run_v_lt_2_sorts_last_with_none_divergence():
    ex = [{"proper_noun": "solo", "vendor_values": {"a": "x"}},
          {"proper_noun": "div", "vendor_values": {"a": "x", "b": "y"}}]
    out = dv.score_run(ex)
    assert out[0]["proper_noun"] == "div"
    assert out[-1]["proper_noun"] == "solo" and out[-1]["divergence"] is None


def test_score_run_abstention_when_fleet_given():
    ex = [{"proper_noun": "p", "vendor_values": {"a": "x", "b": "y"}}]
    out = dv.score_run(ex, fleet_vendors=["a", "b", "c", "d"])
    assert out[0]["abstention"] == 0.5
