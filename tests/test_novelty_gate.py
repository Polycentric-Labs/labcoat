import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import novelty_gate as ng

def test_normalize_lowercases_collapses_ws_strips_punct():
    assert ng.normalize("  GLM is ON the  BIS, Entity-List!! ") == "glm is on the bis entity list"

def test_normalize_handles_none_and_empty():
    assert ng.normalize(None) == "" and ng.normalize("") == ""

def test_finding_key_stable_and_equivalence():
    # normalized-equivalent texts share a key; different texts do not
    assert ng.finding_key("GLM is on the BIS list") == ng.finding_key("glm  is on the BIS, list")
    assert ng.finding_key("a") != ng.finding_key("b")
    assert len(ng.finding_key("x")) == 64   # sha256 hex


def test_jaccard_distance_identical_is_zero_disjoint_is_one():
    assert ng.jaccard_distance("the quick brown fox jumps", "the quick brown fox jumps") == 0.0
    assert ng.jaccard_distance("alpha beta gamma delta", "one two three four") == 1.0

def test_jaccard_distance_partial_overlap_between_0_and_1():
    d = ng.jaccard_distance("the quick brown fox runs", "the quick brown dog runs")
    assert 0.0 < d < 1.0

def test_novelty_distance_empty_corpus_is_fully_novel():
    assert ng.novelty_distance("anything at all here", []) == 1.0

def test_novelty_distance_is_min_distance_to_corpus():
    corpus = ["the quick brown fox jumps high", "totally unrelated content string here"]
    # near-duplicate of corpus[0] -> small distance
    assert ng.novelty_distance("the quick brown fox jumps high", corpus) == 0.0
    # a far text -> large distance
    assert ng.novelty_distance("xxxxx yyyyy zzzzz wwwww vvvvv", corpus) > 0.5

def test_novelty_distance_accepts_injected_distance_fn():
    # an injected distance_fn (e.g. an SBERT-cosine upgrade) overrides the Jaccard floor
    assert ng.novelty_distance("a", ["b"], distance_fn=lambda x, y: 0.25) == 0.25


def _rec(qid, verdict, claim, status="complete"):
    return {"query_id": qid, "validation_verdict": verdict, "claim_text": claim,
            "completion_status": status}

def test_cny_counts_only_confirmed_unseen_distant_findings():
    records = [
        _rec("q1", "confirmed", "the quick brown fox jumps high"),     # novel (empty corpus)
        _rec("q2", "fabricated", "a totally different fabricated claim"),  # not confirmed -> ignored
        _rec("q3", "pending",   "another pending claim here entirely"),    # not confirmed -> ignored
    ]
    out = ng.cny(records, seen_keys=set(), corpus=[], tau=0.5)
    assert out["cny"] == 1
    assert out["novel_findings"] == ["the quick brown fox jumps high"]
    assert len(out["new_keys"]) == 1 and out["new_corpus"] == ["the quick brown fox jumps high"]

def test_cny_dedups_against_seen_keys():
    seen = {ng.finding_key("the quick brown fox jumps high")}
    records = [_rec("q1", "confirmed", "The Quick Brown Fox Jumps High")]   # normalized dup of a seen key
    out = ng.cny(records, seen_keys=seen, corpus=[], tau=0.5)
    assert out["cny"] == 0 and out["new_keys"] == []

def test_cny_excludes_near_duplicates_of_corpus_below_tau():
    corpus = ["the quick brown fox jumps high"]
    records = [_rec("q1", "confirmed", "the quick brown fox jumps high again")]  # very close -> distance < tau
    out = ng.cny(records, seen_keys=set(), corpus=corpus, tau=0.5)
    assert out["cny"] == 0          # unseen key, but too close to the corpus -> not novel
    assert len(out["new_keys"]) == 1   # still recorded as seen (so it won't be re-counted next loop)

