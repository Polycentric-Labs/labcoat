# N2 Cross-Literature — Option C Pre-Registration (gate-discrimination across K positives)

> Committed BEFORE the run to lock every knob (honesty stake: no post-hoc tuning; any change after seeing results
> converts the run to exploratory/uncalibrated, not a PASS). Author: Allen Byrd. Owner-ratified path: n=3 primary +
> n=5 sensitivity (2026-07-02). Full results write-up: private working notes (2026-07-02, not published in this
> repo). This file is the standing honesty record. Continues `references/n2-crosslit-prereg.md` (Plans 3/4/5,
> Addenda 1–3) — see the Addendum-4 pointer there. Statistical design TRANSFORMED by a scoped Deep `/polycentric-labcoat`
> pass (private synthesis notes, 2026-07-02; citations controller-verified).

## Question
Across MULTIPLE documented, cleanly-time-sliced cross-literature discoveries, does the size-conditioning
hypergeometric GATE surface the true pair as **enriched** relative to a size-matched empirical background — i.e. was
the fish-oil↔Raynaud n=1 gate-clearance (Plan 5) a reproducible property of the gate, or a fluke? A PASS is a **weak
existence proof** ("the gate discriminates documented cross-lit gaps from size-matched spurious pairs better than
chance"), NEVER a discovery rate or precision (Moreau 2023 btad090 — time-sliced Swanson gold is noise-dominated;
n is small).

## Why an empirical-null enrichment test (not raw-gate sensitivity/specificity) — the transformed design
1. The raw per-gap hypergeometric p is a MIS-SPECIFIED null (over-dispersed: 4.5% pass at nominal 1% — within-paper /
   topic clustering + overlapping-pair dependence). BH/BY/Storey CANNOT fix a mis-specified per-test null (Efron 2004
   JASA 99:96-104). The fix is an EMPIRICAL / degree-preserving null (Maslov-Sneppen 2002 Science 296:910-913;
   **Tumminello 2011 PLOS ONE 6(3):e17994** — a degree-STRATIFIED hypergeometric IS the bipartite-configuration null
   within a degree-homogeneous stratum ⇒ the SIZE-BAND idea is the statistically-correct empirical null).
2. The corpus's own cross-paper gap population is a valid size-stratified BACKGROUND, NOT labeled negatives
   (contaminated by unlabeled positives → PU-learning; Moreau 2023). ⇒ frame as "ENRICHMENT vs a size-matched
   background," never "specificity vs true negatives."
3. Sensitivity/specificity/AUROC/precision@k are undefensible at small n (Minus 2025 arXiv:2504.16185 — AUROC needs
   many positive events). ⇒ use an EXACT permutation/binomial ENRICHMENT test (Fisher 1935; Clopper-Pearson 1934).

## Gold set (FROZEN; boundary-guard triaged live BEFORE freezing — private probe scripts, 2026-07-02)
The "undiscovered public knowledge" premise requires the two literatures be ISOLATED at the cutoff (≈0 direct A&C
co-mentions ≤ cutoff). Live triage of the full vetted gold set falsified the pickup's ~5-clean assumption; only these
survive:

**PRIMARY (n=3, strict-clean, boundary = 0 direct co-mentions ≤ cutoff):**
| # | pair | cutoff | A-lit query (MeSH) | C-lit query (MeSH) | boundary |
|---|---|---|---|---|---|
| P1 | fish-oil ↔ Raynaud | ≤1985 | `("Fish Oils"[MeSH] OR "Eicosapentaenoic Acid"[MeSH])` | `"Raynaud Disease"[MeSH]` | 0 |
| P2 | indomethacin ↔ Alzheimer | ≤1992 | `"Indomethacin"[MeSH]` | `"Alzheimer Disease"[MeSH]` | 0 (≤1995 has 5 → tightened to pre-Rogers-1993) |
| P3 | Nrf2 ↔ pancreatic cancer | ≤2005 | `"NF-E2-Related Factor 2"[MeSH]` | `"Pancreatic Neoplasms"[MeSH]` | 0 (molecular wet-lab discovery, DeNicola 2011; flagged) |

