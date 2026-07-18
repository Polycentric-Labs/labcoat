# N1-live runbook (operator)

The live N1 adapter (SPECTER2 + faiss) is OPTIONAL. The pure core + the rest of labcoat run without it.
**Status: LIVE-VALIDATED 2026-06-24** (Python 3.14, faiss-cpu 1.14.3, transformers 4.57.6, adapters 1.3.0) — see
"Expect" below.

## One-time install (Python 3.11+; isolated venv recommended)
    python -m venv .venv ; .venv\Scripts\Activate.ps1      # or just `pip install --user -r ...` (works too)
    pip install -r requirements.txt
    pip install -r requirements-n1.txt   # ~2GB: torch + transformers + adapters + faiss-cpu + numpy
(If `py -3.12` reports "No suitable Python runtime", use whatever 3.11+ you have, e.g. `py -3.14` or plain `python`.)

## Build a small arXiv index (downloads SPECTER2 ~440MB on first run)
    $env:PYTHONIOENCODING='utf-8'
    python scripts/smoke_n1_live.py build --query "cat:cs.LG" --n 1500

## Query novelty vs the literature
    python scripts/smoke_n1_live.py query --claim "A relative neighbor density metric scores idea novelty."

Expect: an N1 novelty score, the cited nearest arXiv prior work, off_distribution status, the Seam-1
embedding-vs-Jaccard separation (embedding separates paraphrase ~0.07 from unrelated ~0.22 where Jaccard reports
1.0/1.0), and an `ORACLE ... -> OK` line confirming the faiss index agrees with the pure InMemory index.

Benign notice: the `adapters` library prints `There are adapters available but none are activated for the forward
pass.` once at model-load time. It is harmless — each `embed()` activates the role-correct adapter (proximity for
corpus, adhoc_query for the claim); query vs document roles produce distinct, adapter-applied vectors (verified).

Snapshot + corpus cache write under `_internal/` (gitignored, private). HF weights cache under ~/.cache/huggingface.
N1 is ADVISORY; the adapter choice + bake-off are A/B-gated (no published benchmark for short novelty claims yet).
`tau` stays uncalibrated until a dedicated live-distance calibration run.

## off_distribution gate — query-calibrated (2026-06-25)
The build now stores TWO thresholds in the snapshot: `off_distribution_threshold` (the GATE — the 95th percentile of
{corpus TITLE embedded with the QUERY adapter -> nearest OTHER corpus doc} distances) and `corpus_loo_threshold`
(diagnostic only — the old paper->paper LOO percentile). The gate is calibrated on the QUERY distribution because a
short claim embedded with the adhoc_query adapter sits much farther from any paper (~0.2+) than two full papers sit
from each other (~0.07); calibrating on paper->paper made the gate fire for EVERY query. The build prints both
(`corpus_loo_threshold=… query_calibrated_gate_threshold=…`).

`off_distribution` is an **anti-garbage / out-of-corpus guard, NOT a novelty signal** — a low count means the claims
are coherent / in-corpus, not that they are proven novel (novelty is the separate RND `score`). It is
**meaningful-not-strong**: SPECTER2 separates 1–2-sentence claims weakly, so the in-vs-out margin is thin (a
claim-tuned embedder / claim+context representation is the future lever). Calibration ignores dates (embedding
regime, not temporal); the query-time date-cutoff still applies.
