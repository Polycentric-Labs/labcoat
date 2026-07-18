"""labcoat ROC / OOD-evaluation core — PURE, deterministic, stdlib only (no embedder/index/network/clock; the only
randomness is the seeded bootstrap RNG). Positive class = label 1 = OOD (detection-positive); score = nearest
distance (higher => more OOD). Metrics follow the OOD convention (AUROC + FPR@TPR95; Sun et al. 2022 ICML
arXiv:2204.06507; Hendrycks & Gimpel 2017) — Youden's J is a DIAGNOSTIC only (equal-cost assumption; non-standard
for OOD). Shared core for Build 3a (off_distribution ROC) and 3b (tau). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import math
import random


def roc_auc(scores, labels):
    """Tie-safe AUROC via the Mann-Whitney-U average-rank formula = P(score_OOD > score_ID) + 0.5*P(tie).
    Positive class = label 1. Returns None if either class is empty (undefined)."""
    paired = sorted(((float(s), int(y)) for s, y in zip(scores, labels)), key=lambda t: t[0])
    n_pos = sum(1 for _, y in paired if y == 1)
    n_neg = len(paired) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = [0.0] * len(paired)
    i = 0
    while i < len(paired):
        j = i
        while j < len(paired) and paired[j][0] == paired[i][0]:
            j += 1
        avg = ((i + 1) + j) / 2.0  # average of 1-based ranks i+1..j over the tie block
        for k in range(i, j):
            ranks[k] = avg
        i = j
    sum_ranks_pos = sum(r for r, (_, y) in zip(ranks, paired) if y == 1)
    return (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def operating_point(scores, labels, threshold):
    """TPR/FPR when predicting OOD iff score > threshold. Positive class = label 1. Empty class -> 0.0 for it."""
    thr = float(threshold)
    pos = [float(s) for s, y in zip(scores, labels) if y == 1]
    neg = [float(s) for s, y in zip(scores, labels) if y == 0]
    tpr = (sum(1 for s in pos if s > thr) / len(pos)) if pos else 0.0
    fpr = (sum(1 for s in neg if s > thr) / len(neg)) if neg else 0.0
    return {"tpr": tpr, "fpr": fpr}


def roc_points(scores, labels):
    """ROC points {threshold, tpr, fpr} over candidate thresholds (each unique score, plus -inf for the (1,1)
    endpoint), sorted by (fpr, tpr). Predict OOD iff score > threshold."""
    uniq = sorted({float(s) for s in scores})
    thresholds = [-math.inf] + uniq  # -inf flags everything -> (fpr=1,tpr=1) endpoint
    pts = []
    for t in thresholds:
        op = operating_point(scores, labels, t)
        pts.append({"threshold": t, "tpr": op["tpr"], "fpr": op["fpr"]})
    return sorted(pts, key=lambda p: (p["fpr"], p["tpr"]))


def fpr_at_tpr(scores, labels, *, tpr_target=0.95):
    """FPR@TPR-target — the PRIMARY OOD metric. Among ROC points achieving tpr >= target, return the one with the
    LOWEST fpr (ties -> highest threshold). Returns {threshold, fpr, tpr} or None if a class is empty."""
    if not any(y == 1 for y in labels) or not any(y == 0 for y in labels):
        return None
    qualifying = [p for p in roc_points(scores, labels) if p["tpr"] >= float(tpr_target)]
    if not qualifying:
        return None
    best = min(qualifying, key=lambda p: (p["fpr"], -p["threshold"]))
    return {"threshold": best["threshold"], "fpr": best["fpr"], "tpr": best["tpr"]}


def youden_threshold(scores, labels):
    """DIAGNOSTIC ONLY (never 'optimal' — equal-cost assumption is non-standard for OOD). Threshold maximizing
    Youden's J = tpr - fpr; ties -> highest threshold (fewest flags). Returns {threshold, j, tpr, fpr} or None."""
    if not any(y == 1 for y in labels) or not any(y == 0 for y in labels):
        return None
    best = None
    for p in roc_points(scores, labels):
        j = p["tpr"] - p["fpr"]
        cand = (j, p["threshold"])
        if best is None or cand > (best["j"], best["threshold"]):
            best = {"threshold": p["threshold"], "j": j, "tpr": p["tpr"], "fpr": p["fpr"]}
    return best


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = max(0, min(len(sorted_vals) - 1, int(math.ceil(q * len(sorted_vals)) - 1)))
    return sorted_vals[idx]


def auc_ci(scores, labels, *, n_boot=2000, seed, stratified=True):
    """Seeded STRATIFIED percentile bootstrap CI for AUROC (NOT DeLong — error-prone in stdlib). Resample WITHIN
    each class (preserve class proportions) n_boot times; return {auc, lo, hi, n_boot} (2.5/97.5 pct). None if a
    class is empty. Deterministic given `seed`."""
    point = roc_auc(scores, labels)
    if point is None:
        return None
    pos = [float(s) for s, y in zip(scores, labels) if y == 1]
    neg = [float(s) for s, y in zip(scores, labels) if y == 0]
    rng = random.Random(seed)
    boots = []
    for _ in range(int(n_boot)):
        if stratified:
            bp = [rng.choice(pos) for _ in pos]
            bn = [rng.choice(neg) for _ in neg]
        else:
            pool = list(zip(scores, labels))
            samp = [rng.choice(pool) for _ in pool]
            bp = [float(s) for s, y in samp if y == 1]
            bn = [float(s) for s, y in samp if y == 0]
        a = roc_auc(bp + bn, [1] * len(bp) + [0] * len(bn))
        if a is not None:
            boots.append(a)
    boots.sort()
    return {"auc": point, "lo": _percentile(boots, 0.025), "hi": _percentile(boots, 0.975), "n_boot": int(n_boot)}


def percentile_rank(value, reference_values):
    """Soft advisory score in [0,1]: fraction of reference_values <= value (the query's nearest-distance rank among
    corpus internal distances). Empty reference -> None. The honest 'how far out' signal: trustworthy only near 1.0
    given the thin SPECTER2 margin."""
    ref = [float(x) for x in (reference_values or [])]
    if not ref:
        return None
    return sum(1 for x in ref if x <= float(value)) / len(ref)


def assemble_labeled_set(*, in_corpus, ood_by_kind):
    """Merge in-corpus (label 0) distances + per-kind OOD (label 1) distance lists into (scores, labels) plus an
    index_of map {group_name -> [indices]} for layered + field-stratified reporting. Kind names like
    'heldout_field:<field>' enable per-field slices. Empty kinds are skipped. Pure."""
    scores, labels, index_of = [], [], {"in_corpus": []}
    for d in (in_corpus or []):
        index_of["in_corpus"].append(len(scores)); scores.append(float(d)); labels.append(0)
    for kind, ds in (ood_by_kind or {}).items():
        ds = list(ds or [])
        if not ds:
            continue
        index_of[kind] = []
        for d in ds:
            index_of[kind].append(len(scores)); scores.append(float(d)); labels.append(1)
    return {"scores": scores, "labels": labels, "index_of": index_of}
