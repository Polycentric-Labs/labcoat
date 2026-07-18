import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import gap_channels as gc

def test_abc_whitespace_finds_two_hop_no_direct_link():
    # A-B and B-C present, A-C ABSENT -> (A,C) is an ABC whitespace candidate, bridged by B
    edges = [["fish oil", "blood viscosity"], ["blood viscosity", "raynaud"]]
    out = gc.abc_whitespace(edges)
    assert len(out) == 1
    g = out[0]
    assert {g["a"], g["c"]} == {"fish oil", "raynaud"} and g["bridges"] == ["blood viscosity"]

def test_abc_whitespace_skips_directly_linked_pairs():
    edges = [["a", "b"], ["b", "c"], ["a", "c"]]   # a-c is DIRECT -> not a gap
    assert gc.abc_whitespace(edges) == []

def test_abc_whitespace_relatedness_filter_drops_spurious_absent_edges():
    edges = [["a", "b"], ["b", "c"]]
    # an absent edge is only a gap if a,c are related; relatedness 0 -> dropped
    assert gc.abc_whitespace(edges, relatedness_fn=lambda x, y: 0.0, min_relatedness=0.3) == []
    assert len(gc.abc_whitespace(edges, relatedness_fn=lambda x, y: 0.9, min_relatedness=0.3)) == 1
    assert gc.abc_whitespace([]) == [] and gc.abc_whitespace(None) == []

def test_mine_future_work_extracts_flagged_sentences():
    text = ("We present a new method. In future work, we will scale to 100B params. "
            "The results are strong. This remains an open problem for larger corpora.")
    hits = gc.mine_future_work(text)
    assert any("future work" in h.lower() for h in hits)
    assert any("remains an open" in h.lower() for h in hits)
    assert all("results are strong" not in h.lower() for h in hits)   # non-future sentence excluded
    assert gc.mine_future_work("") == []

def test_find_contradictions_same_subject_opposing():
    # updated for tweak A: output shape is {subject, context, claims}
    claims = [{"subject": "method X scales", "polarity": "+"},
              {"subject": "method X scales", "polarity": "-"},
              {"subject": "method Y is fast", "polarity": "+"}]
    out = gc.find_contradictions(claims)
    assert len(out) == 1 and out[0]["subject"] == "method x scales"
    assert "context" in out[0]                                # context key always present
    assert "claims" in out[0]                                 # claims key present
    # distinct VALUES for the same key also contradict
    val = [{"key": "best F1", "value": "0.82"}, {"key": "best F1", "value": "0.91"}]
    assert len(gc.find_contradictions(val)) == 1
    assert gc.find_contradictions([]) == []
    assert gc.find_contradictions([{"subject": "only one", "polarity": "+"}]) == []

def test_reconcile_whitespace_when_no_future_work_match():
    structural = [{"a": "concept_alpha", "c": "concept_beta", "bridges": ["b"]}]
    future = ["In future work we will study scaling laws."]          # neither concept mentioned
    out = gc.reconcile_channels(structural=structural, future_work=future)
    srecs = [g for g in out if g["gap_type"] == "structural"]
    assert srecs and all(g["evidentiary_status"] == "whitespace" for g in srecs)

def test_reconcile_known_but_unaddressed_when_both_concepts_in_one_future_sentence():
    structural = [{"a": "concept_alpha", "c": "concept_beta", "bridges": ["b"]}]
    future = ["In future work we will combine concept_alpha and concept_beta."]
    out = gc.reconcile_channels(structural=structural, future_work=future)
    srecs = [g for g in out if g["gap_type"] == "structural"]
    assert srecs and all(g["evidentiary_status"] == "known-but-unaddressed" for g in srecs)
    # the corroborating sentence is NOT also emitted as a separate speculative gap (S2 dedupe)
    assert not any(g["evidentiary_status"] == "speculative" for g in out)

