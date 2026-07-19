# Cross-Vendor Divergence — Pre-Registration (fabrication-triage retrospective test)

> Committed BEFORE curating the dataset to lock every knob (honesty stake: no post-hoc tuning; any change after
> seeing the aggregate result converts the run to exploratory, not a measured result). Author: Allen Byrd.
> 2026-07-19. Machinery: `scripts/divergence.py` (frozen at this commit) + `scripts/roc.py` (AUROC = Mann-Whitney U,
> `auc_ci` bootstrap). Full results: private working notes (not published raw). This file is the standing honesty
> record; it is hash-bound in `references/prereg-manifest.json`.

## Question
On real fleet runs, is a model-produced proper noun's **cross-vendor divergence** higher when it is **FABRICATED**
than when it is **CONFIRMED**? A PASS here is a **weak existence proof** that divergence carries a fabrication signal
worth triaging on — NEVER a precision/recall, a calibrated threshold, or a classifier.

## The one-sided-signal invariant (NOT a knob — the governing honesty rule)
High cross-vendor divergence is a POSITIVE fabrication flag only. **Low divergence is NOT exculpatory** — vendors
share training data and co-hallucinate (the F1 case: several models agreed *on* fabrications). This statistic ORDERS
the verification queue; it never clears a proper noun and never replaces verify-to-kill. No result here can weaken
that invariant.

## Prior art (verified 2026-07-19, primary-source)
arXiv:2606.19509 — Dasula/Desikan/Srivastava, *"Detecting Epistemic Blind Spots via Cross-Model Attribution
Divergence"* (EIML@ICML 2026): a named Attribution Disagreement Score + cross-model calibrator built on divergence.
Their setting = LLM-vs-XGBoost on clinical tabular data; ours = multi-vendor fleet on research proper nouns.
Claim **"rare as an integrated productized workflow," NEVER "novel."**

## Data (FROZEN source; curated answer-label-blind to the aggregate)
The 2026-06-20 meta-research fleet run's raw per-model outputs (private working data) joined to its per-referent
verification ledgers (private working data). One row per
referent-slot where ≥2 vendors gave a proper-noun value:
`{slot_id, referent, source_cluster, vendor_values:{vendor:raw_value}, label}`,
`label ∈ {confirmed, fabricated, misleading, unverifiable}`. Curation is MECHANICAL transcription — the aggregate
divergence-vs-label association is NOT computed or eyeballed during curation (standard pre-registration discipline:
rows are visible during collection; the analysis is frozen).

## The FROZEN statistic (per referent-slot)
Group values by **VENDOR** (provider), collapse same-vendor models to one modal normalized vote
(`collapse_by_vendor`). For a slot with `V` answering vendors and `D` distinct normalized values:
- **PRIMARY divergence** = `(D − 1) / (V − 1)`, bounded [0,1]; undefined (slot EXCLUDED) if `V < 2`.
- **Robustness column** = vendor-weighted normalized entropy `H / log(V)` (reported, not the decision statistic).
- Values normalized by `normalize_value` (strip wrapping punctuation + a leading `vendor/` prefix, lowercase)
  BEFORE distinct-counting.

## The FROZEN test + endpoints
Reuse `roc.py`: **AUROC** of (score = divergence, positive = the arm's label) = P(a positive out-diverges a
negative), tie-safe. Effect size = rank-biserial `2·AUROC − 1`. CI = `roc.auc_ci` seeded STRATIFIED bootstrap.
- **PRIMARY endpoint:** positive = FABRICATED, negative = CONFIRMED. (MISLEADING and UNVERIFIABLE are EXCLUDED —
  misleading = real-but-stale is not a fabrication; unverifiable has no ground truth.)
- **SECONDARY endpoint:** positive = FABRICATED ∪ MISLEADING, negative = CONFIRMED (does divergence track
  "not-currently-true" more broadly?).

## FROZEN knobs (no change after curating)
`statistic = (D-1)/(V-1)` vendor-collapsed · `normalize_value` as in `divergence.py` @ this commit · `k_min = 15`
(min of #positive, #negative per arm) · `n_boot = 2000` · `seed = 20260719` · CI = stratified 95% percentile
bootstrap · effect = rank-biserial `2·AUROC−1`.

## FROZEN verdict criteria (per arm; primary is the headline)
- `min(#positive, #negative) < k_min = 15` → **INCONCLUSIVE (underpowered)**. Report the counts + the honest
  "signal recoverable but sample too thin" finding. Do NOT report an AUROC as a result.
- else if bootstrap **CI lower bound > 0.5** → **WEAK_EXISTENCE_PROOF**: "high cross-vendor divergence is associated
  with fabrication in this sample." Advisory only — NEVER a precision/recall or a threshold.
- else → **HONEST_NEGATIVE**: divergence does not discriminate fabrication from confirmation in this sample.

## Honest pre-run prediction (NOT a knob; recorded to keep the result honest)
The spike (TASK-A: 7 vendors, ~6 distinct picks, ledger 6 FABRICATED + 5 MISLEADING) suggests the FABRICATED-vs-
CONFIRMED direction is real. BUT the CONFIRMED negative class is the risk: a confirmed proper noun is often one the
vendors AGREED on (low divergence, and often only 1 vendor named it) → few CONFIRMED slots may clear `V ≥ 2`, so the
PRIMARY arm may land **INCONCLUSIVE** on the negative side. Most-likely outcomes, in order: INCONCLUSIVE (thin
CONFIRMED class) > WEAK_EXISTENCE_PROOF > HONEST_NEGATIVE. A single meta-research run, one topic domain — advisory,
never a calibrated threshold, regardless of outcome.

## Scope + honesty backstops
- Single-domain (research tooling / model governance), single run → NOT generalizable; a weak existence proof at best.
- The raw curated dataset stays PRIVATE (unpublished working data) — it contains model outputs (same leak-gate as the
  raw fleet JSONs); only the aggregate (AUROC + CI + verdict + counts) may reach the public surface.
- No knob above changes after curating or after seeing the aggregate. The frozen `divergence.py` is the method of record.
