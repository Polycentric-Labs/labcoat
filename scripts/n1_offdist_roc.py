"""labcoat Build 3a — off_distribution REAL-ROC harness (SHELL). Loads the OpenAlex snapshot + SPECTER2, builds an
80/20 calibration/test split, fetches+embeds held-out fields (cached), scores in-corpus(test) vs OOD via the
calibration index, and computes layered + field-stratified AUROC + FPR@TPR95 + bootstrap CIs via the pure roc.py.
The deployed gate value is UNCHANGED — Youden + calibration-split thresholds are diagnostics only (advisory).
label 1 = OOD; score = nearest cosine distance. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import sys, pathlib, hashlib, json, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import roc, n1_index, n1_corpus, n1_corpus_openalex as oa

_FAR_FUTURE = "2999-01-01"  # date_cutoff so all docs are eligible (this is a regime test, not temporal)

# OpenAlex tags mega-cited STEM/medicine papers into broad humanities concepts (e.g. "state-of-the-ART" -> Art
# history; COVID/PRISMA papers -> Law/Theology). A held-out "field" polluted with such papers is NOT out-of-corpus
# and would WRONGLY depress the held-out-field AUROC. This guard drops obviously-STEM-mistagged held-out works
# (logged per field in field_meta). Prefer LOW-LEVEL (L2/L3) humanities concepts, which empirically stay clean.
_STEM_RE = re.compile(
    r"state-of-the-art|neural network|deep learning|machine learning|reinforcement learning|convolutional|"
    r"\btransformer|genomic|protein structure|\bquantum|\bdataset\b|\bbenchmark|large language model|"
    r"diffusion model|\bGPU\b|\bCOVID|coronavirus|SARS-CoV|PRISMA|randomi[sz]ed (controlled )?trial", re.I)


def _looks_stem(title) -> bool:
    """True if a held-out-field title looks like a mis-tagged STEM/medicine paper (contamination guard)."""
    return bool(_STEM_RE.search(title or ""))


def _median(vals):
    """True median (average of the two middle values for even n). None for empty. (NOT s[n//2], which is the
    upper-median for even n and would equal `worst` for n=2 — see the 3a review.)"""
    s = sorted(float(v) for v in vals)
    n = len(s)
    if n == 0:
        return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

# Curated off-domain real-text negatives (synthetic-OOD). ~30 coherent non-corpus claims across distinct domains.
OOD_BANK = [
    "Whisk three eggs with sugar, fold into sifted flour, and bake at 180 degrees for twenty minutes.",
    "The lessee shall indemnify the lessor against all liabilities arising under this tenancy agreement.",
    "The striker scored a hat-trick in the second half to win the championship final on penalties.",
    "A traditional sourdough loaf needs a mature starter, long bulk fermentation, and a hot dutch oven.",
    "The sonnet's volta turns on the ninth line, shifting from octave's question to sestet's answer.",
    "Diversify the portfolio across equities, bonds, and commodities to hedge against inflation risk.",
    "Sauté the onions until translucent before deglazing the pan with a splash of dry white wine.",
    "The defendant's motion to suppress was denied for lack of a reasonable expectation of privacy.",
    "The fugue's subject is answered at the dominant before the counter-subject enters in the alto voice.",
    "Rotate the tyres every ten thousand kilometres and check the brake pad wear at each service.",
    "The barista pulled a ristretto shot and steamed the milk to a glossy microfoam for the latte art.",
    "Quarterly earnings beat consensus on stronger margins, lifting the share price in after-hours trading.",
    "The midfielder pressed high to force a turnover, then threaded a through-ball to the overlapping full-back.",
    "Marinate the lamb overnight in yoghurt, garlic, and garam masala before grilling over charcoal.",
    "The plaintiff sought specific performance rather than damages for the breach of the sale contract.",
    "Prune the roses in late winter, cutting to an outward-facing bud above a five-leaflet leaf.",
    "The choir modulated to the relative minor for the second verse of the carol.",
    "Refinance the mortgage to a fixed rate to lock in repayments before the next rate decision.",
    "The goalkeeper parried the penalty onto the post and smothered the rebound at the striker's feet.",
    "Temper the chocolate to thirty-one degrees so the couverture sets with a glossy snap.",
    "The arbitration clause compels the parties to resolve disputes outside the ordinary courts.",
    "Deadhead the petunias weekly to encourage a longer and more vigorous blooming season.",
    "The cellist's vibrato widened through the cadenza before the orchestra re-entered at the tutti.",
    "Dollar-cost-average into the index fund each month to smooth out market volatility over time.",
    "The winger cut inside onto his stronger foot and curled the free-kick over the wall.",
    "Proof the brioche dough until doubled, then knock back and shape before the second rise.",
    "The tribunal found the dismissal procedurally unfair and ordered reinstatement with back pay.",
    "Transplant the seedlings after the last frost, hardening them off over a week on the patio.",
    "The libretto sets the aria in da capo form, repeating the A section with ornamented embellishment.",
    "Hedge the currency exposure with a forward contract to fix the exchange rate for the import.",
]


def _split_ids(ids, *, test_frac=0.20, seed=1):
    """Deterministic id-hash split into (calibration_ids set, test_ids set). seed salts the hash."""
    test = set()
    for i in ids:
        h = int(hashlib.sha256(f"{seed}|{i}".encode("utf-8")).hexdigest(), 16)
        if (h % 10_000) / 10_000.0 < test_frac:
            test.add(i)
    calib = [i for i in ids if i not in test]
    return set(calib), test


def _sub_index(full_idx, keep_ids):
    """Build a FaissN1Index over the subset of full_idx whose id is in keep_ids."""
    keep = set(keep_ids)
    rows = [r for r, i in enumerate(full_idx._ids) if i in keep]
    vecs = [full_idx._x[r].tolist() for r in rows]
    ids = [full_idx._ids[r] for r in rows]
    dates = [full_idx._dates[r] for r in rows]
    titles = [full_idx._titles[r] for r in rows]
    return n1_index.build_index(
        [{"id": i, "vec": v, "date": d, "title": t} for i, v, d, t in zip(ids, vecs, dates, titles)],
        embedder_fingerprint=full_idx._fp)


def nearest_distance(index, qvec):
    """Cosine distance to the nearest doc in `index` (no date filter). None if empty."""
    hit = index.cite_nearest(qvec, date_cutoff=_FAR_FUTURE)
    return hit["distance"] if hit else None


def build_scores(full_idx, embedder, *, heldout_fields, get=None, per_field=150, cache_dir=None, test_frac=0.20,
                 seed=1, rng_seed=42):
    """Assemble the labeled set. Returns (assembled, extras) where assembled = roc.assemble_labeled_set(...) and
    extras carries the calibration-split threshold + in_corpus_ref (the held-out in-corpus distances = the
    percentile_rank reference) + the deployed gate + per-field field_meta (fetched/after_overlap/kept counts).
    in-corpus(test): 20% held-out titles -> nearest doc in the 80% calibration index. OOD: held-out fields
    (overlap- + STEM-contamination-filtered) + the OOD_BANK + random vectors, all scored vs the SAME calib index."""
    import random
    calib_ids, test_ids = _split_ids(full_idx._ids, test_frac=test_frac, seed=seed)
    cidx = _sub_index(full_idx, calib_ids)

    # in-corpus test positives: 20% titles embedded as queries -> nearest in calibration index
    test_rows = [r for r, i in enumerate(full_idx._ids) if i in test_ids]
    test_titles = [full_idx._titles[r] for r in test_rows]
    test_qvecs = embedder.embed(test_titles, role="query")
    in_corpus = [d for d in (nearest_distance(cidx, qv) for qv in test_qvecs) if d is not None]

    # calibration-split threshold: 80% titles-as-queries -> nearest OTHER calib doc, p95 (exclude-self by id)
    calib_rows = [r for r, i in enumerate(full_idx._ids) if i in calib_ids]
    calib_titles = [full_idx._titles[r] for r in calib_rows]
    calib_ids_list = [full_idx._ids[r] for r in calib_rows]
    calib_qvecs = embedder.embed(calib_titles, role="query")
    calib_thr = cidx.query_calibrated_threshold(calib_qvecs, calib_ids_list)
    # percentile_rank reference = the in-corpus held-out (test 20%) nearest distances (`in_corpus` above): they are
    # exclude-self by construction (test items are NOT in the 80% calibration index) and ARE the in-distribution.

    ood_by_kind, field_meta = {}, {}
    corpus_id_set = set(full_idx._ids)
    for field in heldout_fields:
        raw = field["records"]
        recs = [r for r in raw if r.get("id") not in corpus_id_set]      # overlap guard: id already in the corpus
        kept = [r for r in recs if not _looks_stem(r.get("title", ""))]  # STEM mis-tag contamination guard
        field_meta[field["name"]] = {"fetched": len(raw), "after_overlap": len(recs), "kept": len(kept)}
        if not kept:
            continue
        qv = embedder.embed([r["title"] for r in kept], role="query")
        ds = [d for d in (nearest_distance(cidx, v) for v in qv) if d is not None]
        ood_by_kind[f"heldout_field:{field['name']}"] = ds[:per_field]
    # synthetic bank
    sb = embedder.embed(OOD_BANK, role="query")
    ood_by_kind["synthetic"] = [d for d in (nearest_distance(cidx, v) for v in sb) if d is not None]
    # random unit-norm controls
    rng = random.Random(rng_seed)
    dim = full_idx._x.shape[1]
    rand = []
    for _ in range(50):
        v = [rng.gauss(0, 1) for _ in range(dim)]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        rand.append(nearest_distance(cidx, [x / n for x in v]))
    ood_by_kind["random"] = [d for d in rand if d is not None]

    assembled = roc.assemble_labeled_set(in_corpus=in_corpus, ood_by_kind=ood_by_kind)
    extras = {"calibration_split_threshold": calib_thr, "in_corpus_ref": in_corpus,
              "deployed_gate": full_idx._loaded_threshold, "field_meta": field_meta}
    return assembled, extras


def report(assembled, extras, *, seed=7, n_boot=2000, tpr_target=0.95):
    """Build the layered + field-stratified metrics dict from an assembled labeled set. Pure (delegates to roc.py).
    Layers: per_field (each held-out field vs in_corpus); heldout_field = the HONEST HARD HEADLINE (all real
    foreign-field text vs in_corpus, NO synthetic/random); real_text (+ synthetic); full_incl_random (+ random).
    Also emits the soft percentile-rank score (R3): where each threshold sits on the in-corpus distance dist."""
    sc, lb, idxof = assembled["scores"], assembled["labels"], assembled["index_of"]
    inc = idxof["in_corpus"]
    gate = extras.get("deployed_gate"); cst = extras.get("calibration_split_threshold")
    def layer(names):
        ood = [i for n in names for i in idxof.get(n, [])]
        s = [sc[i] for i in inc + ood]; l = [lb[i] for i in inc + ood]
        return {"n_in": len(inc), "n_ood": len(ood), "auroc": roc.roc_auc(s, l),
                "fpr_at_tpr95": (roc.fpr_at_tpr(s, l, tpr_target=tpr_target) or {}).get("fpr"),
                "auc_ci": roc.auc_ci(s, l, n_boot=n_boot, seed=seed),
                "youden": roc.youden_threshold(s, l),  # DIAGNOSTIC only
                "deployed_gate_op": roc.operating_point(s, l, gate) if gate is not None else None,
                "calib_split_op": roc.operating_point(s, l, cst) if cst is not None else None}
    fields = [n for n in idxof if n.startswith("heldout_field:")]
    out = {"per_field": {n: layer([n]) for n in fields},
           "heldout_field": layer(fields),                       # honest hard headline (no synthetic/random)
           "real_text": layer(fields + ["synthetic"]),
           "full_incl_random": layer(fields + ["synthetic", "random"]),
           "calibration_split_threshold": cst,
           "deployed_gate": gate,
           "field_meta": extras.get("field_meta", {})}
    # field-stratified aggregate (TRUE median + worst FPR@TPR95 across fields) — never just pooled
    fvals = [v["fpr_at_tpr95"] for v in out["per_field"].values() if v["fpr_at_tpr95"] is not None]
    if fvals:
        out["field_stratified"] = {"median_fpr_at_tpr95": _median(fvals), "worst_fpr_at_tpr95": max(fvals),
                                   "n_fields": len(fvals)}
    # soft percentile-rank score (R3): the fraction of in-corpus claims at/below each threshold's distance.
    ref = extras.get("in_corpus_ref") or []
    out["soft_score"] = {
        "reference": "held-out in-corpus nearest-distances", "ref_size": len(ref),
        "deployed_gate_percentile_rank": roc.percentile_rank(gate, ref) if (ref and gate is not None) else None,
        "calib_split_percentile_rank": roc.percentile_rank(cst, ref) if (ref and cst is not None) else None}
    return out


def _main(argv):
    import argparse, n1_embedder
    ap = argparse.ArgumentParser(prog="n1_offdist_roc")
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--snapshot", required=True)
    # Default to CLEAN level-2/3 humanities concepts (empirically free of STEM mis-tags — unlike the level-1
    # Art history / Classics / Law / Theology, which OpenAlex pollutes with mega-cited STEM/medicine papers).
    # The _looks_stem guard backs this up; re-probe concept purity at run time (tagging drifts).
    ap.add_argument("--fields", nargs="+",
                    default=["Musicology", "Comparative literature", "Numismatics", "Art criticism"])
    ap.add_argument("--per-field", type=int, default=150)
    ap.add_argument("--cache-dir", default="_internal/offdist-roc-cache")
    ap.add_argument("--out", default="_internal/offdist-roc-report.json")
    ap.add_argument("--mailto", default="")
    a = ap.parse_args(argv)
    emb = n1_embedder.load_embedder("specter2")
    idx = n1_index.load_snapshot(a.snapshot, active_fingerprint=emb.fingerprint())
    # fetch held-out fields (overlap-verified inside build_scores)
    concepts = oa.resolve_concepts(a.fields, mailto=a.mailto)
    heldout = []
    for c in concepts:
        recs = oa.fetch_openalex([c["id"]], per_concept=a.per_field, cache_dir=a.cache_dir, mailto=a.mailto)
        heldout.append({"name": c["name"].replace(" ", "").lower(), "records": recs})
    assembled, extras = build_scores(idx, emb, heldout_fields=heldout, per_field=a.per_field)
    rep = report(assembled, extras)
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    # annotate snapshot diagnostics from the HONEST HARD HEADLINE (held-out-field) layer; the gate is PROTECTED
    # inside annotate_snapshot_diagnostics (any gate key in kv is dropped) so this can never alter the gate.
    hf = rep["heldout_field"]
    n1_index.annotate_snapshot_diagnostics(a.snapshot,
        roc_auroc_heldout_field=hf["auroc"], roc_fpr_at_tpr95=hf["fpr_at_tpr95"], roc_auc_ci=hf["auc_ci"],
        youden_threshold=(hf["youden"] or {}).get("threshold"),
        calibration_split_threshold=rep.get("calibration_split_threshold"),
        deployed_gate_percentile_rank=rep["soft_score"]["deployed_gate_percentile_rank"])
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    _main(sys.argv[1:])
