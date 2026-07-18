# N2 Cross-Literature ABC — Phase-3 Pre-Registration (Swanson known-answer measurement)

> Committed BEFORE the run to lock every knob (honesty stake: no post-hoc tuning; any change after seeing results
> converts the run to exploratory/uncalibrated, not a PASS). Author: Allen Byrd. Full results write-up: private
> working notes (2026-07-01, not published in this repo). This file is the standing honesty record.

## Question
Does the answer-blind global cross-paper ABC ranking place BOTH documented Swanson pairs above an injected
hard-negative set AND above the 95th-percentile empirical null of distractor↔distractor pairs — under EACH of two
pre-registered priorities? A PASS is a **weak existence proof** ("the machinery CAN recover documented cross-lit
gaps"), NEVER a discovery or precision rate.

## Cases (BOTH mandatory; the 2nd is held-out with knobs frozen — zero re-tuning)
1. **fish-oil ↔ Raynaud's** (Swanson 1986). target_a = {eicosapentaenoic acid, fish oils, docosahexaenoic acids,
   fatty acids, omega-3}; target_c = {raynaud disease}.
2. **magnesium ↔ migraine** (Swanson 1988). target_a = {magnesium}; target_c = {migraine disorders, migraine}.

## Corpus (answer-blind)
PubMed/MeSH via E-utilities, `publication year ≤ 1985`, `retmax = 500` per topic. Each case = its 2 target topics +
the SHARED 7 distractor literatures (chosen blind to either bridge): **malaria, epilepsy, glaucoma, psoriasis,
asthma, osteoporosis, schizophrenia**. Concept lists = per-doc MeSH descriptors, lowercased, `strip_check_tags`
applied. Sub-corpus/topic tags are used ONLY for the provenance-aware hub, the target/distractor anchors, and
reporting — NEVER as a ranking feature. **Boundary guard:** assert 0 pre-1985 direct target-A↔target-C co-mentions
(else the "undiscovered public knowledge" premise fails → VOID).

## The two FROZEN priorities (both pre-registered; report both)
- **raw** = `cross_paper_bridge_strength`: Σ over shared non-hub CROSS-paper bridges B of `|prov[{a,B}] ∪ prov[{B,c}]|`.
- **specificity** = `specificity_weighted_bridge_strength`: same, each bridge B down-weighted by
  `idf(B) = log2(1 + n_concepts / degree(B))` (textbook Swanson-LBD generic-B-term suppression).

## Frozen knobs
- `hub_percentile = 0.90` (provenance-aware `topic_aware_hub_bridges`).
- `max_edges = 200000` (NO truncation of the real graph).
- `min_pool = 30` (VOID if the global cross-paper gap pool is smaller — underpowered).
- `null_pct = 95.0`.
- **Empirical null = ALL `C(7,2)=21` distractor↔distractor pair strengths**, a pair surfacing NO gap counted as a
  true-negative competitor at **strength 0.0** (not dropped). Target must strictly exceed the 95th percentile.
- **Hard-negatives (5 known-false distractor pairs)**, likewise 0.0 if no gap; target must strictly out-rank ALL:
  (malaria,glaucoma), (epilepsy,osteoporosis), (psoriasis,schizophrenia), (asthma,glaucoma), (malaria,osteoporosis).

