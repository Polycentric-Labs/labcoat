import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import roc

def test_roc_auc_perfectly_separable():
    # OOD(label 1) all score higher than ID(label 0) -> AUC 1.0
    scores = [0.1, 0.2, 0.8, 0.9]; labels = [0, 0, 1, 1]
    assert roc.roc_auc(scores, labels) == 1.0

def test_roc_auc_inverted_is_zero():
    scores = [0.8, 0.9, 0.1, 0.2]; labels = [0, 0, 1, 1]
    assert roc.roc_auc(scores, labels) == 0.0

def test_roc_auc_ties_give_half_credit():
    # one ID and one OOD tie -> Mann-Whitney U counts a tie as 0.5
    scores = [0.5, 0.5]; labels = [0, 1]
    assert roc.roc_auc(scores, labels) == 0.5

def test_roc_auc_one_class_empty_returns_none():
    assert roc.roc_auc([0.1, 0.2], [0, 0]) is None
    assert roc.roc_auc([], []) is None

def test_operating_point_counts_predict_positive_above_threshold():
    scores = [0.1, 0.2, 0.8, 0.9]; labels = [0, 0, 1, 1]
    op = roc.operating_point(scores, labels, 0.5)   # predict OOD if score > 0.5
    assert op == {"tpr": 1.0, "fpr": 0.0}

def test_operating_point_threshold_flags_one_id():
    scores = [0.1, 0.6, 0.8, 0.9]; labels = [0, 0, 1, 1]
    op = roc.operating_point(scores, labels, 0.5)   # the 0.6 ID is falsely flagged
    assert op == {"tpr": 1.0, "fpr": 0.5}

def test_roc_points_monotone_endpoints():
    scores = [0.1, 0.2, 0.8, 0.9]; labels = [0, 0, 1, 1]
    pts = roc.roc_points(scores, labels)
    fprs = [p["fpr"] for p in pts]; tprs = [p["tpr"] for p in pts]
    assert min(fprs) == 0.0 and max(tprs) == 1.0
    assert pts == sorted(pts, key=lambda p: (p["fpr"], p["tpr"]))  # non-decreasing

def test_fpr_at_tpr95_perfect_separation_zero_fpr():
    scores = [0.1, 0.2, 0.3, 0.8, 0.9, 1.0]; labels = [0, 0, 0, 1, 1, 1]
    r = roc.fpr_at_tpr(scores, labels, tpr_target=0.95)
    assert r["tpr"] >= 0.95 and r["fpr"] == 0.0

def test_fpr_at_tpr95_picks_min_fpr_among_qualifying():
    # one OOD buried among ID forces some FPR to reach 95% recall
    scores = [0.1, 0.4, 0.6, 0.2, 0.5, 0.9]; labels = [0, 0, 0, 1, 1, 1]
    r = roc.fpr_at_tpr(scores, labels, tpr_target=0.95)
    assert r["tpr"] >= 0.95
    assert 0.0 <= r["fpr"] <= 1.0

def test_fpr_at_tpr_one_class_empty_returns_none():
    assert roc.fpr_at_tpr([0.1, 0.2], [1, 1], tpr_target=0.95) is None

def test_youden_threshold_maximizes_j():
    scores = [0.1, 0.2, 0.8, 0.9]; labels = [0, 0, 1, 1]
    r = roc.youden_threshold(scores, labels)
    assert r["j"] == 1.0 and r["tpr"] == 1.0 and r["fpr"] == 0.0
    assert 0.2 <= r["threshold"] < 0.8   # separating threshold

def test_youden_threshold_one_class_empty_none():
    assert roc.youden_threshold([0.1, 0.2], [0, 0]) is None

def test_auc_ci_seeded_reproducible_and_brackets_point():
    scores = [0.1, 0.15, 0.2, 0.25, 0.8, 0.85, 0.9, 0.95]
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    a = roc.auc_ci(scores, labels, n_boot=200, seed=7)
    b = roc.auc_ci(scores, labels, n_boot=200, seed=7)
    assert a == b                                  # deterministic given seed
    assert a["lo"] <= a["auc"] <= a["hi"]          # CI brackets the point estimate
    assert a["n_boot"] == 200
    assert 0.9 <= a["auc"] <= 1.0                  # separable data

def test_auc_ci_one_class_empty_none():
    assert roc.auc_ci([0.1, 0.2], [0, 0], n_boot=50, seed=1) is None

def test_percentile_rank_fraction_at_or_below():
    ref = [0.1, 0.2, 0.3, 0.4]
    assert roc.percentile_rank(0.25, ref) == 0.5      # 2 of 4 <= 0.25
    assert roc.percentile_rank(0.0, ref) == 0.0
    assert roc.percentile_rank(0.4, ref) == 1.0

def test_percentile_rank_empty_reference_none():
    assert roc.percentile_rank(0.3, []) is None

def test_assemble_labeled_set_labels_and_groups():
    out = roc.assemble_labeled_set(
        in_corpus=[0.1, 0.2],
        ood_by_kind={"heldout_field:arthistory": [0.7], "synthetic": [0.6], "random": [0.95]},
    )
    assert out["labels"].count(0) == 2 and out["labels"].count(1) == 3
    # in_corpus indices all label 0
    assert all(out["labels"][i] == 0 for i in out["index_of"]["in_corpus"])
    # a per-kind group resolves to its OOD score
    fi = out["index_of"]["heldout_field:arthistory"]
    assert [out["scores"][i] for i in fi] == [0.7]

def test_assemble_labeled_set_empty_kinds_skipped():
    out = roc.assemble_labeled_set(in_corpus=[0.1], ood_by_kind={"synthetic": [], "random": [0.9]})
    assert "synthetic" not in out["index_of"]
    assert out["labels"] == [0, 1]


def test_assemble_then_auc_overlapping_distributions_near_half():
    # in-corpus and OOD drawn from the SAME range -> the assembled pipeline AUC is ~0.5 (no separability)
    out = roc.assemble_labeled_set(
        in_corpus=[0.20, 0.22, 0.24, 0.26, 0.28],
        ood_by_kind={"heldout_field:x": [0.21, 0.23, 0.25, 0.27, 0.29]})
    auc = roc.roc_auc(out["scores"], out["labels"])
    assert 0.4 <= auc <= 0.7            # overlapping -> near 0.5


def test_assemble_then_auc_separated_distributions_is_one():
    out = roc.assemble_labeled_set(
        in_corpus=[0.10, 0.12, 0.14],
        ood_by_kind={"heldout_field:x": [0.80, 0.82, 0.84]})
    assert roc.roc_auc(out["scores"], out["labels"]) == 1.0   # cleanly separated