def test_reconcile_substring_does_not_false_match_short_token():
    # "ml" must NOT match "formally"/"normally" via substring -> stays whitespace (S1 fix)
    structural = [{"a": "ml", "c": "biology", "bridges": ["b"]}]
    future = ["In future work this will be done more formally in biology settings."]
    out = gc.reconcile_channels(structural=structural, future_work=future)
    srecs = [g for g in out if g["gap_type"] == "structural"]
    assert srecs and all(g["evidentiary_status"] == "whitespace" for g in srecs)   # "ml" not a whole word here

def test_reconcile_drops_already_addressed():
    structural = [{"a": "x", "c": "y", "bridges": ["b"]}]
    assert gc.reconcile_channels(structural=structural, addressed={"x | y"}) == []

def test_score_gap_keeps_two_axes_plus_advisory_priority():
    g = {"text": "gap", "gap_type": "structural", "evidentiary_status": "whitespace"}
    scored = gc.score_gap(g, novelty=0.8, utility=0.5)
    assert scored["novelty_score"] == 0.8 and scored["utility_score"] == 0.5   # BOTH axes kept (not collapsed)
    assert scored["priority"] == 0.4                                           # advisory novelty*utility hint
    assert scored["text"] == "gap"                                             # original fields preserved
    # clamped
    assert gc.score_gap(g, novelty=2.0, utility=-1.0)["priority"] == 0.0

def test_to_next_question_candidates_maps_to_loop_evolution_shape():
    reconciled = [
        {"text": "contradiction on: drug Z", "gap_type": "contradiction", "evidentiary_status": "contradiction",
         "channels": ["contradiction"], "provenance": {}},
        {"text": "the unexplored link between A and B", "gap_type": "structural",
         "evidentiary_status": "whitespace", "channels": ["structural"], "provenance": {}}]
    cands = gc.to_next_question_candidates(reconciled)
    # loop_evolution gap-record shape: {kind, text, seed_evidence}; contradiction kind preserved (ranks first there)
    assert cands[0]["kind"] == "contradiction" and cands[0]["text"]
    assert cands[1]["kind"] == "gap"
    assert all(set(c.keys()) >= {"kind", "text", "seed_evidence"} for c in cands)

def test_extract_concepts_titlecase_acronyms_dedupe_stop():
    txt = "We propose Graph Neural Networks. BERT and Graph Neural Networks improve results. The Transformer helps."
    terms = gc.extract_concepts(txt)
    assert "Graph Neural Networks" in terms
    assert "BERT" in terms
    assert "Transformer" in terms
    assert "We" not in terms and "The" not in terms          # capitalized stopwords dropped
    assert sum(1 for t in terms if t == "Graph Neural Networks") == 1   # case-insensitive dedupe
    assert len(gc.extract_concepts(txt, max_terms=2)) == 2    # cap honored

def test_cooccurrence_edges_within_doc_pairs_dedupe():
    docs = ["Alpha uses Bridge.", "Bridge enables Gamma."]    # Alpha,Gamma never co-occur (a 2-hop gap later)
    edges = gc.cooccurrence_edges(docs)
    assert ("Alpha", "Bridge") in edges and ("Bridge", "Gamma") in edges
    assert ("Alpha", "Gamma") not in edges                    # not in the same doc
    # a < c ordering + cross-doc dedupe
    assert all(a < c for (a, c) in edges)
    assert len(edges) == len(set(edges))

def test_extract_claims_polarity_and_subject():
    # NOTE: plan used "ResNet" but _TITLE_RE splits CamelCase -> "Res"; using all-caps "RESNET" so _ACRONYM_RE
    # catches it and subject is "resnet" as intended. Minimal deviation from plan; intent preserved.
    claims = gc.extract_claims("BERT improves accuracy. RESNET reduces error.")
    assert {"subject": "bert", "polarity": "+"} in claims
    assert {"subject": "resnet", "polarity": "-"} in claims
    assert gc.extract_claims("A neutral sentence with no polarity verb.") == []

def test_extract_claims_feeds_find_contradictions():
    # same subject, opposing polarity across sentences -> find_contradictions flags it
    claims = gc.extract_claims("Dropout improves generalization. Dropout reduces generalization.")
    cons = gc.find_contradictions(claims)
    assert any(c["subject"] == "dropout" for c in cons)

