import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n1_novelty as n1

def test_local_density_inverse_mean_distance():
    # closer neighbors -> higher density
    near = n1.local_density([0.1, 0.1, 0.2])
    far = n1.local_density([1.0, 1.2, 0.8])
    assert near > far
    assert n1.local_density([]) == 0.0          # no neighbors -> maximally sparse

def test_relative_neighbor_density_is_fraction_of_denser_neighbors():
    # candidate sparser (lower density) than most neighbors -> high novelty
    assert n1.relative_neighbor_density(0.1, [0.5, 0.6, 0.7, 0.8]) == 1.0
    # candidate denser than all neighbors -> not novel
    assert n1.relative_neighbor_density(0.9, [0.1, 0.2, 0.3]) == 0.0
    # half denser
    assert n1.relative_neighbor_density(0.5, [0.4, 0.6, 0.7, 0.3]) == 0.5
    assert n1.relative_neighbor_density(0.5, []) == 1.0          # no neighbors -> fully novel

def test_rnd_novelty_composed_relative_density():
    # candidate is in a SPARSE region but its neighbors are DENSE -> genuinely novel -> high
    cand = [0.9, 1.0, 1.1]                                  # far from its own neighbors (sparse)
    neigh = [[0.1, 0.1, 0.1], [0.1, 0.2, 0.1], [0.2, 0.1, 0.1]]  # each neighbor is in a dense cluster
    assert n1.rnd_novelty(cand, neigh) == 1.0
    # GOODHART-RESISTANCE: candidate sparse AND its neighbors equally sparse -> NOT falsely novel (moderate/low)
    cand2 = [0.9, 1.0, 1.1]
    neigh2 = [[0.9, 1.0, 1.1], [1.0, 0.9, 1.1], [1.1, 1.0, 0.9]]  # neighbors equally sparse
    assert n1.rnd_novelty(cand2, neigh2) < 1.0


