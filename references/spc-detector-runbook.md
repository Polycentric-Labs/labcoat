# SPC Detector Runbook — Poisson-CUSUM + Matched-ARL0

> **Status:** ADVISORY. The active yield-collapse detector in the live loop is
> `novelty_gate.yield_collapse` (the K-consecutive-low run rule). The Poisson-CUSUM
> in `scripts/spc.py` is a reference implementation for offline calibration and
> verify-to-kill comparison only. No switch in production without explicit owner approval.

---

## 1. Purpose

**Problem:** `novelty_gate.yield_collapse` uses a K-consecutive-low run rule (floor=0,
window=3) calibrated by inspection on a handful of recorded curves. It is the active
detector. Before committing to it long-term — or switching to a more statistically
principled alternative — we need a fair comparison on a common footing.

**This module provides:**
- A lower Poisson-CUSUM detector (count-data-correct, Lucas 1985)
- A Negative-Binomial generative model (over-dispersed counts, realistic for CNY)
- Seeded Monte-Carlo ARL0 and ARL1 simulators
- A binary-search matched-ARL0 calibrator (so comparisons happen at the same false-alarm
  rate)
- A finite-horizon PFA metric (more meaningful than infinite-horizon ARL0 for short runs)

---

## 2. Poisson-CUSUM Formula

**Reference:** Lucas, J.M. (1985). "Counted Data CUSUM's." *Technometrics*, 27(2), 129–144.

The **lower** CUSUM accumulates evidence of a downward shift (yield collapse):

```
S_0 = 0
S_t = max(0, S_{t-1} + (k - x_t))
alarm at t if S_t > h
```

Where:
- `x_t` — count at loop t (the CNY scalar)
- `k = (mu0 - mu1) / ln(mu0 / mu1)` — the reference value (Lucas 1985 Eq. 1); lies
  between `mu1` and `mu0`
- `mu0` — in-control rate (estimated from calibration data)
- `mu1` — collapse-state rate to detect (estimated from collapse examples)
- `h` — alarm threshold (set via matched-ARL0 calibration)

**Why not normal-theory CUSUM or EWMA?** Both assume constant variance and approximate
normality. CNY is a small integer count (typically 0–30) that is over-dispersed relative
to Poisson (variance > mean). Normal-theory methods are mis-specified here. The Poisson
CUSUM is count-data-correct and is the natural count analogue.

**Why lower, not upper?** We are detecting a collapse *downward* (yield falling toward
zero). The lower CUSUM accumulates when counts run *below* the reference k. An upward
CUSUM accumulates evidence of increase — irrelevant here.

---

## 3. Negative-Binomial Generative Model

Real CNY is over-dispersed: `Var(CNY) > E[CNY]`. The Negative-Binomial (NB) is the
standard over-dispersed count model:

```
X ~ NB(mu, r)    where Var(X) = mu + mu^2 / r
```

- `mu` — mean (set to mu0 for productive simulation, mu_collapse for collapse simulation)
- `r` — dispersion (r → ∞ recovers Poisson; r ≈ 1–5 is typical for over-dispersed counts)

**Implementation:** Gamma-Poisson mixture (`scripts/spc.py::nb_sample`):
```
lam ~ Gamma(shape=r, scale=mu/r)
x   ~ Poisson(lam)
```

**Why this matters for calibration:** If we calibrate ARL0 under a Poisson model but
actual CNY is NB with r=2, the false-alarm rate in deployment will differ. The offline
sweep (§6) covers a range of r values to bound this sensitivity.

---

## 4. Matched-ARL0 Calibration Protocol

**Goal:** compare the Poisson-CUSUM and the K-rule at the *same* false-alarm rate. An
unmatched comparison (e.g., both "calibrated by hand") is unfair and misleading.

**Procedure:**
1. Choose a target ARL0 (mean run length to false alarm on productive data). Typical
   values: 30, 50, 100, 200.
2. Call `match_arl0_cusum(mu0=..., mu1=..., gen_fn=..., target_arl0=..., ...)`. This
   binary-searches h so the CUSUM's Monte-Carlo ARL0 ≈ target.
3. For the K-rule: iterate over (floor, window) pairs; evaluate ARL0 via
   `simulate_arl0(krule_run_length(...), ...)`. Pick the pair closest to the same target.
4. With both detectors matched to the same ARL0, compare ARL1 and PFA(T).

