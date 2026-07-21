# Measured results — provenance for every number on the public surface

Every quantitative claim in `README.md` / `SKILL.md` is listed here with: its **exact scope**, the **harness**
that produced it, the **command to reproduce it**, and the **honest limit** that travels with it.

This exists because of R-1/R-2: *"never trust a proper noun or a statistic until a primary source confirms it."*
That rule applies to labcoat's own numbers. A reader should not have to take the front page on faith.

**Read this first — what "reproducible" means here, honestly:**

| Tier | Which numbers | What a reader can do from a clone |
|---|---|---|
| **Checkable offline, right now** | the saturation-gate calibration | `pytest tests/test_novelty_gate.py -q` — the curves ship as a fixture and the tests re-derive the claim. **No network, no credential.** |
| **Re-derivable in mechanism, but not as the same figure** | AUROC 0.889 · the N3 distance CONFIRM · the ~99.85% noise reduction | the harness ships and the command is below, but re-running needs a corpus build (hours, ~2GB of ML deps) and — for N3 — real OpenRouter spend. **For §1, a rebuild is a _new_ measurement, not a reproduction of this exact figure** — the snapshot behind 0.889 was not retained (see [Known gap](#known-gap-stated-rather-than-papered-over)). |
| **Not independently re-derivable** | the raw per-run report JSONs | they live outside the public tree. The harnesses that regenerate them ship; the specific run artifacts do not. **This is a real gap — see "Known gap" below.** |

---

## 1. N1 out-of-distribution gate — held-out-field AUROC **0.889 [0.874, 0.904]**

- **Cited at:** `README.md` (N1 bullet), `SKILL.md` §North-Star capabilities.
- **Harness:** `scripts/n1_offdist_roc.py` (pure core: `scripts/roc.py`, unit-tested in `tests/test_roc.py`).
- **Runbook:** [`n1-offdist-roc-runbook.md`](n1-offdist-roc-runbook.md) — read its §"Honest caveats" before quoting.
- **Corpus:** the OpenAlex ~25k-work deep corpus — [`n1-openalex-runbook.md`](n1-openalex-runbook.md).
- **Reproduce:**
  ```bash
  python scripts/n1_offdist_roc.py run \
    --snapshot _internal/n1-openalex-snapshot \
    --fields Musicology "Comparative literature" Numismatics "Art criticism" \
    --per-field 150 --cache-dir _internal/offdist-roc-cache \
    --out _internal/offdist-roc-report.json
  ```
  The quoted number is the **`heldout_field` layer** — real foreign-field text vs in-corpus, no synthetic bank,
  no random vectors. Do **not** quote `full_incl_random` (near-1.0 by construction; a sanity check only).
- **Scope + honest limits (do not soften):**
  - It is an **anti-out-of-corpus detector, not a novelty oracle.** It says a claim is far from *this corpus* —
    never that it is new to the world.
  - **The success criterion was NOT met.** The pre-set bar was FPR@TPR95 ≤ 5%; the measured FPR@TPR95 is **~0.45**.
    At its deployed threshold the gate flags ~5.2% of in-corpus queries and catches ~51% of OOD queries. The
    criterion is **unachievable on the current SPECTER2 margin** — that is reported as an honest failure, not tuned away.
    A good AUROC and an unmet operating-point criterion are not in conflict; both are true, and both belong in any quote.
  - **Field-dependent** — pooled AUROC hides per-field variation; prefer the `field_stratified` worst case.
  - **Titles-not-claims** — an upper bound on real performance (production queries are claims, not titles).
  - Narrow SPECTER2 distance band (~0.06 margin) → the measurement is real but thin.

## 2. N3 prior-art distance — engine > raw prompting, **DISTANT pairs only** (CMH p=7.4e-5)

- **Cited at:** `README.md` (N3 bullet), `SKILL.md` §North-Star capabilities.
- **Full numbers:** effect **+0.209**; Cochran-Mantel-Haenszel **p=7.4e-5**; cluster-bootstrap CI **[0.104, 0.320]**;
  **ICC=0** (no rater-cluster effect).
- **Harness:** `scripts/stage_b.py` (the CMH + cluster-bootstrap machinery; unit-tested in `tests/test_stage_b.py`)
  + `scripts/stage_b_measure.py` (the live measurement shell — spends real money, estimate-first, tolerance-gated).
- **Runbook / scope:** [`n3-live-runbook.md`](n3-live-runbook.md) §"Status of the N3 claim".
- **Scope + honest limits:**
  - **Distant domain pairs only.** Near pairs show **no** win. An earlier "raw-strong dominates" reading was
    overturned as a **tier artifact** — which is why the tier control is load-bearing, not decoration.
  - **This is the distance axis and nothing else.** The **soundness axis is HUMAN-GATED and unmeasured**: an LLM
    judge could not be validated past **~0.70** on hard negatives. It catches clear named-law violators but cannot
    separate a *subtly incoherent* cross-domain mapping from genuine novelty — both route COHERENT_NOVEL. Forcing
    that panel to a 0.8 bar biases the measurement, so the axis was left to a human expert instead of shipped.
  - "Beats raw prompting on prior-art distance" is **not** "produces sound or useful ideas." N3 stays ADVISORY.
  - The statistical machinery is unit-tested from the clone (`pytest tests/test_stage_b.py -q`); the *run* is not.

## 3. N2 ABC channel — **~99.85%** noise reduction (and the kept negative that outranks it)

- **Cited at:** `README.md` (N2 bullet), `SKILL.md` §North-Star capabilities.
- **What it is:** the PPMI-context + hub-exclusion fix cut the ABC structural-gap noise flood from **~8000 → ~12**
  candidates across the two characterization corpora (ML + biomedical) — ≈99.85%.
- **Harness:** `scripts/gap_channels.py` (`pmi_context_relatedness`, `hub_bridge_threshold`, `abc_whitespace` —
  unit-tested in `tests/test_gap_channels.py`) via `scripts/gaps_live.py`.
- **Runbook:** [`n2-live-runbook.md`](n2-live-runbook.md) (free path — no ML extras, no credential).
- **Reproduce the filtered-vs-unfiltered ratio on any corpus** (free, ~30s):
  ```bash
  python scripts/gaps_live.py gaps --query "cat:cs.LG" --n 200
  ```
  prints `structural_gaps: <filtered> (PPMI-filtered, ...) vs <unfiltered> (unfiltered)` — the mechanism behind the
  ratio. The exact ~99.85% figure is specific to the two characterization corpora, not a constant.
- **Scope + honest limits — the reduction is the *smaller* story:**
  - This is a win for the **machinery**, not evidence that ABC finds discoveries.
  - **The headline N2 result is a KILL, and it is kept:** the count/co-occurrence ABC channel **cannot discriminate
    a documented cross-literature discovery from big-literature spurious pairs.** The confound is literature **size**;
    neither IDF-specificity nor size-normalization (Association Strength / Salton cosine) rescued it.
  - That KILL was **pre-registered before the run** — [`n2-crosslit-prereg.md`](n2-crosslit-prereg.md), with
    pre-committed PASS/VOID/KILL semantics and an explicit anti-rescue rule. The follow-up
    [`n2-crosslit-optionC-prereg.md`](n2-crosslit-optionC-prereg.md) returned **INCONCLUSIVE (underpowered)** by its
    own decision rule (n=3, k=1, binomial p=0.143) — reported as inconclusive, not as the one positive case it contained.
  - A **semantic substrate** (MeSH/UMLS semantic-type prefilter, SemMedDB predications, LLM-relevance) is the known
    **deferred** next step.

## 4. Saturation gate — calibrated to **tau=0.30 / floor=0 / window=3** on three multi-loop curves

- **Cited at:** `README.md` (saturation-gate bullet), `SKILL.md` §Durable autonomy. This is the one calibration that
  **enforces by default**, so it carries the highest burden of proof — and it is the one you can check offline.
- **The three curves ship:** `tests/fixtures/novelty-gate-calibration-curves.json` — Exp1 LLM `[25,1,0,0,0,0]`
  (sharp), Exp2 CRISPR `[0,4,1,8,0,3]` (steady-productive), Exp3 AI-safety `[0,19,0,0,13,0]` (bursty).
- **Verify the claim from a clone — free, offline, ~0.1s:**
  ```bash
  python -m pytest tests/test_novelty_gate.py -q
  ```
  `test_calibration_adopted_params_classify_all_three_curves_with_zero_errors` replays the gate prospectively
  loop-by-loop over each curve and asserts zero false positives / false negatives.
  `test_calibration_window_2_is_rejected_because_it_false_fires_on_the_bursty_curve` reproduces the recorded
  reason `window=2` was rejected (it fires in the `[0,0]` valley at loop 4, before the burst of 13 arrives).
  These tests pass **only** for the documented `window=3` — `window=2` and `window=4` both fail them.
- **Scope + honest limits:**
  - **`tau=0.30` is UNDER-DETERMINED by this calibration.** The curves are tau-invariant (the Stage-1 seen-set dedup
    dominates the Stage-2 distance test), so tau is held over from the prior default, **not derived here**. `floor`
    and `window` *are* derived. The fixture records this.
  - Three curves is a **small** calibration set.
  - It is a **saturation** signal ("still finding new confirmed things?"), **not** a value-aware fitness function.
  - Even enforcing, the gate **pauses-and-pings — it never auto-stops** (corrigible by construction).

---

## Known gap (stated rather than papered over)

The per-run report JSONs (e.g. `offdist-roc-report.json`, the Stage-B adjudication sets) are **not** in the public
tree. So for §1 and §2 a reader gets *the harness, the command, the scope and the caveats* — but not the original
run artifact, and re-running is not free. **Those two numbers are, from a clone, taken on trust.**

**Sharper, for §1 specifically (do not soften):** the ~25k-work OpenAlex snapshot that produced 0.889 was **not
retained** (it was gitignored and never committable), the harness serializes only per-layer *summaries* — not the
per-item scores — and the recorded figure used a query-sampling configuration that is **not a committed flag**. The
computation is deterministic *given a fixed snapshot*, but that snapshot is gone and OpenAlex drifts, so a fresh
build is a **new** measurement on a drifted corpus — it does **not** reproduce this exact figure. Closing this
honestly means either **(a)** a fresh, **pre-registered** run that publishes its number *and* a re-derivable scores
fixture (the `tests/fixtures/novelty-gate-calibration-curves.json` pattern), or **(b)** adding per-item score
serialization so future runs ship such a fixture by default. Until one of those lands, 0.889 is a recorded
historical result, not a from-clone-reproducible one.

Ranked honestly, the surface is: §4 checkable offline · §3's mechanism free to re-run (its headline is a KILL —
a negative, which is the cheap direction to trust) · §1 and §2 trust-dependent. Publishing the run artifacts, or a
signed digest of them, is the open item. Until then this table is the honest statement of what is and is not
verifiable from what ships — not a claim that everything is.