def _euclid(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

def test_inmemory_index_knn_enforces_date_cutoff():
    entries = [{"id": "old1", "vec": [0.0, 0.0], "date": "2020-01-01"},
               {"id": "old2", "vec": [0.1, 0.0], "date": "2021-01-01"},
               {"id": "future", "vec": [0.0, 0.05], "date": "2030-01-01"}]   # must be EXCLUDED by cutoff
    idx = n1.InMemoryN1Index(entries, distance_fn=_euclid)
    cand_dists, neigh_dists_list = idx.knn([0.0, 0.0], k=2, date_cutoff="2026-01-01")
    # only the 2 pre-cutoff entries are eligible; the future one is excluded
    assert len(cand_dists) == 2
    assert len(neigh_dists_list) == 2          # each eligible neighbor gets its own kNN distance list

def test_inmemory_index_knn_requires_date_cutoff():
    idx = n1.InMemoryN1Index([{"id": "a", "vec": [0.0], "date": "2020-01-01"}], distance_fn=_euclid)
    import pytest
    with pytest.raises(TypeError):
        idx.knn([0.0], k=1)                    # date_cutoff is REQUIRED (keyword-only, no default)

def test_external_novelty_end_to_end_advisory():
    # candidate far from a tight cluster -> novel (high). All entries pre-cutoff.
    entries = [{"id": f"c{i}", "vec": [0.0, float(i) * 0.01], "date": "2020-01-01"} for i in range(6)]
    idx = n1.InMemoryN1Index(entries, distance_fn=_euclid)
    near = n1.external_novelty([0.0, 0.02], idx, k=3, date_cutoff="2026-01-01")   # inside the cluster
    far = n1.external_novelty([5.0, 5.0], idx, k=3, date_cutoff="2026-01-01")     # far outside
    assert 0.0 <= near <= 1.0 and 0.0 <= far <= 1.0
    assert far >= near


def test_goodhart_distance_inflation_does_not_beat_relative_density():
    # NON-VACUOUS Goodhart test: the two cases must produce DISTINCT, meaningful values (NOT both 1.0).
    #
    # Case A — "distance-inflation into a COVERED sparse region":
    #   corpus spread sparsely (x = 0,10,20,30,40,50,60); query at x=35 sits AMONG them in the sparse region.
    #   Its neighbors are themselves sparse, so it scores STRICTLY LESS than 1.0 (relative density catches it).
    sparse_entries = [{"id": f"s{i}", "vec": [float(i * 10), 0.0], "date": "2020-01-01"} for i in range(7)]
    idx_sparse = n1.InMemoryN1Index(sparse_entries, distance_fn=_euclid)
    attacker_in_sparse_covered = n1.external_novelty([35.0, 0.0], idx_sparse, k=3, date_cutoff="2026-01-01")
    #
    # Case B — "genuine novelty far from a DENSE cluster":
    #   tight cluster at x = 0,0.1,0.2,0.3,0.4; query at x=50 is far from dense neighbors -> scores high (≈1.0).
    dense_entries = [{"id": f"d{i}", "vec": [float(i) * 0.1, 0.0], "date": "2020-01-01"} for i in range(5)]
    idx_dense = n1.InMemoryN1Index(dense_entries, distance_fn=_euclid)
    genuine_far_from_dense = n1.external_novelty([50.0, 0.0], idx_dense, k=3, date_cutoff="2026-01-01")
    #
    # Both values are printed implicitly if the test fails; they must be DISTINCT (attacker < genuine).
    # attacker_in_sparse_covered is among equally-sparse neighbors -> fraction denser < 1.0
    # genuine_far_from_dense is far from a dense cluster -> all neighbors denser -> = 1.0
    assert attacker_in_sparse_covered < genuine_far_from_dense


def test_external_novelty_single_entry_corpus_is_novel_not_zero():
    idx = n1.InMemoryN1Index([{"id": "only", "vec": [0.0, 0.0], "date": "2020-01-01"}], distance_fn=_euclid)
    score = n1.external_novelty([1.0, 1.0], idx, k=3, date_cutoff="2026-01-01")
    assert score == 1.0          # one anchor, no relative comparison possible -> novel (NOT the old inverted 0.0)


import math as _math

def test_cosine_distance_identical_orthogonal_opposite():
    assert n1.cosine_distance([1.0, 0.0], [1.0, 0.0]) == 0.0          # identical -> 0
    assert abs(n1.cosine_distance([1.0, 0.0], [0.0, 1.0]) - 1.0) < 1e-9  # orthogonal -> 1
    assert n1.cosine_distance([1.0, 0.0], [-1.0, 0.0]) == 1.0         # opposite -> clamped to 1 (matches faiss 1-IP clamp)
    assert n1.cosine_distance([], [1.0]) == 1.0                       # empty / mismatched -> 1
    assert n1.cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0          # zero-norm -> 1

def test_cosine_distance_magnitude_invariant():
    # cosine ignores magnitude
    assert abs(n1.cosine_distance([2.0, 0.0], [5.0, 0.0])) < 1e-9

def test_corpus_loo_nn_distances_leave_one_out():
    vecs = [[0.0, 0.0], [0.0, 1.0], [10.0, 10.0]]
    loo = n1.corpus_loo_nn_distances(vecs, distance_fn=_euclid)
    # nearest other for [0,0] is [0,1] (d=1); for [0,1] is [0,0] (d=1); for [10,10] is [0,1] (d~12.7)
    assert len(loo) == 3
    assert abs(loo[0] - 1.0) < 1e-9 and abs(loo[1] - 1.0) < 1e-9
    assert loo[2] > 5.0
    assert n1.corpus_loo_nn_distances([], distance_fn=_euclid) == []
    assert n1.corpus_loo_nn_distances([[1.0]], distance_fn=_euclid) == []   # singleton -> no neighbor

def test_corpus_nn_percentile_threshold_nearest_rank():
    d = [float(i) for i in range(1, 101)]          # 1..100
    # nearest-rank ceil(0.95*100)-1 = 94 -> value 95.0 ; exactly 5 values (96..100) EXCEED it
    assert n1.corpus_nn_percentile_threshold(d, percentile=0.95) == 95.0
    assert sum(1 for x in d if x > 95.0) == 5
    # N=101: ceil(0.95*101)-1 = 96-1 = 95 -> value 96.0
    d2 = [float(i) for i in range(1, 102)]
    assert n1.corpus_nn_percentile_threshold(d2, percentile=0.95) == 96.0
    assert n1.corpus_nn_percentile_threshold([], percentile=0.95) is None    # empty -> None
    assert n1.corpus_nn_percentile_threshold([7.0], percentile=0.95) == 7.0  # clamp to [0,N-1]
    assert n1.corpus_nn_percentile_threshold([3.0, 1.0, 2.0], percentile=0.0) == 1.0  # p=0 -> smallest

def test_high_tail_cap_threshold_logic():
    # nearest distance under threshold -> not off-distribution
    r = n1.high_tail_cap([0.2, 0.5, 0.7], off_distribution_threshold=0.4)
    assert r["off_distribution"] is False
    # nearest distance over threshold -> off-distribution (out of corpus)
    r = n1.high_tail_cap([0.6, 0.8], off_distribution_threshold=0.4)
    assert r["off_distribution"] is True
    # empty distances -> off-distribution (no eligible neighbors)
    assert n1.high_tail_cap([], off_distribution_threshold=0.4)["off_distribution"] is True
    # None threshold -> advisory, never flags
    r = n1.high_tail_cap([0.9, 0.95], off_distribution_threshold=None)
    assert r["off_distribution"] is False and "uncalibrated" in r["reason"]

def _fp(**kw):
    base = {"name": "allenai/specter2_base", "revision": "abc123",
            "query_adapter": "allenai/specter2_adhoc_query", "doc_adapter": "allenai/specter2",
            "dim": 768, "normalize": "l2", "metric": "cosine"}
    base.update(kw)
    return base

def test_fingerprint_match_strict():
    assert n1.fingerprint_match(_fp(), _fp()) is True
    assert n1.fingerprint_match(_fp(), _fp(revision="zzz")) is False          # revision drift
    assert n1.fingerprint_match(_fp(), _fp(doc_adapter="other")) is False     # adapter drift
    bad = _fp(); del bad["dim"]
    assert n1.fingerprint_match(bad, _fp()) is False                          # missing field
    extra = _fp(); extra["foo"] = 1
    assert n1.fingerprint_match(extra, _fp()) is False                        # extra field
    assert n1.fingerprint_match({}, _fp()) is False
    assert n1.fingerprint_match("nope", _fp()) is False                       # non-dict

def test_inmemory_cite_nearest_returns_id_title_distance():
    entries = [{"id": "a", "title": "Alpha", "vec": [0.0, 0.0], "date": "2020-01-01"},
               {"id": "b", "title": "Beta",  "vec": [1.0, 0.0], "date": "2020-01-01"},
               {"id": "f", "title": "Future","vec": [0.0, 0.0], "date": "2030-01-01"}]  # excluded by cutoff
    idx = n1.InMemoryN1Index(entries, distance_fn=_euclid)
    cite = idx.cite_nearest([0.05, 0.0], date_cutoff="2026-01-01")
    assert cite["id"] == "a" and cite["title"] == "Alpha"
    assert cite["distance"] < 0.1
    # no eligible -> None
    idx2 = n1.InMemoryN1Index([{"id": "f", "vec": [0.0], "date": "2030-01-01"}], distance_fn=_euclid)
    assert idx2.cite_nearest([0.0], date_cutoff="2026-01-01") is None

def test_external_novelty_capped_composes_score_cap_and_citation():
    # A non-degenerate tight CLUSTER of unit vectors (6 papers within a 25-degree arc) so cosine distances are
    # meaningful (not all 0/1) and the OOD threshold sits well below 1.0 (here ~1-cos(5 deg)).
    angles = [0, 5, 10, 15, 20, 25]
    entries = [{"id": f"c{i}", "title": f"T{i}",
                "vec": [_math.cos(_math.radians(a)), _math.sin(_math.radians(a))], "date": "2020-01-01"}
               for i, a in enumerate(angles)]
    idx = n1.InMemoryN1Index(entries, distance_fn=n1.cosine_distance)
    loo = n1.corpus_loo_nn_distances([e["vec"] for e in entries], distance_fn=n1.cosine_distance)
    thr = n1.corpus_nn_percentile_threshold(loo, percentile=0.95)
    # in-cluster query -> score in range, NOT off-distribution (nearest distance < threshold), cites a neighbor
    q_in = [_math.cos(_math.radians(12)), _math.sin(_math.radians(12))]
    res = n1.external_novelty_capped(q_in, idx, k=3, date_cutoff="2026-01-01", off_distribution_threshold=thr)
    assert 0.0 <= res["score"] <= 1.0
    assert res["nearest"] is not None and "id" in res["nearest"]
    assert res["off_distribution"] is False
    # opposite-direction query is genuinely out of corpus -> off_distribution flagged (strict > threshold)
    q_out = [_math.cos(_math.radians(200)), _math.sin(_math.radians(200))]
    res2 = n1.external_novelty_capped(q_out, idx, k=3, date_cutoff="2026-01-01", off_distribution_threshold=thr)
    assert res2["off_distribution"] is True

def test_external_novelty_capped_empty_pool_is_novel():
    idx = n1.InMemoryN1Index([{"id": "f", "vec": [0.0], "date": "2030-01-01"}], distance_fn=n1.cosine_distance)
    res = n1.external_novelty_capped([1.0], idx, k=3, date_cutoff="2026-01-01", off_distribution_threshold=0.5)
    assert res["score"] == 1.0 and res["off_distribution"] is True and res["nearest"] is None

def test_high_tail_cap_reports_nearest_distance():
    r = n1.high_tail_cap([0.6, 0.8], off_distribution_threshold=0.4)
    assert r["off_distribution"] is True and abs(r["nearest_distance"] - 0.6) < 1e-9
    r2 = n1.high_tail_cap([0.2, 0.5], off_distribution_threshold=0.4)
    assert r2["off_distribution"] is False and abs(r2["nearest_distance"] - 0.2) < 1e-9
    assert n1.high_tail_cap([], off_distribution_threshold=0.4)["nearest_distance"] is None
    # None threshold (uncalibrated) still reports the nearest distance, still advisory (never flags)
    r3 = n1.high_tail_cap([0.9, 0.95], off_distribution_threshold=None)
    assert r3["off_distribution"] is False and abs(r3["nearest_distance"] - 0.9) < 1e-9

def test_external_novelty_capped_includes_nearest_distance():
    entries = [{"id": "a", "title": "Alpha", "vec": [1.0, 0.0], "date": "2020-01-01"},
               {"id": "b", "title": "Beta", "vec": [0.0, 1.0], "date": "2020-01-01"}]
    idx = n1.InMemoryN1Index(entries, distance_fn=n1.cosine_distance)
    res = n1.external_novelty_capped([1.0, 0.0], idx, k=2, date_cutoff="2026-01-01", off_distribution_threshold=0.5)
    assert "nearest_distance" in res and res["nearest_distance"] is not None

def test_inmemory_query_calibrated_threshold_percentile():
    # corpus of 4 collinear points; 4 queries whose ids OVERLAP the corpus so exclude-self-by-id FIRES, leaving
    # nearest-OTHER-id distances {1,1,1,3} -> 95th pct (nearest-rank ceil(0.95*4)-1 = 3 -> sorted[3]) = 3.0.
    corpus = [{"id": "a", "vec": [0.0]}, {"id": "b", "vec": [1.0]}, {"id": "c", "vec": [2.0]}, {"id": "d", "vec": [3.0]}]
    idx = n1.InMemoryN1Index(corpus, distance_fn=_euclid)
    queries = [{"id": "a", "vec": [0.0]}, {"id": "b", "vec": [1.0]},      # share ids with corpus -> self excluded
               {"id": "c", "vec": [2.0]}, {"id": "far", "vec": [6.0]}]    # 'far' not in corpus -> nearest d at d=3
    thr = idx.query_calibrated_threshold(queries, percentile=0.95)
    assert abs(thr - 3.0) < 1e-9
    # empty queries -> None
    assert idx.query_calibrated_threshold([], percentile=0.95) is None

def test_query_calibrated_threshold_discriminates_where_corpus_loo_would_not():
    # THE REGRESSION-PROOF of the fix. A query regime where claim->paper distances (~0.5) are FAR larger than
    # paper->paper LOO distances (~0.1). The corpus-LOO threshold (~0.1) flags BOTH an in-distribution query and a
    # garbage query as off. The query-calibrated threshold (~0.5) flags ONLY the garbage one.
    corpus = [{"id": f"c{i}", "vec": [float(i) * 0.1, 0.0]} for i in range(6)]   # tight cluster, spacing 0.1
    idx = n1.InMemoryN1Index(corpus, distance_fn=_euclid)
    # corpus-LOO threshold (paper->paper): ~0.1
    loo = n1.corpus_loo_nn_distances([c["vec"] for c in corpus], distance_fn=_euclid)
    loo_thr = n1.corpus_nn_percentile_threshold(loo, percentile=0.95)
    # query reference: each corpus point displaced +0.5 in y (claim is ~0.5 from its nearest paper) -> query thr ~0.5
    qrefs = [{"id": f"c{i}", "vec": [float(i) * 0.1, 0.5]} for i in range(6)]
    q_thr = idx.query_calibrated_threshold(qrefs, percentile=0.95)
    assert q_thr > loo_thr                                   # query regime threshold is materially larger
    # an in-distribution query (displaced 0.5, like the reference) and a garbage query (displaced 5.0)
    in_q = n1.high_tail_cap([0.5], off_distribution_threshold=q_thr)
    garbage_q = n1.high_tail_cap([5.0], off_distribution_threshold=q_thr)
    assert in_q["off_distribution"] is False                # in-distribution claim now reads in-corpus
    assert garbage_q["off_distribution"] is True            # garbage still off
    # under the OLD corpus-LOO threshold BOTH would be off (the bug) — proving the fix changes behavior
    assert n1.high_tail_cap([0.5], off_distribution_threshold=loo_thr)["off_distribution"] is True

def test_query_regime_nn_distances_excludes_self_by_id():
    # query q0 shares id with corpus c0 (same vec); its nearest DIFFERENT-id corpus entry is c1 (d=1), not itself.
    corpus = [{"id": "c0", "vec": [0.0, 0.0]}, {"id": "c1", "vec": [0.0, 1.0]}, {"id": "c2", "vec": [9.0, 9.0]}]
    queries = [{"id": "c0", "vec": [0.0, 0.0]}]              # same id as c0 -> c0 excluded
    ds = n1.query_regime_nn_distances(queries, corpus, distance_fn=_euclid)
    assert len(ds) == 1
    assert abs(ds[0] - 1.0) < 1e-9                            # nearest OTHER-id is c1 at d=1, not c0 at d=0

def test_query_regime_nn_distances_cross_set_and_skips():
    corpus = [{"id": "a", "vec": [0.0, 0.0]}, {"id": "b", "vec": [10.0, 0.0]}]
    queries = [
        {"id": "qa", "vec": [0.5, 0.0]},                      # nearest = a (d=0.5)
        {"id": "qb", "vec": [9.0, 0.0]},                      # nearest = b (d=1.0)
        {"id": "nov", "vec": None},                           # missing vec -> skipped
    ]
    ds = n1.query_regime_nn_distances(queries, corpus, distance_fn=_euclid)
    assert len(ds) == 2
    assert abs(ds[0] - 0.5) < 1e-9 and abs(ds[1] - 1.0) < 1e-9
    # empty inputs
    assert n1.query_regime_nn_distances([], corpus, distance_fn=_euclid) == []
    assert n1.query_regime_nn_distances(queries, [], distance_fn=_euclid) == []
    # a query whose ONLY corpus match shares its id -> no eligible neighbor -> skipped
    only_self = n1.query_regime_nn_distances([{"id": "x", "vec": [0.0]}], [{"id": "x", "vec": [0.0]}],
                                             distance_fn=_euclid)
    assert only_self == []
