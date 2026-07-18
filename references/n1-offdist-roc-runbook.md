# N1 off_distribution REAL-ROC Runbook (Build 3a)

## Purpose

The `off_distribution` gate in `n1_index` is an **anti-out-of-corpus guard**, NOT a novelty signal.
It answers: "is this query about something the corpus has never seen?" — blocking hallucinated citations
to nonexistent papers. It does NOT measure scientific novelty. Confusing these leads to severe overclaiming.

This runbook covers the Build 3a ROC analysis: converting the binary 6/6 probe into an honest AUROC +
FPR@TPR95 + bootstrap CIs over the deep OpenAlex N1 corpus.

## Label convention

- **Label 1 = OOD = detection-positive** (the gate should fire)
- **Label 0 = in-corpus = ID** (the gate should not fire)
- **Score = nearest cosine distance** (higher = more OOD)
- **FPR@TPR95** = rate of false advisory on in-corpus queries when the gate catches 95% of OOD queries.
  This is the PRIMARY metric. It tells you how often a legitimate in-corpus query would be wrongly flagged.

Youden's J is a **DIAGNOSTIC ONLY** — the equal-cost assumption (false-alarm = missed-OOD) is not valid
for this use case. Never report Youden's threshold as the "optimal" gate.

## How to run the full ROC analysis

```bash
python scripts/n1_offdist_roc.py run \
  --snapshot _internal/n1-openalex-snapshot \
  --fields Musicology "Comparative literature" Numismatics "Art criticism" \
  --per-field 150 \
  --cache-dir _internal/offdist-roc-cache \
  --out _internal/offdist-roc-report.json
```

**Held-out field selection (IMPORTANT).** Use CLEAN level-2/3 humanities concepts (the default above). Level-1
concepts (Art history, Classics, Law, Theology, Archaeology) are polluted by OpenAlex mis-tagging — mega-cited
STEM/medicine papers ("state-of-the-ART…", COVID, PRISMA) get tagged into them, and such papers are NOT
out-of-corpus, so they would wrongly DEPRESS the held-out-field AUROC. The harness applies a `_looks_stem` title
guard as defense-in-depth (drops counted in `field_meta`), but the right fix is good concept selection. Re-probe
concept purity at run time (OpenAlex tagging drifts) and report the per-field `field_meta` (fetched/after_overlap/
kept) in any write-up.

This will:
1. Load the OpenAlex N1 snapshot + SPECTER2 embedder.
2. Build an 80/20 calibration/test split (deterministic, hash-based).
3. Fetch and embed the held-out fields (overlap- + STEM-filtered, not in the corpus) via OpenAlex.
4. Score in-corpus (test 20%) + OOD (fields + 30-text synthetic bank + 50 random vectors) against
   the calibration (80%) index.
5. Compute AUROC, FPR@TPR95, Youden threshold (DIAGNOSTIC only), bootstrap CIs (2000 iterations) — layered and
   field-stratified — plus the soft percentile-rank score.
6. Write the report to `--out` and annotate `snapshot/meta.json` with diagnostic keys (gate unchanged).

## What the layered + field-stratified numbers mean

The report has these layers:

- **per_field**: each held-out field (e.g. `heldout_field:musicology`) scored against in-corpus alone.
  Shows field-specific separability.
- **heldout_field**: ALL held-out real foreign-field text vs in-corpus, NO synthetic/random. This is the
  **HONEST HARD HEADLINE** — the number to quote.
- **real_text**: held-out fields + synthetic bank vs in-corpus (easier — the synthetic bank is curated-easy OOD).
- **full_incl_random**: adds random unit-norm vectors. Expected near-1.0 AUROC; a sanity check ONLY — never headline it.

**Field-stratified aggregate** (`field_stratified`):
- `median_fpr_at_tpr95` — the TRUE median (avg of the two middle values for even field count) FPR at 95% recall.
- `worst_fpr_at_tpr95` — the highest (worst) FPR@TPR95 across fields. The adversarial case.
- `n_fields` — number of fields contributing.

