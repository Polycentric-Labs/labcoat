# N3-live runbook (operator) — combinatorial generate-judge-ground

N3-live reuses the live N1 adapter (build its snapshot first) + the OpenRouter fleet. N3 is ADVISORY.

## Prereqs
- Python 3.11+ (`combine_live.py` uses `asyncio.run`/`asyncio.gather`).
- `pip install -r requirements-n1.txt` (the live N1 adapter).
- An N1 snapshot: `$env:PYTHONIOENCODING='utf-8'; python scripts/smoke_n1_live.py build --query "cat:cs.LG" --n 1500`
- `OPENROUTER_API_KEY` in the environment — `export OPENROUTER_API_KEY=...` (PowerShell: `$env:OPENROUTER_API_KEY='...'`).
  *Optional convenience:* a `OPENROUTER_API_KEY=...` line in `$LABCOAT_SECRETS_DIR/openrouter.env` (default
  `~/.secrets/openrouter.env` — one author's local layout, **not** a requirement). Either way the key is loaded
  in-process and never printed; the load announces the source path only. Spends OpenRouter, never the Console.

## Estimate (free)
    python scripts/combine_live.py estimate --pairs "immunology:distributed-systems" "cryptography:ecology"

## Run (a few cents; tolerance is the hard ceiling)
    $env:PYTHONIOENCODING='utf-8'
    python scripts/combine_live.py run --pairs "immunology:distributed-systems" --tolerance 0.50

Expect: the proposer/judge pools, the proposed-combination count, an `off_distribution=N/M` line (cross-domain
claims are often out-of-corpus vs a narrow cs.LG index — honest; real N3 needs N1 scale-out), then the
ARCHIVE REPORT: `coverage`, `qd_score` (UPPER BOUND, never "discoveries"), `n_elites`, `post_grounding_survival_rate`
(the only 'real' signal — the web-grounded survivors), and `spent`.

## Status of the N3 claim (updated after the Stage-B measurement)

This runbook originally said the integrated stack was "net-new + UNMEASURED". **That is superseded.** The
Stage-B measurement (`scripts/stage_b.py` + `scripts/stage_b_measure.py`; see
[`n1-offdist-roc-runbook.md`](n1-offdist-roc-runbook.md) for the sibling harness pattern) has since measured the
**prior-art-distance axis**:

- **CONFIRMED, for DISTANT domain pairs only** — the engine beats raw prompting on prior-art distance
  (+0.209; CMH p=7.4e-5; cluster-bootstrap CI [0.104, 0.320]; ICC=0). **Near pairs show no such win** — the
  effect is scoped to distant pairs, and an earlier "raw-strong dominates" read was overturned as a tier artifact.
- **The soundness axis remains HUMAN-GATED and UNMEASURED.** An LLM judge could not be validated past ~0.70 on
  hard negatives — it catches clear named-law violators but cannot separate a subtly incoherent cross-domain
  mapping from genuine novelty. *Verified-non-obvious needs a human expert.*
- So: **distance = measured (distant-only). Soundness/utility = not.** N3 stays **ADVISORY** overall.

HONEST LIMITS (this slice's own output): qd_score = upper bound on diversity+surface-plausibility, never
"discoveries"; only post-grounding survival is real; `combine_live.py` runs operator-supplied pairs (not the
structured cross-product); structural descriptor (coverage = lower bound). The Stage-B CONFIRM above is a result
about the *distance axis*, not a warrant that any given `combine_live` run's elites are sound or useful.
