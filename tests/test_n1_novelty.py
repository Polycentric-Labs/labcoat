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