def test_find_contradictions_context_matching_tweak_a():
    # same subject + same context -> contradiction flagged (carries context)
    claims_same_ctx = [
        {"subject": "drug X efficacy", "polarity": "+", "context": "in vitro"},
        {"subject": "drug X efficacy", "polarity": "-", "context": "in vitro"},
    ]
    out = gc.find_contradictions(claims_same_ctx)
    assert len(out) == 1
    assert out[0]["subject"] == "drug x efficacy"
    assert out[0]["context"] == "in vitro"
    assert "claims" in out[0]

    # same subject, DIFFERENT context -> NOT flagged (conditionally reconcilable, tweak A)
    claims_diff_ctx = [
        {"subject": "drug X efficacy", "polarity": "+", "context": "in vitro"},
        {"subject": "drug X efficacy", "polarity": "-", "context": "in vivo"},
    ]
    assert gc.find_contradictions(claims_diff_ctx) == []

    # no-context claims grouped under '' (unconditioned) -> still flagged if polarity disagrees
    claims_no_ctx = [
        {"subject": "accuracy", "polarity": "+"},
        {"subject": "accuracy", "polarity": "-"},
    ]
    out_no_ctx = gc.find_contradictions(claims_no_ctx)
    assert len(out_no_ctx) == 1
    assert out_no_ctx[0]["context"] == ""

def test_cooccurrence_edges_from_concepts_builds_unique_pairs():
    lists = [["alpha", "beta", "gamma"], ["beta", "gamma"], ["beta", "alpha"]]
    edges = gc.cooccurrence_edges_from_concepts(lists)
    assert ("alpha", "beta") in edges and ("beta", "gamma") in edges and ("alpha", "gamma") in edges
    assert len(edges) == len(set(edges))                       # deduped across docs
    assert all(a < c for (a, c) in edges)                      # a<c canonical order
    assert gc.cooccurrence_edges_from_concepts([]) == []

def test_cooccurrence_edges_refactor_is_identical(monkeypatch):
    docs = ["The Transformer improves BLEU. We study Adam and SGD.",
            "Adam outperforms SGD on ImageNet with ResNet."]
    # the refactored cooccurrence_edges must equal building from extract_concepts directly
    expected = gc.cooccurrence_edges_from_concepts([gc.extract_concepts(d, max_terms=12) for d in docs])
    assert gc.cooccurrence_edges(docs) == expected

def test_abc_whitespace_excludes_hub_bridges():
    import gap_channels as g
    # A-C have no direct edge; their ONLY shared bridge is H (a hub, deg 4). With max_bridge_degree=2, H is excluded
    # -> no non-hub bridge -> A,C is NOT a gap.
    edges = [("A","H"),("C","H"),("H","X"),("H","Y")]   # H deg 4; A,C deg 1
    assert g.abc_whitespace(edges) and any(p["a"]=="A" and p["c"]=="C" for p in g.abc_whitespace(edges))  # gap w/o exclusion
    excluded = g.abc_whitespace(edges, max_bridge_degree=2)
    assert not any(p["a"]=="A" and p["c"]=="C" for p in excluded)   # H-only gap dropped
    # a gap with a LOW-degree real bridge survives
    edges2 = [("A","B"),("C","B"),("B","Z")]            # B deg 3; bridge B for A,C
    assert any(p["a"]=="A" and p["c"]=="C" for p in g.abc_whitespace(edges2, max_bridge_degree=3))

def test_abc_whitespace_none_preserves_behavior():
    import gap_channels as g
    edges = [("A","B"),("C","B")]
    assert g.abc_whitespace(edges) == g.abc_whitespace(edges, max_bridge_degree=None)   # regression

