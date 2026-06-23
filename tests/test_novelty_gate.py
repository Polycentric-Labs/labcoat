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