## Verdict (per case × per priority)
- **VOID** — target pair absent from the ranking (bridge not surfaced) OR pool < `min_pool`. (Substrate/power finding.)
- **KILL** — target present but a hard-negative out-scores it, OR it fails to beat the 95th-pct empirical null.
  (Honest negative about the priority's discrimination.)
- **PASS** — out-ranks ALL hard-negatives AND beats the 95th-pct null.
- **Overall per priority** = PASS iff BOTH cases PASS.

## Considered deviation from the design spec (declared)
The spec §4 named a "K-shuffle provenance-label permutation null." It is operationalized here as the **empirical
distractor↔distractor null** — cheaper, more interpretable, and MORE adversarial (it uses the real high-strength
spurious cross-lit pairs the Task-14 checkpoint surfaced, e.g. malaria–psoriasis, rather than a synthetic shuffle).
Frozen before the run.

## Honest pre-run prediction (NOT a knob; recorded to keep the result honest)
The Task-14 checkpoint showed **raw** count-weighted strength is literature-size-confounded (target top 0.02% but
~23 large-literature pairs outrank it) → **raw is predicted to KILL**. **specificity** MAY rescue the target IF its
bridges are genuinely more specific than the distractors' generic sharing — but that is exactly what this run
MEASURES; the priority formula was fixed on principle (IDF B-term suppression), not tuned to the target's rank.

## Reporting
Report the full 2×2 (case × priority) VOID/KILL/PASS table with target rank/strength, the null 95th-pct value, pool
size, and hard-negative strengths. Existence-proof framing only. No knob may change after the run.

## ADDENDUM (2026-07-02) — Association-Strength discriminating metric (Plan 4; frozen BEFORE the AS re-run)
After the raw+specificity KILL, an Exhaustive `/polycentric-labcoat` pass (primary-source-verified; private working
notes, 2026-07-02) identified the fix for the literature-SIZE confound = size-normalized association scoring. This addendum FREEZES two
additional priorities + a gate, run on the **SAME** frozen ≤1985 corpus + **SAME** 9 pre-registered pairs + **SAME**
answer-blindness + **SAME** hub-exclusion/cross-paper classifier (apples-to-apples with the KILL; only the scorer changes):
- **association_strength** (PRIMARY): `AS(A,C) = c_AC / (deg(A)·deg(C))`, deg = non-hub bridge-neighbour count,
  c_AC = shared non-hub cross-paper bridge count. Ranked by AS effect size. **Hypergeometric significance GATE:** keep
  gaps with `c_AC ≥ min_support=3` AND `hypergeom_sf(c_AC, Nc, deg(A), deg(C)) < alpha=0.01` (Nc = distinct non-hub
  concepts). Rank by AS, **NEVER by p**. Citation: van Eck & Waltman 2009 JASIST 60(8):1635-1651 (CONFIRMED).
- **salton_cosine** (robustness column): `c_AC / √(deg(A)·deg(C))` — resists AS's tiny-literature over-reward.
- Reported diagnostics: `target_hub_share` (fraction of the target's bridges that are high-degree ≥ 90th-pct non-hub
  degree — attributes a PARTIAL result to bridge-degree-variance vs semantics) + `pmi_of_target` = `log2(AS·Nc)`
  (AS-only; rank-correlates with AS, reported not ranked-on).
- **PASS criterion (per case, under association_strength):** the target / 95th-pct-distractor ratio crosses **> 1.0**
  AND the target is NOT out-ranked by any big-literature distractor pair (the existing VOID/KILL/PASS verdict, PLUS the
  ratio > 1.0 requirement). VOID/KILL semantics unchanged.
- **Honest pre-run prediction (recorded, not a knob):** the research predicts a MOST-LIKELY **PARTIAL** result — AS
  cancels the FIRST-ORDER endpoint-size confound but not the residual hub-bridge-degree-variance; if AS also KILLs, the
  confound is semantic → the deferred semantic-prefilter / SemMedDB path is mandated. Re-finding a Swanson pair does NOT
  prove discrimination (Moreau 2023, btad090 — time-sliced Swanson gold is noise-dominated). No knob changes after the run.

## ADDENDUM 2 (2026-07-02) — Structural-vs-Semantic residual PROBE (Plan 5 / Option A; frozen BEFORE the probe)
After the AS/cosine PARTIAL, before committing to a semantic build (or closing), this DIAGNOSTIC probe attributes the
residual to STRUCTURAL (hub-antagonism) vs SEMANTIC (coherence), on the SAME frozen ≤1985 corpus + SAME fish-oil↔Raynaud
case + SAME answer-blindness, at $0. The trigger below was HARDENED after a 3-lens adversarial validation
(forking-paths / measurement-validity / decidability): the naive "target out-ranks distractors on salton_cosine" trigger
was REJECTED as confound-UNSAFE (cosine's tiny-literature over-reward can lift the small Raynaud endpoint for reasons of
literature SIZE — the very confound this line exists to escape), and a same-case "confirmatory PASS" was REJECTED as
circular (entailed by the selection that spawns it). The frozen trigger is instead **target-intrinsic size-controlled
significance recovery**, and the probe is **diagnostic-only**.

- **Scope:** the fish-oil↔Raynaud case ONLY (where the residual is PARTIAL, hence attributable). Held-out Mg↔migraine
  stays VOID (out of scope).
- **DIAGNOSTIC-ONLY (honesty guard):** emits exactly one ATTRIBUTION ∈ {STRUCTURAL, SEMANTIC}. Issues NO VOID/KILL/PASS.
  **No config-relaxation run on the fish-oil case can upgrade the mission verdict** (only a NEW case or NEW metric family
  could). **BOTH branches CLOSE the arc at PARTIAL.** No same-case "confirmatory" run is spawned.
- **Configs (hub-relaxation sweep):** decision scorer = `association_strength` + the frozen gate (`min_support=3`,
  `alpha=0.01`, `hypergeom_sf`); `salton_cosine` reported for DESCRIPTIVE continuity ONLY (NOT a decision input — the
  rejected confound). All else unchanged from Addendum 1.
  - **C0** `hub_percentile=0.90` (anchor; AS VOID, already measured) · **C1** `0.95` (realistic/shippable) ·
    **C2** `0.99` (realistic/shippable) · **C3** `hub=∅` — DESCRIPTIVE ENDPOINT ONLY (not shippable — readmits the
    generic-hub noise-flood; **can never yield STRUCTURAL**; it only disambiguates "0.99 still too aggressive" from
    "keeping the bridges never helps").
- **Reported per config:** (decision) the target's `c_AC` + whether it clears `c_AC ≥ 3` AND
  `hypergeom_sf(c_AC, nc, deg(A), deg(C)) < 0.01` (size-controlled by construction — the hypergeom tail conditions on
  `deg(A)·deg(C)·nc`); (descriptive) cosine `R(cfg)` = target/95th-pct-distractor ratio, null built identically to
  `measure_case` (all C(7,2)=21 distractor pairs, no-gap → 0.0); (corroborating, NOT a gate conjunct) `target_hub_share`
  vs the {median, 90th-pct} `hub_share_fraction` over ONLY distractor pairs with ≥1 non-hub bridge (no-gap pairs excluded,
  never counted 0.0).
- **FROZEN attribution rule (binary; no post-hoc judgment).** "Clears the gate at cfg" = `c_AC ≥ 3` AND
  `hypergeom_sf < 0.01`; at C0 the target does NOT clear (the AS VOID).
  - **STRUCTURAL** iff the target clears at **C1 or C2** (report the least-relaxed; C1 stronger). → close at PARTIAL +
    record the clearing percentile as a lead for a FUTURE multi-positive eval.
  - **SEMANTIC** otherwise — including clears ONLY at C3 = **SEMANTIC (EXHAUSTED)** (rescue only under the non-shippable
    noise-flood is not a structural fix). → close at PARTIAL; SemMedDB typed predications = the out-of-scope principled path.
  - No MIXED category; the outcome is a deterministic function of gate-survival at {C0, C1, C2, C3}.
- **Mechanical dependencies (target-neutral; declared; same class as the earlier `min_strength=0` fix):** (1) a
  `hub_override` param on `measure_case` (default = computed hub) so C3 can pass `hub=frozenset()` — `hub_percentile`
  cannot reach ∅ (`topic_aware_hub_bridges` caps `idx` at `n-2`, always keeping the max-degree hub excludable); (2)
  surface the target's `c_AC` + `hypergeom_sf` per cfg (computed in the gating loop, not currently returned); (3)
  operator-harness glue looping the existing pure `hub_share_fraction` over distractor pairs (≥1-bridge only). None touch
  the frozen scorer, the gate constants, or the answer-blind corpus.
- **Cost $0** (deterministic, cached corpus, no LLM/API). **Honest backstop:** recovering significance on n=1 does not
  prove discrimination (Moreau 2023); the probe only attributes the PARTIAL's cause. No knob changes after the run.

## ADDENDUM 3 (2026-07-02) — max_gaps truncation CORRECTION (completeness fix; frozen BEFORE the re-run)
The Addendum-2 probe's $0 re-run (honesty gate: "always re-run + eyeball before interpreting a VOID/KILL") uncovered that
the ENTIRE frozen Plan-3/Plan-4 headline was computed under an UNSTATED enumeration cap: `cross_paper_gaps_ranked` has a
hardcoded `max_gaps=100000` default that `measure_case` never overrode. VERIFIED (a private diagnostic script, 2026-07-02,
$0): at hub_percentile=0.90 the fish-oil case enumerates **737,818** cross-paper gaps; the target
(eicosapentaenoic acid, raynaud disease) has **c_AC=67** non-hub cross-paper bridges and **CLEARS** the size-controlled
hypergeometric gate (p=4.8e-4, deg 275×731, nc=4383), but its AS effect size (3.3e-4) ranks it **662,920 / 737,818** — far
beyond the 100k cap → TRUNCATED before the AS gate ran.

CONSEQUENCES:
- **The Plan-4 "AS VOID = hub-antagonism → <3 non-hub bridges" diagnosis is FALSIFIED.** The target has 67 non-hub
  bridges and passes the gate; the AS VOID is a max_gaps TRUNCATION artifact, not hub-exclusion stripping the target.
- The cap contaminates ALL priorities via the empirical null (distractor↔distractor pairs truncated past 100k are
  backfilled to 0.0, deflating the null → the cosine ratio 0.856 and the raw/spec nulls are suspect). The Mg↔migraine
  VOIDs may likewise be truncation, not genuine absence.

CORRECTION (FROZEN here BEFORE the re-run):
- Add a target-neutral `max_gaps` parameter to `measure_case` (threaded to `cross_paper_gaps_ranked`), and re-run the
  ENTIRE headline (both cases × all 4 priorities) + the Addendum-2 probe with `max_gaps` set ABOVE the total enumerated
  gap count for every case/config (verified no truncation: returned gap count < max_gaps). This restores Addendum-1's
  STATED intent ("max_edges=200000 = NO truncation of the real graph") to the gap enumeration, which the 100k gap cap
  silently violated.
- This is a COMPLETENESS correction, NOT a criterion change: no scorer, gate constant (min_support=3, alpha=0.01), hub
  rule, null definition, or verdict threshold changes. Same class as the Plan-3 max_edges=2000 catch and the Plan-4
  min_strength=1 catch — both found by this same $0-re-run gate. The truncation-free numbers REPLACE the
  truncation-contaminated frozen table; the honest record is "Plan-3/4 was under an unstated 100k gap truncation;
  corrected truncation-free results follow."
- **Addendum-2 rule note:** the probe's frozen attribution rule assumed the target was VOID at C0 because it failed the
  gate. The re-run confirms it CLEARS the gate at C0 (never a gate failure) — so the structural-rescue hypothesis is
  falsified directly (the target's significance was never hub-suppressed). The residual is characterized on the
  truncation-free numbers, reported honestly, existence-proof framing only. No criterion changes after the re-run.

## ADDENDUM 4 (2026-07-02) — Option C: gate-discrimination across K positives (SEPARATE pre-registration)
Plan 5's NARROW gate-carried AS PASS was n=1 (fish-oil↔Raynaud). Option C tests whether the size-conditioning
hypergeometric GATE discriminates across MULTIPLE documented, cleanly-time-sliced cross-lit discoveries via a
size-stratified EMPIRICAL NULL + an EXACT binomial ENRICHMENT test (the design transformed by a scoped Deep labcoat
pass on the gate's FDR/validity — Efron 2004 / Maslov-Sneppen 2002 / Tumminello 2011 / Minus 2025, all controller-
verified). It is a NEW eval (new corpora, new statistical test, new pure machinery) with its own frozen knobs, so its
full pre-registration lives in a dedicated file: **`references/n2-crosslit-optionC-prereg.md`** (owner-ratified path:
n=3 primary + n=5 sensitivity, 2026-07-02). A live boundary-guard triage BEFORE freezing falsified the assumed
~5-clean-positive premise (only 2 strictly-clean canonical Swanson pairs survive) — that scarcity is itself a
first-class finding. See that file for the gold set, corpus construction, the empirical-null banding, and the PASS
criterion. This addendum is the pointer; that file is the standing Option-C honesty record.