def test_pmi_context_relatedness_discriminates():
    import gap_channels as g
    # A and C never co-occur, but both co-occur with the SAME real intermediates {M,N,P} across docs -> related.
    # X and Y never co-occur and share only a HUB H (which co-occurs with everything) -> low after context cosine.
    docs = [["A","M","N"],["A","N","P"],["C","M","N"],["C","N","P"],   # A,C share context {M,N,P}
            ["X","H","M"],["Y","H","P"],["H","A"],["H","C"],["H","X"],["H","Y"]]  # H is a hub
    rel = g.pmi_context_relatedness(docs)
    r_ac = rel("A", "C")
    r_xy = rel("X", "Y")
    assert r_ac > 0.3            # A,C share real intermediates -> meaningfully related
    assert r_ac > r_xy          # related pair scores higher than the hub-only pair
    assert rel("A", "ZZZ") == 0.0   # unknown concept -> 0
    assert g.pmi_context_relatedness([])("A", "B") == 0.0

def test_hub_bridge_threshold_percentile():
    import gap_channels as g
    # star: HUB connects to 10 DISTINCT leaves (deg 10); each leaf deg 1. n=11 nodes. (Hub named "HUB" so it does not
    # collide with any leaf — the prior "H" + A..J leaves silently made H a leaf via the dropped self-edge.)
    edges = [("HUB", f"L{i}") for i in range(10)]
    thr = g.hub_bridge_threshold(edges, percentile=0.90)
    assert thr is not None and thr >= 1
    assert g.concept_degrees(edges)["HUB"] > thr        # the topic hub (max degree) sits above the threshold -> excludable
    assert g.hub_bridge_threshold([], percentile=0.9) is None       # <2 nodes
    # SMALL-n regression (the min(n-2) fix): even a tiny 5-node star must keep the hub excludable (the old min(n-1)
    # returned the hub's OWN degree as the threshold, so strict `>` never excluded it).
    small = [("HUB", f"L{i}") for i in range(4)]        # HUB deg 4, 4 leaves deg 1, n=5
    assert g.concept_degrees(small)["HUB"] > g.hub_bridge_threshold(small, percentile=0.90)

def test_concept_degrees_counts_distinct_partners():
    import gap_channels as g
    edges = [("A", "B"), ("A", "C"), ("B", "C"), ("D", "A")]
    d = g.concept_degrees(edges)
    assert d == {"A": 3, "B": 2, "C": 2, "D": 1}        # A partners {B,C,D}
    assert g.concept_degrees([]) == {}
    assert g.concept_degrees([("X", "X"), ("", "Y")]) == {}   # self-loop + empty dropped

def test_gaps_pipeline_wires_relatedness_and_reconcile():
    # the shape gaps_live uses: cooccurrence_edges -> abc_whitespace(relatedness_fn) -> reconcile -> candidates.
    docs = ["Alpha uses Bridge.", "Bridge enables Gamma."]   # Alpha,Gamma 2-hop via Bridge, no direct edge
    edges = gc.cooccurrence_edges(docs)
    kept = gc.abc_whitespace(edges, relatedness_fn=lambda a, c: 1.0, min_relatedness=0.5)
    dropped = gc.abc_whitespace(edges, relatedness_fn=lambda a, c: 0.0, min_relatedness=0.5)
    assert len(kept) >= 1 and len(dropped) == 0              # N1-fusion filtering demonstrably removes the gap
    rec = gc.reconcile_channels(structural=kept, future_work=[], contradictions=[])
    cands = gc.to_next_question_candidates(rec)
    assert cands and all("kind" in c and "text" in c for c in cands)
    assert rec[0]["evidentiary_status"] == "whitespace"     # structural-only -> whitespace tag

def test_cooccurrence_provenance_maps_pairs_to_docids():
    concept_lists = [["fish oil", "blood viscosity"],          # doc P1
                     ["blood viscosity", "raynaud"],            # doc P2
                     ["fish oil", "blood viscosity"]]           # doc P3 (repeat pair)
    prov = gc.cooccurrence_provenance(concept_lists, ["P1", "P2", "P3"])
    assert prov[frozenset({"fish oil", "blood viscosity"})] == {"P1", "P3"}
    assert prov[frozenset({"blood viscosity", "raynaud"})] == {"P2"}
    assert frozenset({"fish oil", "raynaud"}) not in prov   # never co-mentioned

