# N2-live runbook (operator) — gap/whitespace channels

N2-live runs the multi-channel gap detector over a real arXiv corpus. The default path is **FREE** (local stdlib
extraction + FREE PPMI-context relatedness + free arXiv; NO OpenRouter / NO Console spend); the `--llm`
quality path is **opt-in** (a few cents — the research-validated LLM-tagged extractor, below). N2 is ADVISORY.

## Prereqs
- Python 3.11+. **That is all** — the free path is pure stdlib + the free arXiv fetcher.
- **No ML extras.** `requirements-n1.txt` (torch/faiss, ~2GB) is **NOT** needed here and installing it changes
  nothing about this pipeline. `gaps_live.py` does not import the N1 embedder at all: ABC relatedness comes from
  `gap_channels.pmi_context_relatedness` (PPMI-context, Church-Hanks) — SPECTER2 was **dropped for concept-concept
  relatedness** (it returned a useless ~uniform 0.86-0.95 on short terms). SPECTER2 stays for N1 paper-to-paper
  novelty only. The output's `n1_used` field is therefore always `False` **by design**, not a degraded mode.
- `OPENROUTER_API_KEY` in the environment — **only** for the opt-in `--llm` path (see below). The free path needs
  no credential.

## Run (free)
    $env:PYTHONIOENCODING='utf-8'
    python scripts/gaps_live.py gaps --query "cat:cs.LG" --n 200

Expect: `docs`/`concept_edges`, then the structural-gap line comparing **PPMI-filtered vs unfiltered** — printed as
`structural_gaps: <n> (PPMI-filtered, min_rel=..., hub_thr=...) vs <n> (unfiltered)` (the PPMI relatedness filter
+ hub-degree bridge exclusion drop spurious absent edges) — plus `future_work`/`contradictions` counts, the
`by_status` evidentiary-tag histogram (whitespace / known-but-unaddressed / speculative / contradiction), and the
top next-question candidates.

## Run (`--llm` — the quality path; opt-in, ~$0.01–0.10)
    $env:PYTHONIOENCODING='utf-8'
    python scripts/gaps_live.py gaps --llm --query "cat:cs.LG" --n 50 [--min-relatedness 0.3]

Replaces the noisy stdlib extractor with LLM-tagged per-doc extraction (strict-JSON concepts + claim records
`{subject, polarity, value, context}`), behind the SAME pure channels. Opt-in (estimate-first; the key comes from
`OPENROUTER_API_KEY` in the env, or optionally a `$LABCOAT_SECRETS_DIR/openrouter.env` file (default
`~/.secrets/openrouter.env` — one author's local layout, not a requirement); loaded in-process, never printed,
source path announced; cheap model; bounded by `--n`). **Research-validated** (a
labcoat-on-itself pass; Peng et al. PMC6481912 verified): three tweaks ship — (A) the claim record carries `context`
and `find_contradictions` requires same subject+context so CONDITIONAL findings ("improves in vitro" vs "reduces in
vivo") are NOT flagged as contradictions; (B) `--min-relatedness` is the ABC precision lever (22-27%→71-98% with
fusion); (D) a span-verification guard drops any extracted term absent (verbatim) from the source (anti-hallucination).

HONEST FINDINGS (live smoke, n=12): `--llm` eliminates the stdlib concept noise ("After"/"All"/"Ms" garbage gone) and
**activates the contradiction channel** (2 contradictions vs 0 for stdlib). But clean concepts over a few DIVERSE
papers share few cross-document ABC bridges → ~0 structural gaps (stdlib's common-word noise manufactured 216 spurious
ones). Real ABC structural-gap yield needs a DENSER / focused corpus — characterize before relying on it. Contradiction
candidates are ADVISORY (a context-collision false-positive is possible when the LLM returns empty `context`).

HONEST LIMITS: the default stdlib extractor is CRUDE (Title-case/acronym; misses lowercase; noisy) — `--llm` is the
fix. Concept-concept relatedness uses PPMI-context, **not** SPECTER2: SPECTER2's short-input degradation (~uniform
0.86-0.95 on short terms) made it inert as a filter, so it was dropped here; the PPMI + hub-exclusion replacement
removed ~99.85% of the ABC noise flood. That is a win for the *machinery* — it does **not** make ABC a discovery
detector: the cross-literature headline result is a **kept negative** (the count/co-occurrence ABC channel cannot
discriminate a documented cross-literature discovery from big-literature spurious pairs; the confound is literature
*size*, and neither IDF-specificity nor size-normalization rescued it — see
[`n2-crosslit-prereg.md`](n2-crosslit-prereg.md) and [`n2-crosslit-optionC-prereg.md`](n2-crosslit-optionC-prereg.md)
for the frozen pre-registrations and their pre-committed KILL/VOID/PASS semantics). A **semantic substrate**
(MeSH/UMLS semantic-type prefilter, SemMedDB, or LLM-relevance) is the known deferred next step. N2 emits scored
HYPOTHESES, not validated gaps (the loop is the prospective validation). N2 stays ADVISORY.
