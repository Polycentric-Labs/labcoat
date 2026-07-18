"""labcoat SPC — count-data yield-collapse detection. PURE, deterministic, stdlib only (the only randomness is a
seeded random.Random). The lower POISSON-CUSUM (Lucas 1985, "Counted Data CUSUM's", Technometrics 27:129-144) is the
count-data-correct detector for a sustained DOWNWARD shift in CNY (a small over-dispersed count) — normal-theory
CUSUM/EWMA assume constant sigma + normality, both violated. Calibration uses a NEGATIVE-BINOMIAL generative model
(over-dispersion) + matched-ARL0. The detector is ADVISORY; the active loop detector stays novelty_gate.yield_collapse
until an owner-approved switch. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import math
import random
import statistics
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import novelty_gate


def _cusum_k(mu0: float, mu1: float):
    """Lucas (1985) lower reference value k = (mu0-mu1)/ln(mu0/mu1) (lies between mu1 and mu0). None if invalid."""
    if mu0 <= 0 or mu1 <= 0 or mu1 >= mu0:
        return None
    return (mu0 - mu1) / math.log(mu0 / mu1)


def poisson_cusum_collapse(history, *, mu0, mu1, h) -> dict:
    """Lower Poisson-CUSUM (Lucas 1985). Detects a sustained DOWNWARD shift mu0->mu1 (mu1<mu0) in a count series:
    S_t = max(0, S_{t-1} + (k - x_t)) with k = (mu0-mu1)/ln(mu0/mu1); collapse when S_t > h (accumulates when counts
    run below k). Guards mu0<=0 / mu1<=0 / mu1>=mu0 -> never fires. Pure. Returns {collapsed, cusum, k, n}.
    NOTE: `cusum` is the value AFTER all n observations (the CUSUM keeps running past the first alarm), NOT the value
    at the first alarm point — so `collapsed=True` with a small/zero `cusum` is possible if late counts recovered.
    Use `poisson_cusum_run_length` for the first-alarm index."""
    k = _cusum_k(float(mu0), float(mu1))
    if k is None:
        return {"collapsed": False, "cusum": 0.0, "k": None, "n": len(history or []),
                "reason": "invalid config (need 0<mu1<mu0)"}
    s, collapsed = 0.0, False
    for x in (history or []):
        s = max(0.0, s + (k - float(x)))
        if s > float(h):
            collapsed = True
    return {"collapsed": collapsed, "cusum": s, "k": k, "n": len(history or [])}


def poisson_cusum_run_length(series, *, mu0, mu1, h):
    """Index (1-based) of the FIRST loop the lower Poisson-CUSUM alarms, else None. Single O(n) pass (the ARL
    primitive). None for an invalid config."""
    k = _cusum_k(float(mu0), float(mu1))
    if k is None:
        return None
    s = 0.0
    for i, x in enumerate(series or []):
        s = max(0.0, s + (k - float(x)))
        if s > float(h):
            return i + 1
    return None


def krule_run_length(series, *, floor, window):
    """Index (1-based) of the FIRST loop novelty_gate.yield_collapse flags collapse on the growing prefix, else None.
    Puts the K-rule on the same run-length footing as the CUSUM for a fair ARL comparison."""
    seq = list(series or [])
    for i in range(1, len(seq) + 1):
        if novelty_gate.yield_collapse(seq[:i], floor=floor, window=window)["collapsed"]:
            return i
    return None


_KNUTH_LAM_MAX = 700.0  # above this, exp(-lam) underflows toward 0.0 (== 0.0 near lam~745) -> Knuth's `p<=L` test
                        # can never be true -> INFINITE LOOP. Switch to the Gaussian approximation there.


def poisson_sample(lam, rng) -> int:
    """Poisson(lam) variate. lam<=0 -> 0. For lam < 700: Knuth's exact algorithm (O(lam) expected iterations, NOT
    O(exp(lam)) — the iteration count IS the Poisson value). For lam >= 700: a Gaussian approximation
    Poisson(lam) ~ Normal(lam, lam) (the Normal approx is excellent for large lam) — this guards the exp(-lam)
    UNDERFLOW infinite loop (exp(-lam)->0.0 near lam~745). nb_sample can in principle produce a large lam for very
    big mu / small r, so this guard is defensive (the planned CNY sweep, mu0<=20, never reaches it). Pure (seeded rng).
    The threshold preserves the EXACT Knuth path for the entire normal CNY regime (lam<<700), so seeded results are
    unchanged for realistic inputs."""
    lam = float(lam)
    if lam <= 0:
        return 0
    if lam >= _KNUTH_LAM_MAX:
        return max(0, int(round(rng.gauss(lam, lam ** 0.5))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


def nb_sample(mu, r, rng) -> int:
    """Negative-binomial count with mean `mu` and size/dispersion `r` (variance = mu + mu^2/r; r->inf ~ Poisson)
    via the Gamma-Poisson mixture: lam ~ Gamma(shape=r, scale=mu/r), x ~ Poisson(lam). mu<=0 -> 0. Pure (seeded rng)."""
    mu = float(mu)
    if mu <= 0:
        return 0
    lam = rng.gammavariate(float(r), mu / float(r))
    return poisson_sample(lam, rng)


def simulate_productive(mu0, r, n_loops, rng):
    """An in-control CNY series: n_loops NB(mu0, r) draws. Pure (seeded rng)."""
    return [nb_sample(mu0, r, rng) for _ in range(int(n_loops))]


def simulate_saturating(mu0, mu_collapse, r, t_star, n_loops, rng, *, decay=None):
    """A saturating series: NB(mu0,r) for loops < t_star, then collapse. decay None -> step to NB(mu_collapse,r);
    decay=tau (float) -> geometric mean decay mu_t = max(mu_collapse, mu0*exp(-(t-t_star)/tau)) NB-sampled. Pure."""
    out = []
    for t in range(int(n_loops)):
        if t < int(t_star):
            out.append(nb_sample(mu0, r, rng))
        elif decay is None:
            out.append(nb_sample(mu_collapse, r, rng))
        else:
            mu_t = max(float(mu_collapse), float(mu0) * math.exp(-(t - int(t_star)) / float(decay)))
            out.append(nb_sample(mu_t, r, rng))
    return out


def _arl(run_length_fn, *, gen_fn, n_runs, max_loops, seed):
    rng = random.Random(seed)
    rls, n_event = [], 0
    for _ in range(int(n_runs)):
        rl = run_length_fn(gen_fn(rng, int(max_loops)))
        if rl is None or rl > max_loops:
            rls.append(int(max_loops))            # right-censored at the horizon
        else:
            rls.append(rl); n_event += 1
    mean = statistics.fmean(rls)
    se = (statistics.stdev(rls) / (len(rls) ** 0.5)) if len(rls) > 1 else 0.0  # sample stdev (N-1) for the SEM
    return mean, se, n_event


def simulate_arl0(run_length_fn, *, gen_fn, n_runs, max_loops, seed) -> dict:
    """Mean run length to FALSE alarm on PRODUCTIVE series (want LARGE). gen_fn(rng, n_loops)->series. Right-censored
    at max_loops. Returns {mean, se, n_censored, n_runs}. Seeded -> deterministic."""
    mean, se, n_event = _arl(run_length_fn, gen_fn=gen_fn, n_runs=n_runs, max_loops=max_loops, seed=seed)
    return {"mean": mean, "se": se, "n_censored": int(n_runs) - n_event, "n_runs": int(n_runs)}


def simulate_arl1(run_length_fn, *, gen_fn, n_runs, max_loops, seed) -> dict:
    """Mean run length to DETECT on SATURATING series (want SMALL). gen_fn(rng, n_loops)->series. A non-detection
    counts as max_loops (reported as n_missed). Returns {mean, se, n_missed, n_runs}. Seeded."""
    mean, se, n_event = _arl(run_length_fn, gen_fn=gen_fn, n_runs=n_runs, max_loops=max_loops, seed=seed)
    return {"mean": mean, "se": se, "n_missed": int(n_runs) - n_event, "n_runs": int(n_runs)}


def match_arl0_cusum(*, mu0, mu1, gen_fn, target_arl0, n_runs=2000, max_loops=2000, seed=0,
                     tol=0.05, h_lo=0.0, h_hi=200.0, max_iter=40) -> dict:
    """Binary-search the CUSUM threshold h so its ARL0 (under gen_fn) ~ target_arl0 (within tol*target). ARL0 is
    monotone increasing in h; the SAME seed is reused each evaluation so ARL0(h) is a deterministic monotone
    function (clean bisection). Returns the closest {h, arl0} found. Seeded -> deterministic.
    NOTE: for small counts the ARL0(h) curve is a STEP function (integer paths quantize h), so an exact target may be
    unreachable — the bisection then returns the nearest achievable best-found (do NOT read it as exact)."""
    if max_loops < target_arl0:
        raise ValueError(f"max_loops ({max_loops}) must be >= target_arl0 ({target_arl0}): otherwise censoring "
                         f"dominates (every run hits the horizon), ARL0 saturates below target, and the bisection "
                         f"drives h to h_hi and returns a wrong threshold.")
    lo, hi, best = float(h_lo), float(h_hi), None
    for _ in range(int(max_iter)):
        h = (lo + hi) / 2.0
        rl = lambda s, _h=h: poisson_cusum_run_length(s, mu0=mu0, mu1=mu1, h=_h)
        arl0 = simulate_arl0(rl, gen_fn=gen_fn, n_runs=n_runs, max_loops=max_loops, seed=seed)["mean"]
        if best is None or abs(arl0 - target_arl0) < abs(best["arl0"] - target_arl0):
            best = {"h": h, "arl0": arl0}
        if abs(arl0 - target_arl0) <= tol * target_arl0:
            return {"h": h, "arl0": arl0}
        if arl0 < target_arl0:
            lo = h
        else:
            hi = h
    return best


def pfa_by_horizon(run_length_fn, *, gen_fn, T, n_runs, seed) -> float:
    """P(false alarm by loop T) on PRODUCTIVE series — the finite-horizon metric (loops run ~5-20, so this is more
    meaningful than infinite-horizon ARL0). Fraction of runs whose alarm index <= T. Seeded."""
    rng = random.Random(seed)
    hits = 0
    for _ in range(int(n_runs)):
        rl = run_length_fn(gen_fn(rng, int(T)))
        if rl is not None and rl <= T:
            hits += 1
    return hits / int(n_runs)