def test_cooccurrence_provenance_ignores_self_pairs_and_blanks():
    prov = gc.cooccurrence_provenance([["x", "x", ""]], ["D"])
    assert prov == {}

def test_abc_whitespace_classifies_cross_vs_intra_paper():
    # Cross: fish oil–blood viscosity from P1, blood viscosity–raynaud from P2 (different papers)
    cross_lists = [["fish oil", "blood viscosity"], ["blood viscosity", "raynaud"]]
    edges = gc.cooccurrence_edges_from_concepts(cross_lists)
    prov = gc.cooccurrence_provenance(cross_lists, ["P1", "P2"])
    out = gc.abc_whitespace(edges, provenance=prov)
    g = [x for x in out if {x["a"], x["c"]} == {"fish oil", "raynaud"}][0]
    assert g["paper_scope"] == "cross"

def test_abc_whitespace_intra_paper_same_doc_is_intra_and_excludable():
    # A,B,C all co-occur in ONE paper -> the (A,C) gap is a same-paper artifact
    intra_lists = [["a", "b", "c"], ["b", "d"]]   # a-b,b-c,a-c? a-c present in doc1 -> not a gap; use a,b,c minus a-c
    # Build edges WITHOUT a direct a-c: give doc1 = a,b and b,c via two concept sub-lists sharing paper P1
    lists = [["a", "b"], ["b", "c"]]
    prov = {frozenset({"a", "b"}): {"P1"}, frozenset({"b", "c"}): {"P1"}}
    edges = [["a", "b"], ["b", "c"]]
    out = gc.abc_whitespace(edges, provenance=prov)
    g = [x for x in out if {x["a"], x["c"]} == {"a", "c"}][0]
    assert g["paper_scope"] == "intra"
    assert gc.abc_whitespace(edges, provenance=prov, exclude_intra=True) == []

def test_abc_whitespace_provenance_none_is_unchanged():
    edges = [["fish oil", "blood viscosity"], ["blood viscosity", "raynaud"]]
    out = gc.abc_whitespace(edges)
    assert out == [{"a": "fish oil", "c": "raynaud", "bridges": ["blood viscosity"]}]
    assert "paper_scope" not in out[0]

def test_bridge_overlap_relatedness_rewards_shared_nonhub_bridges():
    prov = {frozenset({"fish oil", "blood viscosity"}): {"P1", "P3"},
            frozenset({"blood viscosity", "raynaud"}): {"P2"}}
    rel = gc.bridge_overlap_relatedness(prov)
    r = rel("fish oil", "raynaud")     # shared bridge "blood viscosity", weight = 2 + 1 = 3
    assert r > 0.0 and abs(r - (1 - 1/(1 + 3))) < 1e-9
    assert rel("fish oil", "unrelated") == 0.0

def test_bridge_overlap_relatedness_excludes_hub_bridges():
    prov = {frozenset({"a", "hub"}): {"P1"}, frozenset({"hub", "c"}): {"P2"}}
    rel = gc.bridge_overlap_relatedness(prov, hub_bridges=frozenset({"hub"}))
    assert rel("a", "c") == 0.0   # only bridge is a hub -> no cross-lit signal

def test_topic_aware_hub_keeps_cross_topic_bridge_excludes_intra_topic_hub():
    # "blood viscosity" spans 2 topics with modest intra-topic degree; "assay" is a big single-topic hub
    cmap = {
        "blood viscosity": {"raynaud": 2, "fishoil": 2},   # max intra-topic degree = 2 (spanning)
        "assay":           {"hematology": 9},               # max intra-topic degree = 9 (single-topic hub)
        "x": {"raynaud": 1}, "y": {"fishoil": 1}, "z": {"hematology": 1},
    }
    hubs = gc.topic_aware_hub_bridges(edges=None, doc_of_concept_topic=cmap, percentile=0.90)
    assert "assay" in hubs and "blood viscosity" not in hubs