**Important caveat — step-function ARL0 curve:** The Poisson CUSUM over integer counts
has a step-discontinuity ARL0 curve (e.g., h=3.2 → ARL0≈33, h=3.4 → ARL0≈67 with the
calibration parameters used in unit tests). A target ARL0 in a gap cannot be achieved
exactly; `match_arl0_cusum` returns the closest h found. The K-rule has similar
discreteness. Both detectors are therefore compared at "approximately matched" ARL0, not
exactly matched.

---

## 5. Finite-Horizon PFA

For short runs (5–20 loops), the infinite-horizon ARL0 is less useful than:

```
PFA(T) = P(false alarm by loop T | productive process)
```

Computed by `pfa_by_horizon(run_length_fn, gen_fn=..., T=..., n_runs=..., seed=...)`.

**Interpretation:**
- PFA(T=10) ≈ 0.05 means 5% of productive-process runs trigger a false alarm within 10
  loops. This is the finite-horizon analogue of a 5% type-I error rate.
- A detector with lower PFA(T) at the same ARL1 is strictly better for short-run usage.

---

## 6. How to Run the Offline Calibration Sweep

The calibration sweep lives in `_internal/` (gitignored). It is NOT a unit test — it
requires no embedder, no network, and no API spend (pure stdlib). It is run manually.

**Steps:**
1. Create `_internal/spc_calibration_sweep.py` (not committed).
2. Define a parameter grid:
   - `mu0` values: estimated from productive CNY history (e.g., 5, 10, 20)
   - `mu1` values: estimated from observed collapse floor (e.g., 0.1, 0.5, 1.0)
   - `r` (NB dispersion): sweep 1.0, 2.0, 5.0, 10.0 (Poisson limit)
   - K-rule: `(floor=0, window=2)`, `(floor=0, window=3)`, `(floor=1, window=3)`
   - Target ARL0 values: 30, 50, 100
3. For each (mu0, mu1, r, target_arl0):
   a. Find matched CUSUM h via `match_arl0_cusum`.
   b. Find matched K-rule (floor, window) via `simulate_arl0` sweep.
   c. Compute ARL1 for both via `simulate_arl1` on a saturating NB series (t_star=3).
   d. Compute PFA(T=10) for both.
   e. Replay the 3 real curves + `[25,10,5,3,2,1]` + `[5,0,0,4,3]` through both.
4. Output an ARL table (`_internal/spc_arl_table.csv`) and a pass/fail verdict.

**Sample invocation (pseudocode):**
```python
gen = lambda rng, n: simulate_productive(mu0, r, n, rng)
gen_c = lambda rng, n: simulate_saturating(mu0, mu1, r, t_star=3, n_loops=n, rng=rng)
matched = match_arl0_cusum(mu0=mu0, mu1=mu1, gen_fn=gen, target_arl0=target, ...)
cusum_arl1 = simulate_arl1(lambda s: poisson_cusum_run_length(s, mu0=mu0, mu1=mu1, h=matched["h"]),
                           gen_fn=gen_c, n_runs=2000, max_loops=200, seed=42)
krule_arl1 = simulate_arl1(lambda s: krule_run_length(s, floor=0, window=3),
                           gen_fn=gen_c, n_runs=2000, max_loops=200, seed=42)
```

---

## 7. Replacement Criterion (Verify-to-Kill)

The K-rule (`novelty_gate.yield_collapse`) is the ACTIVE detector. The Poisson-CUSUM is
ADVISORY. Replace the active detector ONLY if ALL of the following hold:

1. **ARL1 reduction ≥ 1 loop** on the saturating NB generative model, across the full
   dispersion sweep (r ∈ {1, 2, 5, 10}). Not just at one (mu0, mu1) pair.
2. **No worse PFA(T=10)** than the K-rule at the same matched ARL0. The CUSUM must not
   buy ARL1 gains by increasing short-horizon false-alarm risk.
3. **Replays correctly on all real recorded curves** — the 3 historical curves plus the
   synthetic `[25,10,5,3,2,1]` and `[5,0,0,4,3]` curves. The CUSUM must alarm at least
   as early as the K-rule on true collapse curves, and must NOT alarm earlier on
   productive/bursty curves.
4. **Owner sign-off** on the dispersion estimates (mu0, mu1, r) used for calibration,
   and on the chosen h. These parameters are estimated from n=3 (thin data) and the
   decision is sensitive to them.

