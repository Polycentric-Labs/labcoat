import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import loop_evolution as le

def test_parse_gaps_normalizes_and_defaults_kind():
    out = le.parse_gaps([{"kind": "contradiction", "text": "A conflicts with B", "seed_evidence": "ev1"},
                         {"text": "no kind given"}, {"kind": "BOGUS", "text": "unknown kind"}])
    assert out[0] == {"id": "g1", "kind": "contradiction", "text": "A conflicts with B", "seed_evidence": "ev1"}
    assert out[1]["kind"] == "gap"          # missing kind -> safe default
    assert out[2]["kind"] == "gap"          # unknown kind -> safe default
    assert out[1]["id"] == "g2"

def test_parse_gaps_tolerates_json_string_envelope_and_drops_empty():
    env = json.dumps({"gaps": [{"kind": "future_work", "text": "do Z"}, {"text": ""}]})
    out = le.parse_gaps(env)
    assert [g["text"] for g in out] == ["do Z"]
    assert le.parse_gaps(None) == [] and le.parse_gaps(42) == []

def test_rank_gaps_contradictions_first_stable():
    gaps = [{"id":"g1","kind":"gap","text":"a"}, {"id":"g2","kind":"contradiction","text":"b"},
            {"id":"g3","kind":"future_work","text":"c"}, {"id":"g4","kind":"contradiction","text":"d"}]
    ranked = le.rank_gaps(gaps)
    assert [g["id"] for g in ranked] == ["g2", "g4", "g3", "g1"]   # contradiction<won<future<gap, stable

def test_minimal_criterion_rejects_trivially_answerable():
    established = ["the sky is blue because of rayleigh scattering of sunlight"]
    # near-identical candidate -> already established -> rejected
    assert le.minimal_criterion("the sky is blue because of rayleigh scattering of sunlight",
                                established, max_similarity=0.7) is False
    # unrelated candidate -> not trivial -> accepted
    assert le.minimal_criterion("how do tax incentives affect battery recycling rates",
                                established, max_similarity=0.7) is True
    assert le.minimal_criterion("", established) is False          # empty candidate
    assert le.minimal_criterion("anything", []) is True            # nothing to be trivial against

def test_question_novelty_distance_to_prior_questions():
    prior = ["how does X scale", "what causes Y"]
    assert le.question_novelty("what causes Y", prior) == 0.0       # identical to a prior question
    assert le.question_novelty("entirely unrelated probe", prior) > 0.5
    assert le.question_novelty("anything", []) == 1.0               # no prior -> fully novel

def test_select_evolved_questions_filters_and_preserves_rank():
    ranked = [{"id":"g1","kind":"contradiction","text":"does claim A contradict claim B under load","seed_evidence":""},
              {"id":"g2","kind":"gap","text":"how does X scale","seed_evidence":""},        # == a prior question
              {"id":"g3","kind":"gap","text":"the sky is blue rayleigh scattering sunlight","seed_evidence":""}]  # established
    prior_questions = ["how does X scale"]
    established = ["the sky is blue rayleigh scattering sunlight"]
    out = le.select_evolved_questions(ranked, prior_questions, established,
                                      min_question_distance=0.3, max_similarity_to_established=0.7, max_select=6)
    ids = [g["id"] for g in out]
    assert ids == ["g1"]                       # g2 too-close-to-prior, g3 trivially-established -> dropped
    assert "question_distance" in out[0]

def test_question_stream_collapsed_spc_rule():
    # all <= floor and non-increasing over the window -> collapsed
    assert le.question_stream_collapsed([0.2, 0.1, 0.05], floor_distance=0.3, window=3)["collapsed"] is True
    # a recent high-distance question -> not collapsed
    assert le.question_stream_collapsed([0.1, 0.1, 0.9], floor_distance=0.3, window=3)["collapsed"] is False
    # warm-up: fewer than window samples -> not collapsed
    assert le.question_stream_collapsed([0.1, 0.1], floor_distance=0.3, window=3)["collapsed"] is False