def test_cny_ignores_confirmed_with_empty_claim_text():
    records = [_rec("q1", "confirmed", "   ")]
    assert ng.cny(records, seen_keys=set(), corpus=[], tau=0.5)["cny"] == 0


def test_yield_collapse_warmup_never_collapses():
    # fewer than `window` samples -> warm-up, never collapsed (must not halt a young run)
    assert ng.yield_collapse([0, 0], floor=0, window=3)["collapsed"] is False

def test_yield_collapse_all_low_and_nonincreasing_collapses():
    r = ng.yield_collapse([5, 1, 0, 0, 0], floor=0, window=3)
    assert r["collapsed"] is True and r["trend"] == "decaying"

def test_yield_collapse_all_low_but_recovering_does_not_collapse():
    # within the window the last value rose above the first -> recovering, not collapsed
    assert ng.yield_collapse([0, 0, 1], floor=1, window=3)["collapsed"] is False

def test_yield_collapse_above_floor_does_not_collapse():
    assert ng.yield_collapse([3, 4, 5], floor=0, window=3)["collapsed"] is False


def test_shingles_and_cny_handle_short_text():
    # a 1-word finding text produces a sane single shingle and does not crash cny
    assert ng._shingles("singleword") == {"singleword"}
    out = ng.cny([_rec("q1", "confirmed", "novel")], seen_keys=set(), corpus=[], tau=0.5)
    assert out["cny"] == 1   # 1-word confirmed finding, empty corpus -> fully novel


# --- Saturation-gate calibration (the warrant for the ENFORCING default) -------------------------------------
# README.md / SKILL.md claim the gate is "calibrated to tau=0.30 / floor=0 / window=3 on three diverse multi-loop
# curves" with zero false positives/negatives. These tests re-derive that claim from the shipped curves, so a
# reader can check the ENFORCING default from a clone — no network, no credential, no live run required.
import json

_CALIB = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" /
                     "novelty-gate-calibration-curves.json").read_text(encoding="utf-8"))


def _first_collapse_loop(cny_history, *, floor, window):
    """Replay the gate prospectively, loop by loop, exactly as the live engine does: return the 1-indexed loop
    at which yield_collapse first fires over the history-so-far, or None if it never fires."""
    for i in range(1, len(cny_history) + 1):
        if ng.yield_collapse(cny_history[:i], floor=floor, window=window)["collapsed"]:
            return i
    return None


def test_calibration_fixture_matches_the_documented_params():
    # the adopted params are exactly the ones README.md/SKILL.md advertise as the enforcing default
    assert _CALIB["adopted_params"] == {"tau": 0.30, "floor": 0, "window": 3}
    assert len(_CALIB["curves"]) == 3
    assert {c["shape"] for c in _CALIB["curves"]} == {"sharp", "steady-productive", "bursty"}


def test_calibration_adopted_params_classify_all_three_curves_with_zero_errors():
    # THE claim: floor=0 / window=3 classifies all three curves correctly -- no false positive, no false negative
    p = _CALIB["adopted_params"]
    for curve in _CALIB["curves"]:
        got = _first_collapse_loop(curve["cny_history"], floor=p["floor"], window=p["window"])
        assert (got is not None) == curve["expected_collapse"], f"{curve['id']}: {curve['why']}"
        assert got == curve["expected_first_collapse_loop"], f"{curve['id']}: fired at loop {got}"


def test_calibration_window_2_is_rejected_because_it_false_fires_on_the_bursty_curve():
    # the recorded reason window=2 was rejected: it fires in the [0,0] valley BEFORE the burst of 13 arrives
    bursty = next(c for c in _CALIB["curves"] if c["id"] == "exp3_ai_safety")
    assert _first_collapse_loop(bursty["cny_history"], floor=0, window=2) == 4   # false positive
    assert _first_collapse_loop(bursty["cny_history"], floor=0, window=3) is None  # window=3 does not
    assert bursty["cny_history"][4] == 13   # ...and a productive burst really does follow the valley
