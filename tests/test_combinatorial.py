import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import combinatorial as cb

def test_parse_combinations_normalizes_and_assigns_ids():
    out = cb.parse_combinations([
        {"domain_a": "immunology", "domain_b": "distributed systems", "mechanism": "circuit breaker",
         "claim": "model cytokine storms as cascading failures"},
        {"domain_a": "x", "domain_b": "y", "mechanism": "m"}])     # claim absent -> "" allowed at parse
    assert out[0]["id"] == "c1" and out[0]["domain_a"] == "immunology"
    assert out[1]["id"] == "c2" and out[1]["claim"] == ""

def test_parse_combinations_tolerates_json_string_envelope_and_drops_incomplete():
    env = json.dumps({"combinations": [
        {"domain_a": "a", "domain_b": "b", "mechanism": "m", "claim": "c"},
        {"domain_a": "only-a"}]})                                   # missing domain_b/mechanism -> dropped
    out = cb.parse_combinations(env)
    assert [c["domain_a"] for c in out] == ["a"]
    assert cb.parse_combinations(None) == [] and cb.parse_combinations(42) == []

def test_structural_coherence_kills_degenerates():
    ok = {"domain_a": "immunology", "domain_b": "distributed systems", "mechanism": "circuit breaker", "claim": "x"}
    assert cb.structural_coherence(ok) is True
    assert cb.structural_coherence({"domain_a": "x", "domain_b": "x", "mechanism": "m", "claim": "c"}) is False  # same domain
    assert cb.structural_coherence({"domain_a": "x", "domain_b": "y", "mechanism": "", "claim": "c"}) is False   # no mechanism
    assert cb.structural_coherence({"domain_a": "", "domain_b": "y", "mechanism": "m", "claim": "c"}) is False   # empty domain

def test_creativity_score_is_multiplicative_and_clamped():
    assert cb.creativity_score(0.8, 0.5) == 0.4
    assert cb.creativity_score(0.9, 0.0) == 0.0      # incoherent/useless -> ~0 even if novel
    assert cb.creativity_score(0.0, 0.9) == 0.0      # trivial -> ~0 even if useful
    assert cb.creativity_score(1.5, 2.0) == 1.0      # clamped into [0,1]
    assert cb.creativity_score(-1.0, 0.5) == 0.0     # clamped

def test_combination_descriptor_order_normalizes_the_pair():
    c1 = {"domain_a": "Immunology", "domain_b": "Distributed Systems", "mechanism": "Circuit Breaker", "claim": "x"}
    c2 = {"domain_a": "distributed systems", "domain_b": "immunology", "mechanism": "circuit breaker", "claim": "y"}
    # (X,Y) and (Y,X) are the SAME combination -> same descriptor (pair sorted, normalized)
    assert cb.combination_descriptor(c1) == cb.combination_descriptor(c2)
    da, db, mech = cb.combination_descriptor(c1)
    assert da <= db                                   # sorted pair

def test_cell_index_deterministic_finite_grid():
    d = ("immunology", "distributed systems", "circuit breaker")
    cell = cb.cell_index(d, bins=16)
    assert cell == cb.cell_index(d, bins=16)          # deterministic
    assert len(cell) == 3 and all(0 <= x < 16 for x in cell)
    # near-identical-after-normalization descriptors co-locate
    assert cb.cell_index(("A", "B", "M")) == cb.cell_index(("a", "b", " m "))

def test_admit_keeps_highest_creativity_elite_per_cell_pure():
    arch = {}
    arch = cb.admit(arch, cell=(1, 2, 3), candidate={"id": "c1"}, creativity=0.4)
    assert arch[(1, 2, 3)]["creativity"] == 0.4 and arch[(1, 2, 3)]["candidate"]["id"] == "c1"
    # lower creativity in the same cell -> NOT replaced
    arch2 = cb.admit(arch, cell=(1, 2, 3), candidate={"id": "c2"}, creativity=0.2)
    assert arch2[(1, 2, 3)]["candidate"]["id"] == "c1"
    # higher -> replaced; input archive not mutated (pure)
    arch3 = cb.admit(arch2, cell=(1, 2, 3), candidate={"id": "c3"}, creativity=0.9)
    assert arch3[(1, 2, 3)]["candidate"]["id"] == "c3"
    assert arch[(1, 2, 3)]["candidate"]["id"] == "c1"          # original untouched

def test_coverage_and_qd_score():
    arch = {}
    arch = cb.admit(arch, cell=(0, 0, 0), candidate={"id": "a"}, creativity=0.5)
    arch = cb.admit(arch, cell=(1, 1, 1), candidate={"id": "b"}, creativity=0.3)
    assert cb.qd_score(arch) == 0.8
    assert cb.coverage(arch, bins=16) == 2 / (16 ** 3)
    assert [e["id"] for e in cb.elites(arch)] == ["a", "b"] or {e["id"] for e in cb.elites(arch)} == {"a", "b"}

