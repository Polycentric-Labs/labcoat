import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n2_extract_llm as ex

def test_extraction_prompt_is_deterministic_and_grounded():
    p1 = ex.extraction_prompt("A Title", "An abstract about transformers.")
    p2 = ex.extraction_prompt("A Title", "An abstract about transformers.")
    assert p1 == p2                                            # deterministic
    assert "A Title" in p1 and "transformers" in p1
    assert "concepts" in p1 and "claims" in p1 and "polarity" in p1   # schema instruction present
    assert "context" in p1                                    # tweak A: context field present
    assert "verbatim" in p1 or "appear" in p1                 # tweak D: verbatim/appear-in-text rule

def test_parse_extraction_clean_fenced_prose_and_malformed():
    clean = '{"concepts": ["graph neural network", "attention"], "claims": [{"subject": "accuracy", "polarity": "+"}]}'
    r = ex.parse_extraction(clean)
    assert r["concepts"] == ["graph neural network", "attention"]
    assert r["claims"] == [{"subject": "accuracy", "polarity": "+"}]
    fenced = "```json\n" + clean + "\n```"
    assert ex.parse_extraction(fenced)["concepts"] == ["graph neural network", "attention"]
    prose = "Here is the JSON:\n" + clean + "\nHope that helps!"
    assert ex.parse_extraction(prose)["claims"][0]["subject"] == "accuracy"
    # malformed claims dropped (missing subject / bad polarity), good kept; value + context preserved when present
    mixed = '{"concepts": ["x", "x", "Y"], "claims": [{"subject":"a","polarity":"+","value":"BLEU","context":"in vitro"},{"polarity":"+"},{"subject":"b","polarity":"?"}]}'
    rm = ex.parse_extraction(mixed)
    assert rm["concepts"] == ["x", "Y"]                        # case-dedupe ('x' once)
    assert len(rm["claims"]) == 1
    assert rm["claims"][0]["subject"] == "a"
    assert rm["claims"][0]["polarity"] == "+"
    assert rm["claims"][0].get("value") == "BLEU"
    assert rm["claims"][0].get("context") == "in vitro"        # tweak A: context carried
    assert ex.parse_extraction("not json at all") == {"concepts": [], "claims": []}

def test_ground_extraction_span_guard():
    parsed = {
        "concepts": ["graph neural network", "FABRICATED"],
        "claims": [
            {"subject": "accuracy", "polarity": "+"},
            {"subject": "ghost", "polarity": "-"},
        ],
    }
    source = "we study a graph neural network; accuracy improves"
    result = ex.ground_extraction(parsed, source)
    assert result["concepts"] == ["graph neural network"]      # FABRICATED dropped (not in source)
    assert result["claims"] == [{"subject": "accuracy", "polarity": "+"}]  # ghost dropped
    # empty source -> drops all
    empty_result = ex.ground_extraction(parsed, "")
    assert empty_result["concepts"] == [] and empty_result["claims"] == []
    # missing keys safe
    safe = ex.ground_extraction({}, "some text")
    assert safe == {"concepts": [], "claims": []}

def test_extract_llm_with_injected_brain_fn():
    docs = [{"title": "T1", "abstract": "A1"}, {"title": "T2", "abstract": "A2"}, {"title": "T3", "abstract": "A3"}]
    replies = {
        ex.extraction_prompt("T1", "A1"): '{"concepts":["alpha","beta"],"claims":[{"subject":"x","polarity":"+"}]}',
        ex.extraction_prompt("T2", "A2"): '```json\n{"concepts":["beta","gamma"],"claims":[]}\n```',
        ex.extraction_prompt("T3", "A3"): 'garbage no json',         # fail-soft -> contributes nothing
    }
    concept_lists, claims = ex.extract_llm(docs, brain_fn=lambda p: replies[p])
    # ground_extraction applied: "alpha","beta" NOT in "T1 A1" source text -> dropped; same for T2
    # All concepts will be dropped because none appear verbatim in the 1-char abstract "A1"/"A2"
    assert len(concept_lists) == 3
    assert concept_lists[0] == [] and concept_lists[1] == []   # alpha/beta/gamma grounded out (not in "T1 A1"/"T2 A2")
    assert concept_lists[2] == []   # garbage -> empty
    # claims: "x" not in "T1 A1" -> grounded out
    assert claims == []

def test_extract_llm_with_context_flowing_through():
    # context flows through when brain returns it and subject is grounded
    docs = [{"title": "accuracy study", "abstract": "accuracy improves in vitro"}]
    reply = '{"concepts":["accuracy"],"claims":[{"subject":"accuracy","polarity":"+","context":"in vitro"}]}'
    concept_lists, claims = ex.extract_llm(docs, brain_fn=lambda p: reply)
    assert concept_lists[0] == ["accuracy"]      # "accuracy" appears in source
    assert claims[0]["context"] == "in vitro"    # context preserved
    assert claims[0]["polarity"] == "+"

def test_extract_llm_hallucinated_concept_dropped():
    # hallucinated concept (not in source) is dropped by ground_extraction (tweak D)
    docs = [{"title": "neural network study", "abstract": "we study a neural network"}]
    reply = '{"concepts":["neural network","FABRICATED_TERM"],"claims":[]}'
    concept_lists, claims = ex.extract_llm(docs, brain_fn=lambda p: reply)
    assert "neural network" in concept_lists[0]
    assert "FABRICATED_TERM" not in concept_lists[0]

def test_parse_extraction_omits_empty_context_and_value():
    # context/value omitted when empty string or missing
    no_ctx = '{"concepts": ["x"], "claims": [{"subject":"a","polarity":"+","value":"","context":""}]}'
    r = ex.parse_extraction(no_ctx)
    assert "context" not in r["claims"][0]
    assert "value" not in r["claims"][0]
