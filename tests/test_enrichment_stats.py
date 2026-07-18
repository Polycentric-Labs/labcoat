import sys, pathlib, math
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import enrichment_stats as es


# ---------- octave_band ----------
def test_octave_band_floor_log2():
    assert es.octave_band(1.0) == 0
    assert es.octave_band(2.0) == 1
    assert es.octave_band(3.9) == 1
    assert es.octave_band(4.0) == 2
    assert es.octave_band(0.5) == -1


def test_octave_band_nonpositive_is_none():
    assert es.octave_band(0.0) is None
    assert es.octave_band(-1.0) is None
    assert es.octave_band(None) is None


# ---------- exact_binomial_sf (P(X>=k)) ----------
def _bf_binom_sf(k, n, p):
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(max(0, k), n + 1))


def test_binomial_sf_matches_bruteforce():
    for n in (0, 1, 3, 5, 8, 12):
        for p in (0.05, 0.1, 0.3, 0.5, 0.9):
            for k in range(-1, n + 2):
                got = es.exact_binomial_sf(k, n, p)
                exp = 1.0 if k <= 0 else (0.0 if k > n else _bf_binom_sf(k, n, p))
                assert abs(got - exp) < 1e-9, (k, n, p, got, exp)


def test_binomial_sf_known_value():
    # P(X>=2 | n=4, p=0.5) = 1 - 1/16 - 4/16 = 11/16
    assert abs(es.exact_binomial_sf(2, 4, 0.5) - 11 / 16) < 1e-12


def test_binomial_sf_edges():
    assert es.exact_binomial_sf(0, 5, 0.3) == 1.0        # P(X>=0)=1
    assert es.exact_binomial_sf(6, 5, 0.3) == 0.0        # k>n -> 0
    assert es.exact_binomial_sf(1, 5, 0.0) == 0.0        # p=0 -> X=0 a.s.
    assert es.exact_binomial_sf(5, 5, 1.0) == 1.0        # p=1 -> X=n a.s.


# ---------- exact_binomial_cdf (P(X<=k)) ----------
def test_binomial_cdf_matches_bruteforce():
    for n in (1, 4, 7):
        for p in (0.1, 0.5, 0.8):
            for k in range(-1, n + 1):
                got = es.exact_binomial_cdf(k, n, p)
                exp = sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(0, max(0, min(k, n)) + 1)) if k >= 0 else 0.0
                assert abs(got - exp) < 1e-9, (k, n, p, got, exp)


def test_binomial_cdf_complement_of_sf():
    # cdf(k) = 1 - sf(k+1)
    assert abs(es.exact_binomial_cdf(1, 4, 0.5) - (1 - es.exact_binomial_sf(2, 4, 0.5))) < 1e-12


# ---------- clopper_pearson_ci ----------
def test_cp_k_zero_closed_form():
    lo, hi = es.clopper_pearson_ci(0, 10, conf=0.95)
    assert lo == 0.0
    assert abs(hi - (1 - 0.025 ** (1 / 10))) < 1e-6   # upper solves (1-p)^n = alpha/2


def test_cp_k_equals_n_closed_form():
    lo, hi = es.clopper_pearson_ci(10, 10, conf=0.95)
    assert abs(lo - 0.025 ** (1 / 10)) < 1e-6          # lower solves p^n = alpha/2
    assert hi == 1.0


def test_cp_bounds_bracket_point_estimate_and_satisfy_tail_equations():
    for k, n in ((1, 5), (2, 5), (3, 10), (7, 20)):
        lo, hi = es.clopper_pearson_ci(k, n, conf=0.95)
        assert 0.0 <= lo <= k / n <= hi <= 1.0
        # Clopper-Pearson defining equations: sf(k,n,lo)=a/2 and cdf(k,n,hi)=a/2
        assert abs(es.exact_binomial_sf(k, n, lo) - 0.025) < 1e-6
        assert abs(es.exact_binomial_cdf(k, n, hi) - 0.025) < 1e-6


