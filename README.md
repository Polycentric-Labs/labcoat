# Polycentric Labcoat

> The rigorous net-new research-investigation engine. Fan a question across a live multi-model fleet, then **kill** every finding that can't be traced to a primary source, validate the survivors three ways, and return a ruthlessly ranked synthesis. Built to be wrong-proof, not fast.

A [Claude Code](https://code.claude.com) skill (Agent Skills standard) backed by a standalone, provider-agnostic Python multi-model fleet runner, a fail-closed redaction gate, and a novelty source-log.

**Repo** `Polycentric-Labs/labcoat` · **skill name** `polycentric-labcoat` — invoke `/polycentric-labcoat`; to install, junction this repo into `~/.claude/skills/polycentric-labcoat`.

## Why it exists

Opinion models hallucinate proper nouns. In the run that produced this skill, an 8-model fleet fabricated ~9 CVE IDs and ~6 academic citations — including a *real* arXiv ID paired with a *hallucinated* title — and per-item web-grounding caught every one. On its first real investigation it also caught the opposite failure: all four models in the fleet *unanimously denied* a real standard existed. A research method that trusts model output for a CVE number, a repo name, a version string, or a citation will confidently ship fiction.

So labcoat treats every fleet-produced proper noun (CVE/advisory ID, arXiv ID, repo, version, citation, tool name, statistic) as a **claim to disprove**, not a fact to relay. The fleet is an idea generator; only a primary-source check produces a fact.

## The 6-phase pipeline

Every phase ends at a **stop-and-ask gate** — no phase auto-advances past a material decision.

0. **Scope + redact + cost** — decompose the question, challenge the premise, pull prior research, run the redaction gate on every outbound prompt, pick a depth tier and show the cost estimate.
1. **Harvest** — parallel agents answer non-overlapping sub-questions, writing to disk as they go.
2. **Multi-model divergence** — route each query, then fan it across a live, multi-vendor fleet (Gemini + GPT + Grok + DeepSeek as a floor). Disagreement is signal.
3. **Hard-skeptic web-grounded verification** — the spine. Try to *kill* each finding; web-confirm every proper noun against a primary source (`gh` for repos, arXiv/Semantic Scholar for papers, NVD/vendor for CVEs, fetch/Playwright for pages). Quarantine the unconfirmed.
4. **3× adversarial validation** — three distinct lenses: fidelity, soundness, completeness.
5. **Rank + synthesize** — a ruthless ranking with per-item evidence and an honest skip/kill list.
6. **Capture** — record high-signal sources, hand the synthesis off for cadence-based refresh.

## The autonomous engine (Nuclear)

Beyond the interactive pipeline, `scripts/nuclear.py` runs the same method **unattended in a multi-loop cycle** with an external brain and machine gates (spend tolerance, pacing, a saturation gate), reboot-survivable via an append-only ledger. What is live vs. advisory, stated honestly:

> Every number below is traced in **[`references/measured-results.md`](references/measured-results.md)** — scope, the harness that produced it, the command to reproduce it, the honest limit, and a plain statement of which numbers you currently have to take on trust from a clone (two of them do).

- **Loop-evolution (live).** Each loop after the first re-decomposes from the prior loop's surfaced gaps and contradictions (contradictions first) — the engine *chases* the next question instead of re-asking the same one.
- **Calibrated saturation gate (live, enforcing).** A control-chart signal (Confirmed-Novelty Yield + an SPC yield-collapse rule, computed only over *confirmed* findings) detects when a run has saturated and **pauses-and-pings the operator — it never auto-stops** (corrigible). Calibrated to `tau=0.30 / floor=0 / window=3` on three diverse multi-loop curves (sharp / steady-productive / bursty); `--novelty-enforcing` is on by default. **The three curves ship** as `tests/fixtures/novelty-gate-calibration-curves.json` and `python -m pytest tests/test_novelty_gate.py -q` re-derives the calibration offline — this is the one gate that *enforces*, so it is the one you can check yourself in a second. Honest caveat carried in the fixture: `floor`/`window` are derived from those curves, but **`tau` is under-determined** by them (the curves are tau-invariant — the seen-set dedup dominates), so 0.30 is held over from the prior default.
- **N1 literature-grounded novelty (live, advisory).** RND-style relative-neighbor-density scored against a real external corpus — the adapter is wired and runs live over a SPECTER2 + faiss index (arXiv + an OpenAlex ~25k-work corpus). Its out-of-distribution gate is *measured*: **held-out-field AUROC 0.889 [0.874, 0.904]**. Read honestly, that gate is an **anti-out-of-corpus detector, not a general novelty oracle** — it says a claim is far from *this corpus*, not that it is new to the world, and it is field-dependent.
- **N3 combinatorial / analogical synthesis (live, advisory).** A MAP-Elites archive + multiplicative novelty×utility + a proposer≠judge separation, running the full live loop: propose → N1-novelty → judge → ground. A measured comparison **confirmed the engine beats raw prompting on prior-art distance — for DISTANT domain pairs only** (CMH p=7.4e-5, cluster-bootstrap CI [0.104, 0.320]); near pairs show no such win. The **soundness axis is human-gated**: an LLM judge could not be validated past ~0.70 on hard negatives — it catches clear named-law violators but cannot separate a subtly incoherent cross-domain mapping from genuine novelty. Verified-non-obvious needs a human expert.
- **N2 gap / whitespace channels (live, advisory — with an honest negative).** Swanson-ABC + future-work + contradiction → reconciliation, wired and running live. The headline result is a **negative we kept**: the count/co-occurrence ABC channel **cannot discriminate a documented cross-literature discovery from big-literature spurious pairs** — the confound is literature *size*, and neither IDF-specificity nor size-normalization rescued it. A PPMI + hub-exclusion fix did remove **~99.85% of the noise flood** (a real win for the machinery), but the channel is not a discovery detector on raw co-occurrence. A **semantic substrate** (MeSH/UMLS semantic-type prefilter, SemMedDB, or LLM-relevance) is the known deferred next step.
- **Value axis (advisory).** A quality dimension that stays advisory by design — a value-aware novelty metric is a genuinely-unsolved Goodhart problem, so it is reported, never consumed by the loop's decision.

Operator: `nuclear.py estimate` (free — no paid call; still needs `OPENROUTER_API_KEY` for the catalogue probe) then `run --tolerance <usd>` (paid, bounded by tolerance + an explicit burn gate). Requires `claude-agent-sdk`.

## Components

| Path | Role |
|---|---|
| `SKILL.md` | The 6-phase orchestration, the gates, the anti-hallucination rules |
| `scripts/fleet.py` | Standalone parallel multi-model fleet runner with reasoning-model-safe defaults (no secrets in code) |
| `scripts/redaction_gate.py` | Fail-closed sensitive-data gate for outbound prompts (findings carry offsets, never the secret) |
| `scripts/novelty_log.py` | Persistent high-signal source-domain log |
| `scripts/route_integration.py` | Wrapper over a query-routing classifier with a safe-default degrade; optionally calls the [`sonar-router`](https://github.com/Polycentric-Labs/sonar-router) companion — degrades gracefully if absent |
| `scripts/nuclear.py` | The autonomous multi-loop engine (operator entrypoint; estimate-first, tolerance-gated) |
| `scripts/{n1_*,combinatorial,combine_live,stage_*}.py` | The N1 novelty + N3 synthesis cores and their live adapters |
| `scripts/{gap_channels,gaps_live,n2_*,pubmed_adapter}.py` | The N2 gap/whitespace cores + live adapters |
| `scripts/{roc,spc,enrichment_stats}.py` | Pure measurement/statistics cores (stdlib only — never scipy) |
| `references/anti-hallucination.md` | The R-1..R-5 rules + the case study |
| `references/measured-results.md` | **Provenance for every number on this page** — scope, harness, repro command, honest limit, and what is *not* verifiable from a clone |
| `references/n2-crosslit-prereg.md`, `references/n2-crosslit-optionC-prereg.md` | **The frozen pre-registrations** — knobs locked *before* each run, with pre-committed PASS/VOID/KILL semantics and an anti-rescue rule. The runs returned KILL and INCONCLUSIVE; both were published as such |
| `references/{n1-live,n1-openalex,n1-offdist-roc,n2-live,n3-live,spc-detector}-runbook.md` | Operator runbooks — the runnable commands behind each live/measured claim |
| `references/research-skill-router.md` | Which of the three research skills to use (they compose; they don't overlap) |
| `references/output-templates/` | Standardized doc shapes for each phase |
| `tests/` | `python -m pytest tests/ -q` — **577 tests** over the pure cores |

47 scripts in all; `SKILL.md` carries the full grouped inventory with a one-line role each, and its §"Cross-references" annotates every doc under `references/`.

## Use

**As a Claude Code skill:** place the folder under your skills directory (e.g. symlink/junction it to `~/.claude/skills/polycentric-labcoat`) and invoke `/polycentric-labcoat` or ask for "rigorous research" / "investigate X with the fleet."

**The fleet runner standalone:**
```bash
pip install -r requirements.txt -r requirements-dev.txt   # CORE (httpx + claude-agent-sdk) + test deps
export OPENROUTER_API_KEY=...           # env only — never hardcode, never log
python -m pytest tests/ -q              # 577 tests — no ML extras needed
```

`OPENROUTER_API_KEY` in the environment is the **only** credential path labcoat requires. As an optional
convenience the operator scripts will also read a `OPENROUTER_API_KEY=...` line from
`$LABCOAT_SECRETS_DIR/openrouter.env` (default `~/.secrets/openrouter.env` — one author's local convention, not
a requirement); when they do, they print the **path** they loaded it from (never the value), so a credential is
never picked up implicitly. With neither present you get an actionable "set `OPENROUTER_API_KEY`" message.

**Three dependency tiers:**

| File | Holds | Needed for |
|---|---|---|
| `requirements.txt` | **core** — `httpx` + `claude-agent-sdk` | the fleet runner, the 6-phase pipeline, the Nuclear engine |
| `requirements-dev.txt` | **test deps** — `pytest`, `pytest-asyncio` | running the test suite (`pytest-asyncio` is required — two tests are `async`) |
| `requirements-n1.txt` | **optional live-N1 extras** — `numpy`, `faiss-cpu`, `torch`, `transformers`, `adapters` | only the live N1 adapter (`n1_embedder.py` / `n1_index.py` / `smoke_n1_live.py`) |

The heavy ML deps are **optional and import-guarded**: the pure N1 core (`n1_novelty.py`) and every other script run without them. **On the core install + dev deps (`requirements.txt` + `requirements-dev.txt`, no ML extras) the suite passes clean — 570 passed, 7 skipped, zero failures** (the skips are the live-adapter tests, guarded to skip rather than fail when faiss/torch are absent; adding `requirements-n1.txt` un-skips 5 of them → 575 passed, 2 skipped). Nothing in `requirements-n1.txt` is needed to import, test, or run labcoat's default paths; install the extras only when you want the live SPECTER2 + faiss literature index. (`faiss-cpu` ships Windows wheels for CPython 3.11/3.12, so no conda/build step; if a wheel is ever unavailable, the zero-dep `InMemoryN1Index` path still works.)

> **Nuclear engine (`scripts/nuclear.py`) additionally requires** `claude-agent-sdk` (already in `requirements.txt`) and the `claude` CLI on PATH.
`fleet.run_fleet(...)` fans a prompt across models in parallel and returns one structured result per model; the API key never appears in any result. See `SKILL.md` for the call shapes.

The fleet runs against the OpenRouter API via `fleet.py`. *Optional:* you can instead drive it interactively through the third-party [`openrouter-multimodal`](https://github.com/stabgan/openrouter-mcp-multimodal) MCP — it's not required and bundles none of labcoat.

## Companion projects

- [`sonar-router`](https://github.com/Polycentric-Labs/sonar-router) — optional query-routing companion. `route_integration.py` wraps its classifier; if sonar-router is absent the wrapper degrades gracefully to a safe default.

## Anti-hallucination (the spine)

- **R-1** — never trust an opinion-model proper noun until web-confirmed (even at full fleet consensus).
- **R-2** — primary-source check for every "X exists / is novel / says Y."
- **R-3** — a dedicated fabrication-purge pass; expect fabrication.
- **R-4** — hard-skeptic posture: try to kill each finding, not confirm it.
- **R-5** — whatever renders the truth (fetch, then a headless browser for JS-heavy pages).

Tripwire: a proper noun that no verification record confirms is blocked from the synthesis. Full detail in [`references/anti-hallucination.md`](references/anti-hallucination.md).

**The rules apply to labcoat's own results.** The N2 cross-literature work was **pre-registered** — every knob locked *before* the run, with PASS/VOID/KILL semantics committed in advance and an explicit anti-rescue rule ("no config-relaxation run can upgrade the mission verdict"). The run came back **KILL**. It is published as a KILL, above, and the pre-registration is in the repo: [`references/n2-crosslit-prereg.md`](references/n2-crosslit-prereg.md). The follow-up [`references/n2-crosslit-optionC-prereg.md`](references/n2-crosslit-optionC-prereg.md) returned **INCONCLUSIVE (underpowered)** by its own pre-committed decision rule, and that is what is reported — not the one positive case it contained.

## License

MIT — see [LICENSE](LICENSE).

## AI assistance

This project was developed alongside AI platforms.

Models used: Claude Opus 4.6, Claude Opus 4.7, Sonar Deep Research