---

## 8. Honest Caveats (Do Not Soften)

1. **Model-conditional ARLs.** The ARL0 and ARL1 values are conditional on the NB
   generative model being correct. If actual CNY has heavier tails, longer auto-
   correlation, or non-stationarity (e.g., trending mu0), the true false-alarm and
   detection rates will differ from the simulated values. These are model-conditional
   comparisons, not deployment guarantees.

2. **mu0, mu1 estimated from thin data.** `mu0` and `mu1` are estimated from n=3
   recorded runs (the calibration corpus as of 2026-06-26). The ARL surface is
   sensitive to these parameters — a 2× error in mu0 or mu1 can shift ARL1 by an order
   of magnitude. The dispersion sweep (§6) partially bounds this, but the coverage is
   not exhaustive.

3. **The K-rule is likely competitive for abrupt collapse.** For a step collapse (mu0 →
   mu_collapse instantly at t_star), the K-rule with window=3 and floor=0 alarms at
   t_star + 3 (deterministically, once all three post-collapse samples are at floor).
   The Poisson-CUSUM must accumulate S_t > h, which also takes ~3–5 loops at typical
   (mu0, mu1) settings. For abrupt collapse, neither detector has a decisive advantage.
   The CUSUM is more likely to win for *gradual* collapse (geometric decay), which is
   the realistic failure mode.

4. **Finite sample sizes in Monte-Carlo.** The unit tests use 300–500 runs for speed.
   The offline calibration sweep should use ≥2000 runs per configuration for stable ARL
   estimates. The step-function ARL0 curve (§4) means that even 2000 runs may have
   ≥10% relative error near a step discontinuity.

5. **No EWMA comparison.** EWMA (exponentially weighted moving average) is a third
   candidate that is also misspecified (Gaussian assumption) but known to be good for
   gradual shifts. It is deferred — not enough recorded gradual-collapse examples to
   calibrate. If the CUSUM loses to the K-rule, EWMA is the next candidate to evaluate.

6. **This build is pure stdlib and deterministic.** The only randomness is a seeded
   `random.Random`. Results are reproducible given the same Python version and seed.
   Python's `random.Random` is NOT cryptographically secure; it is not used for anything
   requiring security, only for Monte-Carlo simulation.

---

## 9. Module API Reference

```python
# scripts/spc.py — pure stdlib, no network, no embedder

poisson_cusum_collapse(history, *, mu0, mu1, h) -> dict
    # Batch: run the lower CUSUM over history; return {collapsed, cusum, k, n}

poisson_cusum_run_length(series, *, mu0, mu1, h) -> int | None
    # Streaming: 1-based loop index of first alarm, else None

krule_run_length(series, *, floor, window) -> int | None
    # Same footing as above but for novelty_gate.yield_collapse (the K-rule)

poisson_sample(lam, rng) -> int
    # Knuth Poisson variate for lam<700; lam<=0 -> 0; lam>=700 uses a Gaussian approximation
    # (guards the exp(-lam) underflow infinite-loop — defensive; the CNY sweep never reaches it)

nb_sample(mu, r, rng) -> int
    # Gamma-Poisson NB variate; mu<=0 -> 0

simulate_productive(mu0, r, n_loops, rng) -> list[int]
    # In-control NB series

simulate_saturating(mu0, mu_collapse, r, t_star, n_loops, rng, *, decay=None) -> list[int]
    # Collapse series: step (decay=None) or geometric decay (decay=tau float)

simulate_arl0(run_length_fn, *, gen_fn, n_runs, max_loops, seed) -> dict
    # Monte-Carlo ARL0; {mean, se, n_censored, n_runs}

simulate_arl1(run_length_fn, *, gen_fn, n_runs, max_loops, seed) -> dict
    # Monte-Carlo ARL1; {mean, se, n_missed, n_runs}

match_arl0_cusum(*, mu0, mu1, gen_fn, target_arl0, n_runs, max_loops, seed, tol, ...) -> dict
    # Binary-search h for CUSUM ARL0 ~ target; {h, arl0}

pfa_by_horizon(run_length_fn, *, gen_fn, T, n_runs, seed) -> float
    # P(false alarm by loop T) on productive series
```

---

*Author: Allen Byrd. Build 3b-i, 2026-06-26. Advisory until owner-approved switch.*