def test_cp_symmetric_case():
    lo, hi = es.clopper_pearson_ci(5, 10, conf=0.95)
    assert abs((lo + hi) - 1.0) < 1e-6                 # symmetric around 0.5


# ---------- size_banded_empirical_p ----------
def test_empirical_p_target_most_extreme_is_a_hit():
    # all gaps share (da,dc)=(50,50) -> same band; higher c_ac => more extreme (smaller hypergeom sf).
    nc = 1000
    target = (20, 50, 50)                              # far above expected 2.5 -> extreme
    background = [(c, 50, 50) for c in range(1, 20)]   # 19 less-extreme gaps
    r = es.size_banded_empirical_p(target, background, nc, alpha=0.05, min_band=5)
    assert r["voided"] is False
    assert r["n_band"] == 19
    assert abs(r["empirical_p"] - 1 / 20) < 1e-12      # (0+1)/(19+1)
    assert r["hit"] is True


def test_empirical_p_target_least_extreme_not_a_hit():
    nc = 1000
    target = (1, 50, 50)                               # least extreme
    background = [(c, 50, 50) for c in range(2, 21)]   # 19 more-extreme gaps
    r = es.size_banded_empirical_p(target, background, nc, alpha=0.05, min_band=5)
    assert abs(r["empirical_p"] - 20 / 20) < 1e-12     # (19+1)/(19+1)
    assert r["hit"] is False


def test_empirical_p_voids_when_band_underpowered():
    nc = 1000
    target = (10, 50, 50)
    background = [(c, 50, 50) for c in range(1, 6)]     # only 5 in-band gaps
    r = es.size_banded_empirical_p(target, background, nc, alpha=0.05, min_band=50, widen_octaves=2)
    assert r["voided"] is True
    assert r["hit"] is False


def test_empirical_p_widens_band_to_reach_min():
    # target band (da=dc=50 -> E=2.5 -> band 1) has too few; neighbours in band 0/2 fill the quota.
    nc = 1000
    target = (20, 50, 50)                               # band 1
    band1 = [(c, 50, 50) for c in range(1, 4)]          # 3 band-1 gaps
    band0 = [(2, 30, 30) for _ in range(4)]             # E=0.9 -> band -1..0 ; da*dc=900 -> E=0.9 -> band -1
    band2 = [(2, 80, 80) for _ in range(4)]             # E=6.4 -> band 2
    r = es.size_banded_empirical_p(target, band1 + band0 + band2, nc, alpha=0.5, min_band=8, widen_octaves=2)
    assert r["voided"] is False
    assert r["band_width"] >= 1                         # had to widen beyond the exact band
    assert r["n_band"] >= 8


# ---------- enrichment_test (the exact binomial across positives) ----------
def test_enrichment_test_all_hits_passes():
    results = [{"voided": False, "hit": True} for _ in range(3)]
    out = es.enrichment_test(results, alpha_region=0.05, alpha_test=0.05)
    assert out["K"] == 3 and out["k"] == 3 and out["n_void"] == 0
    assert abs(out["binomial_p"] - 0.05 ** 3) < 1e-12   # P(X>=3 | 3, 0.05)
    assert out["passed"] is True


def test_enrichment_test_excludes_voided_from_K():
    results = [{"voided": False, "hit": True}, {"voided": True, "hit": False}, {"voided": False, "hit": False}]
    out = es.enrichment_test(results, alpha_region=0.05, alpha_test=0.05)
    assert out["K"] == 2 and out["k"] == 1 and out["n_void"] == 1


def test_enrichment_test_one_hit_of_three_is_not_significant():
    results = [{"voided": False, "hit": True}] + [{"voided": False, "hit": False} for _ in range(2)]
    out = es.enrichment_test(results, alpha_region=0.05, alpha_test=0.05)
    # P(X>=1 | 3, 0.05) = 1 - 0.95^3 ~ 0.1426 > 0.05
    assert abs(out["binomial_p"] - (1 - 0.95 ** 3)) < 1e-12
    assert out["passed"] is False
    assert 0.0 <= out["ci_lo"] <= out["k"] / out["K"] <= out["ci_hi"] <= 1.0
