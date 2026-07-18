"""labcoat N2 Option C — the gate-discrimination ENRICHMENT statistics. PURE (stdlib + math.lgamma; NEVER
scipy/numpy). A size-stratified EMPIRICAL NULL (endpoint-degree octave bands; Tumminello 2011) recalibrates the
over-dispersed per-gap hypergeometric p (Efron 2004), and an EXACT binomial ENRICHMENT test (Fisher 1935 /
Clopper-Pearson 1934; Minus 2025 — no AUROC at small n) asks whether K documented cross-lit positives land in the
low-empirical-FPR region MORE than a size-matched background. See references/n2-crosslit-optionC-prereg.md for the
frozen design. Deterministic; no network/key/clock. ADVISORY. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import math
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gap_channels as gc   # reuse the tested pure hypergeom_sf (DRY; no re-implementation)


def octave_band(e):
    """Expected-count octave band = floor(log2(E)), E = deg_A*deg_C/nc (the hypergeometric mean the gate normalizes
    by). None for E <= 0 / None. Pure."""
    if e is None:
        return None
    e = float(e)
    if e <= 0.0:
        return None
    return math.floor(math.log2(e))


def _log_choose(n, k):
    if k < 0 or k > n or n < 0:
        return -math.inf
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def exact_binomial_sf(k, n, p) -> float:
    """P(X >= k) for X ~ Binomial(n, p). Pure (lgamma + log-sum-exp). k<=0 -> 1.0; k>n -> 0.0. Edge p in {0,1}."""
    n, k, p = int(n), int(k), float(p)
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0.0:
        return 0.0            # X = 0 a.s. -> P(X >= k>=1) = 0
    if p >= 1.0:
        return 1.0            # X = n a.s. -> P(X >= k<=n) = 1
    lp, lq = math.log(p), math.log1p(-p)
    terms = [_log_choose(n, i) + i * lp + (n - i) * lq for i in range(k, n + 1)]
    mx = max(terms)
    s = mx + math.log(sum(math.exp(t - mx) for t in terms))
    return max(0.0, min(1.0, math.exp(s)))


def exact_binomial_cdf(k, n, p) -> float:
    """P(X <= k) for X ~ Binomial(n, p) = 1 - P(X >= k+1). Pure. k<0 -> 0.0; k>=n -> 1.0."""
    n, k = int(n), int(k)
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return max(0.0, min(1.0, 1.0 - exact_binomial_sf(k + 1, n, p)))


def _bisect_monotone(f, lo=0.0, hi=1.0, *, tol=1e-14, iters=200):
    """Root of a monotone f on [lo,hi] (works for increasing OR decreasing f — brackets the sign change). Pure."""
    flo = f(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        fmid = f(mid)
        if (flo <= 0.0) == (fmid <= 0.0):
            lo, flo = mid, fmid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def clopper_pearson_ci(k, n, *, conf: float = 0.95):
    """Exact (Clopper-Pearson 1934) two-sided CI for a binomial proportion k/n at confidence `conf`. Solved by
    bisection on the exact binomial tails: lower solves P(X>=k | n, lo)=alpha/2, upper solves P(X<=k | n, hi)=alpha/2.
    k=0 -> lo=0; k=n -> hi=1. Pure/deterministic. Returns (lo, hi)."""
    k, n = int(k), int(n)
    if n <= 0:
        return (0.0, 1.0)
    a2 = (1.0 - float(conf)) / 2.0
    lo = 0.0 if k == 0 else _bisect_monotone(lambda p: exact_binomial_sf(k, n, p) - a2)
    hi = 1.0 if k >= n else _bisect_monotone(lambda p: exact_binomial_cdf(k, n, p) - a2)
    return (lo, hi)


def size_banded_empirical_p(target, background, nc, *, alpha: float = 0.05, min_band: int = 50,
                            widen_octaves: int = 2) -> dict:
    """Score one query pair's within-size-band empirical enrichment. `target`=(c_AC, deg_A, deg_C);
    `background`=iterable of (c_AC, deg_A, deg_C) for the corpus's other cross-paper gaps (LEAVE-ONE-OUT: the caller
    must exclude the target pair itself). Band each gap by octave(E=deg_A*deg_C/nc); take the background in the
    target's band, WIDENING to |band diff| <= w for w=0,1,...,widen_octaves until n_band >= min_band (else VOID).
    Within-band empirical enrichment p (Phipson-Smyth 2010 +1) = (#{bg: s <= s_target} + 1)/(n_band + 1), s =
    hypergeom_sf(c_AC, nc, deg_A, deg_C) (lower s = more extreme). HIT iff empirical_p <= alpha. Pure; hypergeom
    memoized locally on (c,da,dc). Returns {voided, hit, empirical_p, n_band, band, band_width, target_s, reason?}."""
    c_t, da_t, dc_t = int(target[0]), int(target[1]), int(target[2])
    nc = int(nc)
    void = {"voided": True, "hit": False, "empirical_p": None, "n_band": 0, "band": None,
            "band_width": None, "target_s": None}
    if da_t <= 0 or dc_t <= 0 or nc <= 0:
        return {**void, "reason": "degenerate target size (deg or nc <= 0)"}
    band_t = octave_band((da_t * dc_t) / nc)
    if band_t is None:
        return {**void, "reason": "target E <= 0"}
    # background bands (skip degenerate)
    bg = []
    for g in (background or []):
        c, da, dc = int(g[0]), int(g[1]), int(g[2])
        if da <= 0 or dc <= 0:
            continue
        b = octave_band((da * dc) / nc)
        if b is not None:
            bg.append((b, c, da, dc))
    # widen until the quota is met
    sel, w_used = [], None
    for w in range(0, int(widen_octaves) + 1):
        sel = [(c, da, dc) for (b, c, da, dc) in bg if abs(b - band_t) <= w]
        if len(sel) >= int(min_band):
            w_used = w
            break
    if w_used is None:
        return {**void, "band": band_t, "n_band": len(sel), "band_width": int(widen_octaves),
                "reason": f"band underpowered (n_band {len(sel)} < min_band {min_band})"}
    _memo = {}

    def s_of(c, da, dc):
        key = (c, da, dc)
        v = _memo.get(key)
        if v is None:
            v = gc.hypergeom_sf(c, nc, da, dc)
            _memo[key] = v
        return v

    s_t = s_of(c_t, da_t, dc_t)
    le = sum(1 for (c, da, dc) in sel if s_of(c, da, dc) <= s_t)
    n_band = len(sel)
    emp_p = (le + 1) / (n_band + 1)
    return {"voided": False, "hit": emp_p <= float(alpha), "empirical_p": emp_p, "n_band": n_band,
            "band": band_t, "band_width": w_used, "target_s": s_t}


def enrichment_test(results, *, alpha_region: float = 0.05, alpha_test: float = 0.05, conf: float = 0.95) -> dict:
    """The exact binomial ENRICHMENT test across the K positives. `results` = list of size_banded_empirical_p dicts
    (or any {voided, hit}). Excludes voided from K; k = #hits among the non-voided K. binomial_p = P(X >= k | K,
    alpha_region) (the size-matched-background hit rate under H0). PASS iff binomial_p < alpha_test. Clopper-Pearson
    CI on k/K. Pure."""
    live = [r for r in (results or []) if not r.get("voided")]
    n_void = len(results or []) - len(live)
    K = len(live)
    k = sum(1 for r in live if r.get("hit"))
    binom_p = exact_binomial_sf(k, K, alpha_region) if K > 0 else None
    ci_lo, ci_hi = clopper_pearson_ci(k, K, conf=conf) if K > 0 else (None, None)
    return {"K": K, "k": k, "n_void": n_void, "binomial_p": binom_p,
            "ci_lo": ci_lo, "ci_hi": ci_hi, "alpha_region": float(alpha_region),
            "passed": (binom_p is not None and binom_p < float(alpha_test))}