**SENSITIVITY (adds to n=5; near-clean, boundary ≤ 3; a pre-registered robustness arm, NOT the primary claim):**
| # | pair | cutoff | A-lit query | C-lit query | boundary |
|---|---|---|---|---|---|
| S4 | estrogen ↔ Alzheimer | ≤1988 | `"Estrogens"[MeSH]` | `"Alzheimer Disease"[MeSH]` | 1 |
| S5 | iPLA2 ↔ schizophrenia | ≤1990 | `("Phospholipases A"[MeSH] OR "Phospholipases A2"[MeSH])` | `"Schizophrenia"[MeSH]` | 3 |

**VOID control (reported separately, EXCLUDED from the enrichment test):** magnesium ↔ migraine ≤1987 (bridge absent,
established VOID in Plan 3).

**Target endpoint terms** (MeSH descriptor names, lowercased; the gap endpoints are descriptor names):
P1 a={fish oils, eicosapentaenoic acid, docosahexaenoic acids, fatty acids, omega-3} c={raynaud disease};
P2 a={indomethacin} c={alzheimer disease}; P3 a={nf-e2-related factor 2} c={pancreatic neoplasms};
S4 a={estrogens, estradiol, estrogen replacement therapy} c={alzheimer disease};
S5 a={phospholipases a, phospholipases a2} c={schizophrenia}.

## Corpus construction (answer-blind, per positive)
- One corpus PER positive = {A-literature, C-literature, 7 shared distractor literatures}, each `publication year ≤
  cutoff`, `retmax = 500`. Concept lists = per-doc MeSH descriptors, lowercased, `strip_check_tags` applied.
- **Shared distractors** (chosen blind to any bridge): malaria, epilepsy, glaucoma, psoriasis, asthma, osteoporosis,
  schizophrenia. **For S5 ONLY** (schizophrenia is the C-lit): replace the `schizophrenia` distractor with
  `tuberculosis` (`"Tuberculosis"[MeSH]`) so the distractor pool stays disjoint from the target.
- **Boundary guard** (per positive, asserted at build): direct A&C co-mention count ≤ cutoff must equal the frozen
  boundary above (0 primary / ≤3 sensitivity); a larger count VOIDs that positive as substrate-invalid.
- Sub-corpus/topic tags used ONLY for the provenance-aware hub + reporting — NEVER as a ranking feature.

## Machinery reuse + the size variable (all pre-existing, frozen)
Per corpus, `n2_crosslit_measure.measure_case(..., priority="raw", return_internals=True, max_gaps=<above the total
gap count — NO truncation, per Addendum 3>)` yields the FULL untruncated cross-paper gap population `ranked` (raw
priority ⇒ every gap with ≥1 cross-paper non-hub bridge, i.e. c_AC ≥ 1), plus `prov`, `hub`, `nonhub_degrees`, `nc`.
- `hub_percentile = 0.90`, `max_edges = 200000` (frozen throughout the arc).
- Per gap g: `deg_A = nonhub_degrees[g.a]`, `deg_C = nonhub_degrees[g.c]`, `c_AC = pair_bridge_count(g, prov, hub)`,
  expected count `E = deg_A·deg_C / nc`, significance `s = hypergeom_sf(c_AC, nc, deg_A, deg_C)` (lower = more extreme).

## The size-stratified empirical null + within-band enrichment score (NEW pure machinery, `scripts/enrichment_stats.py`)
For a query pair Q with (c_AC, deg_A, deg_C) against the corpus's background (all cross-paper gaps, c_AC ≥ 1, LEAVING
OUT Q):
1. **Band** every gap by its expected-count octave: `band = floor(log2(E))` (E>0 by construction). Q's band = its own
   octave.
2. **Size-matched background** = background gaps in Q's band. If `n_band < min_band=50`, WIDEN to `band ± 1` octave
   (then, if still `< min_band`, `band ± 2`), up to `widen_octaves = 1` step each side is tried first, then `2`; if
   still `< min_band` → Q is **VOID (band underpowered)**.