**Soft percentile-rank score** (`soft_score`): where each threshold sits on the held-out in-corpus
nearest-distance distribution — e.g. `deployed_gate_percentile_rank ≈ 0.95` means the gate flags ~5% of in-corpus
claims. This is the advisory's honest "how far out" signal; given the thin SPECTER2 margin it is trustworthy only
near 1.0 (clearly-far claims), which is why the live advisory should emit the rank, not just a binary flag.

The deployed gate value in `meta.json` (`off_distribution_threshold`) is NEVER changed by this analysis —
`annotate_snapshot_diagnostics` PROTECTS it (any gate key passed in is dropped). Diagnostic keys
(`roc_auroc_heldout_field`, `roc_fpr_at_tpr95`, `roc_auc_ci`, `youden_threshold`, `calibration_split_threshold`,
`deployed_gate_percentile_rank`) are ADDED alongside it.

## Deployed gate status

The gate remains at its calibrated value from the build process. This ROC analysis is advisory —
it measures how well the gate performs across held-out fields, but does not update the gate.

If you want to update the gate based on this analysis:
1. Note the `calibration_split_threshold` (p95 of in-corpus query distances on the 80% split).
2. Compare to the deployed gate.
3. If you decide to change the gate, run `build_openalex_index.py` with an explicit `--gate-threshold`
   argument and save a new snapshot. This is a deliberate, documented, separate action.

## Honest caveats (verbatim from design spec §6 — do not soften)

1. **Threshold optimism / leakage**: the calibration-split threshold is fit on the 80% calibration
   partition. Even though the 20% test partition is held out for the in-corpus scores, the 80%/20%
   boundary is still derived from the same corpus. In a small corpus, this inflates measured performance.
   Report the train/test split sizes alongside every metric.

2. **Field-dependent calibration**: the OOD separability varies by field. A field like "Law" may be
   much more separable from bioscience literature than "Musicology". Pooled AUROC hides this. Always
   report field-stratified numbers (per_field + field_stratified) rather than just the full-pool metric.

3. **Thin-margin reliability**: SPECTER2 cosine distances cluster in a narrow band (measured margin
   ~0.06 for the current corpus). Wide bootstrap CIs are expected and honest. A CI of [0.65, 0.85]
   means the measurement is real but uncertain — do not round up to "good performance."

4. **Titles-not-claims**: the N1 corpus and the held-out OOD inputs are represented as TITLES only.
   The actual labcoat use case queries with scientific CLAIMS. Title-to-title distances are more
   separable than claim-to-title distances. The ROC numbers from this analysis are an upper bound on
   real performance; actual FPR@TPR95 in production is expected to be higher.

5. **Class imbalance**: the synthetic bank (30 texts) and random controls (50 vectors) are intentionally easy OOD
   cases. The `heldout_field` and `per_field` layers exclude them; use those for the honest evaluation (the
   `real_text` layer includes the synthetic bank, and `full_incl_random` is inflated by the random control).
   Further: **production OOD frequency is unknown** — the labeled set is artificially balanced (~50% OOD). If true
   out-of-corpus queries are rare (or common) in production, the effective false-advisory rate may differ
   materially from these measurements.

6. **Single-field-is-one-draw**: each held-out field is one sample of a domain. "Art history" from
   OpenAlex may not represent the full distribution of non-biomedical queries. Five fields give a
   rough upper bound on diversity; the field_stratified worst-case is more reliable than the median
   for safety assessments.

## Success criterion (advisory, not deployed)

- Deployed gate meets: FPR@TPR95 (heldout_field layer — the honest hard headline) ≤ 5% AND TPR at deployed gate
  ≥ 90% across held-out fields.
- If this criterion is NOT met, it is an honest finding. Report it as-is and assess whether the gate
  needs re-calibration with a richer corpus. Do not adjust the metric to make the gate look better.