def test_cross_paper_bridge_strength_counts_cross_paper_evidence():
    prov = {frozenset({"fish oil", "blood viscosity"}): {"P1", "P3"},
            frozenset({"blood viscosity", "raynaud"}): {"P2"}}
    gap = {"a": "fish oil", "c": "raynaud", "bridges": ["blood viscosity"]}
    # cross-paper (P1/P3 vs P2) -> union {P1,P3,P2} size 3
    assert gc.cross_paper_bridge_strength(gap, prov) == 3

def test_cross_paper_bridge_strength_zero_for_same_paper_only():
    prov = {frozenset({"a", "b"}): {"P1"}, frozenset({"b", "c"}): {"P1"}}
    gap = {"a": "a", "c": "c", "bridges": ["b"]}
    assert gc.cross_paper_bridge_strength(gap, prov) == 0   # same single paper -> not cross-paper evidence

def test_cross_paper_bridge_strength_excludes_hub_bridges():
    prov = {frozenset({"a", "hub"}): {"P1"}, frozenset({"hub", "c"}): {"P2"}}
    gap = {"a": "a", "c": "c", "bridges": ["hub"]}
    assert gc.cross_paper_bridge_strength(gap, prov, hub_bridges=frozenset({"hub"})) == 0


def test_strip_check_tags_removes_generic_index_tags():
    concepts = ["Raynaud Disease", "Humans", "Male", "Aged", "Rats, Inbred Strains",
                "Platelet Aggregation", "Animals", "Middle Aged", "Blood Viscosity"]
    out = gc.strip_check_tags([c.lower() for c in concepts])
    assert out == ["raynaud disease", "platelet aggregation", "blood viscosity"]

def test_strip_check_tags_preserves_order_and_unknown_terms():
    assert gc.strip_check_tags(["fish oils", "humans", "eicosapentaenoic acid"]) == ["fish oils", "eicosapentaenoic acid"]


def test_cross_paper_gaps_ranked_orders_by_strength_and_is_answer_blind():
    # two cross-paper gaps: (x,z) bridged by b1 (P1/P2) + b2 (P3/P4) => strength 4; (x,w) bridged only by b1 => 2.
    # Note: {b1,b2} is also a legitimate answer-blind gap bridged by {x,z} at the same strength (the fixture is a
    # symmetric 4-cycle) -> both strength-4 pairs sort ahead of the strength-2 pairs, and the documented (a,c)
    # lexicographic tiebreak (b1 < x) puts {b1,b2} first among them.
    lists = [["x","b1"],["b1","z"],["x","b2"],["b2","z"],["x","b1_w"],["b1_w","w"]]
    ids   = ["P1","P2","P3","P4","P5","P6"]
    edges = gc.cooccurrence_edges_from_concepts(lists)
    prov = gc.cooccurrence_provenance(lists, ids)
    ranked = gc.cross_paper_gaps_ranked(edges, prov)
    top_strengths = [g["strength"] for g in ranked[:2]]
    top_pairs = [{g["a"], g["c"]} for g in ranked[:2]]
    assert top_strengths == [4, 4]
    assert {"x", "z"} in top_pairs and {"b1", "b2"} in top_pairs
    # (a,c) lexicographic tiebreak among equal-strength pairs, per the documented public ordering contract
    assert (ranked[0]["a"], ranked[0]["c"]) < (ranked[1]["a"], ranked[1]["c"])
    assert all("strength" in g for g in ranked)
    # answer-blind: no pair with a direct edge appears
    assert all(not (g["c"] in _adj(edges).get(g["a"], set())) for g in ranked)

def _adj(edges):
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    return adj