3. **Within-band empirical enrichment p** (Phipson-Smyth 2010 exact-permutation +1, conservative under ties):
   `empP(Q) = (#{background gaps in band with s ≤ s_Q} + 1) / (n_band + 1)`.
4. **HIT** iff `empP(Q) ≤ alpha_region = 0.05` (⇒ under H0 "Q behaves like a random same-band gap", P(hit) ≤ 0.05,
   conservatively — the exact binomial null rate).

## The exact enrichment test across the K positives (the PASS criterion)
- Run steps 1–4 on each of the K positives (their own corpora). `k = #hits`, over the `K` positives that are NOT VOID
  (target pair absent from the ranking OR band underpowered → excluded from K, reported separately).
- **Exact one-sided binomial test:** `p = exact_binomial_sf(k, K, alpha_region=0.05)` = P(X ≥ k | Binomial(K, 0.05)).
  Report `p` + the **Clopper-Pearson 95% CI** on the hit rate `k/K`.
- **PASS** iff `p < 0.05`. Otherwise **INCONCLUSIVE** (not a KILL — small K has limited power; report k/K + CI honestly).
- **Reported at two nested endpoints, both pre-registered; PRIMARY declared before the run:**
  - **PRIMARY = the n=3 strict-clean set (P1,P2,P3).** This is the headline claim.
  - **SECONDARY/sensitivity = the n=5 set (P1,P2,P3,S4,S5).** Robustness: does adding the 2 near-clean marginals change
    the verdict? A divergence (primary vs sensitivity) is itself reported as a gold-purity-dependence finding.
  - The VOID control (Mg↔migraine) and any positive that VOIDs are reported but NOT counted in either K.

## Frozen knobs (no change after the run)
`hub_percentile=0.90` · `max_edges=200000` · `max_gaps=` above the per-corpus total gap count (verified no truncation:
returned gap count < max_gaps) · background = raw-priority cross-paper gaps (c_AC≥1), leave-one-out on the query ·
band = `floor(log2(deg_A·deg_C/nc))` octave · `min_band=50` · widen `±1` then `±2` octaves · empirical p =
`(#{s_bg ≤ s_Q}+1)/(n_band+1)` · `alpha_region=0.05` (hit region) · enrichment test = exact binomial `P(X≥k|K,0.05)` ·
CI = Clopper-Pearson 95% · PASS = binomial `p<0.05` · PRIMARY endpoint = n=3 (P1,P2,P3).

## Honest pre-run predictions + caveats (NOT knobs; recorded to keep the result honest)
- **Power is intrinsically low** (exact binomial, region 5%): n=3 needs ≥2 hits for `p=0.007` (1 miss tolerated); n=5
  needs ≥3 hits for `p≈0.001` (2 misses tolerated); n=2 (if a primary VOIDs) is all-or-nothing (`2/2` → p=0.0025).
- **Clean gold is scarce** — the boundary triage (2 strict-clean canonical Swanson pairs of the whole vetted set) is a
  first-class finding substantiating Moreau 2023, reported regardless of the enrichment outcome.
- **Contamination caveat:** the empirical-null background is a size-matched BACKGROUND, not clean negatives (it may
  contain unlabeled true gaps); mitigated by the size-matched-background framing (Tumminello/Efron), NOT eliminated.
- **Same-E exchangeability caveat:** an E-octave band fixes the hypergeometric MEAN but not the VARIANCE (two pairs
  with equal E but different (deg_A,deg_C) shapes differ in null spread) → the empirical p is approximately, not
  exactly, size-controlled; acceptable for a weak existence proof, declared here.
- **Nrf2↔pancreatic is a wet-lab discovery** (DeNicola 2011), not a literature-mining Swanson case; it is a valid GATE
  test case (boundary 0, genuine latent A-B / B-C structure) but its provenance is flagged, and the n=2 strict-Swanson
  subset (P1,P2) is reported alongside as the maximally-conservative literature-mining-only readout.
- **Re-run + eyeball is the real validity gate** (it caught 3 truncation-class bugs in Plans 3/4/5). $0 (NCBI free +
  pure). No knob changes after the run.