def test_propose_prompt_forces_analogical_mapping_not_free_association():
    p = cb.propose_prompt("immunology", "distributed systems", n=3)
    assert "immunology" in p and "distributed systems" in p
    assert "relational" in p.lower() and "STRICT JSON" in p
    assert "do not free-associate" in p.lower() or "not free-associate" in p.lower()
    for key in ("domain_a", "domain_b", "mechanism", "claim"):
        assert key in p

def test_judge_prompt_is_retrieval_grounded_not_unanchored():
    c = {"domain_a": "a", "domain_b": "b", "mechanism": "m", "claim": "claimX"}
    p = cb.judge_prompt(c, ["prior work 1 (arXiv:1234.5678)", "prior work 2"])
    assert "claimX" in p and "prior work 1 (arXiv:1234.5678)" in p
    assert "nearest" in p.lower() and "STRICT JSON" in p
    # must NOT invite a free-form 'is this novel?' — it judges AGAINST retrieved art
    assert "retrieved" in p.lower()

def test_partition_fleet_disjoint_proposer_and_judge():
    models = [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}, {"id": "m4"}]
    part = cb.partition_fleet(models, judge_ids=["m3", "m4"])
    assert {m["id"] for m in part["judge_pool"]} == {"m3", "m4"}
    assert {m["id"] for m in part["proposer_pool"]} == {"m1", "m2"}
    # no model is in both pools (the load-bearing invariant)
    assert not ({m["id"] for m in part["proposer_pool"]} & {m["id"] for m in part["judge_pool"]})
    # default fraction split also disjoint + non-empty
    auto = cb.partition_fleet(models, judge_fraction=0.5)
    assert auto["proposer_pool"] and auto["judge_pool"]
    assert not ({m["id"] for m in auto["proposer_pool"]} & {m["id"] for m in auto["judge_pool"]})

def test_run_round_pipeline_with_injected_scorers():
    combos = [
        {"id": "c1", "domain_a": "immunology", "domain_b": "distributed systems", "mechanism": "circuit breaker", "claim": "good"},
        {"id": "c2", "domain_a": "x", "domain_b": "x", "mechanism": "m", "claim": "degenerate"},   # incoherent -> rejected pre-judge
        {"id": "c3", "domain_a": "music", "domain_b": "protein folding", "mechanism": "harmony", "claim": "novel-useless"}]
    novelty = {"c1": 0.9, "c3": 0.9}
    utility = {"c1": 0.8, "c3": 0.0}                  # c3 useless -> creativity 0 -> NOT archived
    res = cb.run_round(combos, novelty_fn=lambda c: novelty.get(c["id"], 0.0),
                       utility_fn=lambda c: utility.get(c["id"], 0.0))
    assert "c2" in res["rejected_incoherent"]         # degenerate killed before scoring
    admitted_ids = {a["candidate"]["id"] for a in res["archive"].values()}
    assert "c1" in admitted_ids                       # creativity 0.72 -> archived
    assert "c3" in res["zero_value"]                  # creativity 0 -> NOT archived, recorded in zero_value
    assert "c1" in {a["id"] for a in res["admitted"]}
    assert res["report"]["qd_score"] >= 0.72          # only c1 contributes

def test_archive_report_is_honest_about_qd_score_and_survival():
    arch = cb.admit({}, cell=(0, 0, 0), candidate={"id": "a"}, creativity=0.6)
    rep = cb.archive_report(arch, bins=16, grounded_survivors=["a"])
    assert rep["qd_score"] == 0.6 and rep["n_elites"] == 1
    assert rep["qd_score_is_upper_bound"] is True                 # labeled, not a discovery count
    assert rep["post_grounding_survival_rate"] == 1.0
    rep0 = cb.archive_report(arch, bins=16)                       # no grounding data
    assert rep0["post_grounding_survival_rate"] is None           # honestly undefined, not faked

def test_partition_fleet_boundary_errors():
    import pytest
    models = [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]
    with pytest.raises(ValueError): cb.partition_fleet(models, judge_ids=["nope"])      # matches nothing
    with pytest.raises(ValueError): cb.partition_fleet(models, judge_ids=["m1","m2","m3"])  # all judges -> no proposers
    with pytest.raises(ValueError): cb.partition_fleet([{"id": "only"}])                 # <2 models
    with pytest.raises(ValueError): cb.partition_fleet([])                                # empty

def test_admit_does_not_alias_candidate():
    cand = {"id": "c1", "claim": "x"}
    arch = cb.admit({}, cell=(0,0,0), candidate=cand, creativity=0.5)
    cand["claim"] = "MUTATED"
    assert arch[(0,0,0)]["candidate"]["claim"] == "x"   # archive holds a copy, not a reference