def test_cross_paper_gaps_ranked_excludes_hub_only_and_intra_gaps():
    # (a,c) bridged ONLY by a hub -> excluded; (p,q) bridged only within one paper -> excluded
    lists = [["a","hub"],["hub","c"],["p","b3"],["b3","q"]]
    ids = ["D1","D2","D3","D3"]   # p-b3 and b3-q BOTH in D3 -> intra
    edges = gc.cooccurrence_edges_from_concepts(lists)
    prov = gc.cooccurrence_provenance(lists, ids)
    ranked = gc.cross_paper_gaps_ranked(edges, prov, hub_bridges=frozenset({"hub"}))
    keys = {frozenset({g["a"], g["c"]}) for g in ranked}
    assert frozenset({"a","c"}) not in keys      # hub-only bridge -> excluded
    assert frozenset({"p","q"}) not in keys       # intra-paper only -> excluded

def test_cross_paper_gaps_ranked_accepts_strength_fn_and_default_is_unchanged():
    lists = [["x","b1"],["b1","z"],["x","b2"],["b2","z"]]
    ids = ["P1","P2","P3","P4"]
    edges = gc.cooccurrence_edges_from_concepts(lists)
    prov = gc.cooccurrence_provenance(lists, ids)
    base = gc.cross_paper_gaps_ranked(edges, prov)
    # a custom strength_fn that returns a constant reorders nothing but proves the seam is used
    same = gc.cross_paper_gaps_ranked(edges, prov, strength_fn=lambda g, p, h: gc.cross_paper_bridge_strength(g, p, hub_bridges=h))
    assert [ (g["a"],g["c"],g["strength"]) for g in base ] == [ (g["a"],g["c"],g["strength"]) for g in same ]
    # a custom POSITIVE strength_fn is actually invoked: every gap takes its score (surviving the min_strength
    # filter), and the SAME pairs surface (the seam changes scores, not which gaps) -> proves strength_fn is used
    seam = gc.cross_paper_gaps_ranked(edges, prov, strength_fn=lambda g, p, h: 7)
    assert seam and all(g["strength"] == 7 for g in seam)
    assert {(g["a"], g["c"]) for g in seam} == {(g["a"], g["c"]) for g in base}

import math as _math
def test_specificity_weighted_downweights_high_degree_bridges():
    prov = {frozenset({"a","spec"}): {"P1"}, frozenset({"spec","c"}): {"P2"},
            frozenset({"a","gen"}):  {"P1"}, frozenset({"gen","c"}):  {"P2"}}
    gap = {"a":"a","c":"c","bridges":["spec","gen"]}
    degrees = {"spec": 2, "gen": 50}         # gen is generic (high degree)
    s = gc.specificity_weighted_bridge_strength(gap, prov, degrees, n_concepts=1000)
    # each bridge union_size = 2 (P1,P2 cross-paper); idf(spec) >> idf(gen)
    idf_spec = _math.log2(1 + 1000/2); idf_gen = _math.log2(1 + 1000/50)
    assert abs(s - (2*idf_spec + 2*idf_gen)) < 1e-9 and idf_spec > idf_gen

def test_specificity_strength_fn_matches_and_is_usable_by_ranker():
    lists = [["a","spec"],["spec","c"],["a","gen"],["gen","c"]]
    ids = ["P1","P2","P3","P4"]
    edges = gc.cooccurrence_edges_from_concepts(lists)
    prov = gc.cooccurrence_provenance(lists, ids)
    degrees = gc.concept_degrees(edges); nconc = len({x for l in lists for x in l})
    fn = gc.specificity_strength_fn(degrees, nconc)
    ranked = gc.cross_paper_gaps_ranked(edges, prov, strength_fn=fn)
    assert any({g["a"],g["c"]}=={"a","c"} for g in ranked)

def test_pair_rank_and_beats_percentile():
    ranked = [{"a":"malaria","c":"psoriasis","strength":777},
              {"a":"eicosapentaenoic acid","c":"raynaud disease","strength":294},
              {"a":"x","c":"y","strength":10}]
    r = gc.pair_rank(ranked, {"eicosapentaenoic acid","fish oils"}, {"raynaud disease"})
    assert r["rank"] == 2 and r["strength"] == 294
    assert gc.beats_percentile(300, [10, 100, 294], 95.0) is True
    assert gc.beats_percentile(50, [10, 100, 294], 95.0) is False

def test_crosslit_verdict_void_kill_pass():
    tgt = {"rank":2, "strength":294, "a":"epa", "c":"raynaud"}
    # VOID: pool too small
    assert gc.crosslit_verdict(tgt, [10], [10,20], pool_size=5)["verdict"] == "VOID"
    # KILL: a hard-negative out-scores the target
    assert gc.crosslit_verdict(tgt, [777], [10,20,30], pool_size=100)["verdict"] == "KILL"
    # PASS: beats all hard-negs + the null 95th pct
    assert gc.crosslit_verdict(tgt, [100,120], [10,20,30,40], pool_size=100)["verdict"] == "PASS"
    # VOID: target absent
    assert gc.crosslit_verdict(None, [1], [1], pool_size=100)["verdict"] == "VOID"

import math as _m
def test_hypergeom_sf_matches_known_values():
    # X~Hypergeom(N=50,K=10,n=10); P(X>=0)=1; P(X>=1)=1-C(40,10)/C(50,10)
    assert abs(gc.hypergeom_sf(0, 50, 10, 10) - 1.0) < 1e-9
    p1 = gc.hypergeom_sf(1, 50, 10, 10)
    exp = 1.0 - _m.exp(_m.lgamma(41)-_m.lgamma(11)-_m.lgamma(31) - (_m.lgamma(51)-_m.lgamma(11)-_m.lgamma(41)))
    assert abs(p1 - exp) < 1e-9
    assert gc.hypergeom_sf(11, 50, 10, 10) == 0.0   # can't draw 11 successes in 10 draws
    # big overlap is highly significant (small p)
    assert gc.hypergeom_sf(8, 1000, 10, 10) < 1e-6

def test_pair_bridge_count_counts_nonhub_crosspaper_bridges():
    prov = {frozenset({"a","b1"}):{"P1"}, frozenset({"b1","c"}):{"P2"},   # b1 cross-paper
            frozenset({"a","b2"}):{"P3"}, frozenset({"b2","c"}):{"P3"},   # b2 SAME paper -> intra
            frozenset({"a","hub"}):{"P4"}, frozenset({"hub","c"}):{"P5"}} # hub -> excluded
    gap = {"a":"a","c":"c","bridges":["b1","b2","hub"]}
    assert gc.pair_bridge_count(gap, prov, hub_bridges=frozenset({"hub"})) == 1   # only b1

def test_association_strength_and_cosine_downweight_high_degree_endpoints():
    prov = {frozenset({"a","b"}):{"P1"}, frozenset({"b","c"}):{"P2"}}   # c_AC = 1 (b cross-paper)
    gap = {"a":"a","c":"c","bridges":["b"]}
    deg_small = {"a":5, "c":5}; deg_big = {"a":100, "c":100}
    as_fn_s = gc.association_strength_fn(deg_small); as_fn_b = gc.association_strength_fn(deg_big)
    s_small = as_fn_s(gap, prov, frozenset()); s_big = as_fn_b(gap, prov, frozenset())
    assert abs(s_small - 1/25) < 1e-9 and abs(s_big - 1/10000) < 1e-9 and s_small > s_big   # size penalized
    cos_s = gc.salton_cosine_fn(deg_small)(gap, prov, frozenset())
    assert abs(cos_s - 1/5.0) < 1e-9   # 1/sqrt(25)
    assert gc.association_strength_fn({"a":0,"c":5})(gap, prov, frozenset()) == 0.0   # degree 0 guard

def test_hub_share_fraction_flags_high_degree_bridges():
    prov = {frozenset({"a","lo"}):{"P1"}, frozenset({"lo","c"}):{"P2"},
            frozenset({"a","hi"}):{"P3"}, frozenset({"hi","c"}):{"P4"}}
    gap = {"a":"a","c":"c","bridges":["lo","hi"]}
    degrees = {"lo":2, "hi":50}
    frac = gc.hub_share_fraction(gap, prov, degrees, hub_degree_quantile_value=10)
    assert abs(frac - 0.5) < 1e-9   # 1 of 2 bridges (hi) is high-degree
