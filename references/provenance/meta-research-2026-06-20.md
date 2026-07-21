# Provenance — the 2026-06-20 uniqueness meta-research run

*A curated provenance extract for the multi-model research run behind labcoat's uniqueness thesis.
It reproduces the **verifiable skeleton** of the run — what was asked, which models ran, what it cost, and
what the hard-skeptic verification layer found — **without** republishing the raw model prose. The raw
outputs are retained privately (see [What is withheld](#what-is-withheld-and-why)); every figure below is
either computed directly from the run's call ledger or summarized from its verification ledgers.*

This is the object [`references/measured-results.md`](measured-results.md) and the README's uniqueness claims
rest on: it makes the run **inspectable** (you can see the method, the spend, and the fabrication catches)
and, via the SHA-256 manifest, **integrity-bound** to the exact private artifacts — rather than asked to be
taken on faith.

---

## 1. What this run was

On **2026-06-20**, labcoat was pointed at itself: a multi-model meta-research run to resolve the open
positioning/uniqueness questions behind the tool ("what, if anything, is actually rare here?"). It was
decomposed into **7 non-overlapping sub-question streams (S1–S7)** and run through labcoat's own 6-phase
pipeline. The synthesis of these streams is the evidentiary basis for the uniqueness thesis stated in the
README — *that labcoat's rarity is an integrated, productized combination (cross-vendor divergence,
every-proper-noun verify-to-kill, a transparent calibrated saturation gate, hash-bound pre-registration with
honest-negative publishing), not any single conceptually-unprecedented axis.*

## 2. Method (6 phases)

1. **Decompose / scope / redact / cost** — split into S1–S7 at differentiated depth; a redaction pass gates
   every outbound prompt (no client-specific material leaves the machine).
2. **Harvest** — pull relevant prior technical research per stream.
3. **Multi-model fleet divergence** — the same question to a fleet of vendor-diverse models via OpenRouter;
   disagreement is a first-class signal.
4. **Hard-skeptic primary-source verification (verify-to-kill)** — every proper noun (arXiv ID, DOI, repo,
   model slug, license, statistic) is treated as a *claim to disprove* against a primary source before it is
   allowed into the synthesis.
5. **Adversarial validation** — cross-check the verified findings.
6. **Ranked synthesis + capture.**

## 3. Sub-question streams

| ID | Stream (topic) | Depth | Hallucination risk |
|---|---|---|---|
| **S1** | Durable multi-day/-month orchestration feasibility on a Windows + Claude Code stack (external-process vs CC-native vs hybrid vs workflow-tool) | Deep | High |
| **S2** | Best non-xAI "blunt-critic" model + per-model data-governance / ownership / jurisdiction risk profiles | Standard | High |
| **S3** | Model timeout baselines (deep-research et al.) for per-query scope-sizing | Quick–Standard | Medium |
| **S4** | Redaction SOTA — surgical redaction, secret/PII detection (NER/entropy), over-redaction avoidance | Standard | High |
| **S5** | Evolutionary novelty-engine SOTA — idea generation, novelty/fitness scoring, analogical transfer, whitespace detection, autonomous-research-agent systems | Deep | Very high |
| **S6** | Competitive landscape (Elicit / Consensus / Perplexity / FutureHouse-class) — capabilities, gaps, differentiation | Standard | High |
| **S7** | Cross-loop knowledge-graph + memory backend (mem0 / Zep / Graphiti / Qdrant / Neo4j / Postgres / Redis), governance + self-host-vs-SaaS | Deep | High |

The streams that carry the highest hallucination risk (S5 autonomous-research systems; S2 model-ownership
claims; S3 timeout figures) are exactly the ones the verification layer scrutinized hardest — see §6.

## 4. Fleet call ledger (computed from the run)

**33 calls · 7 streams · 8 distinct models · $1.3884 fleet spend · 9,898 in / 126,879 out tokens · 1 failure.**

Per stream:

| Stream | Calls | Models used |
|---|---|---|
| S1 | 4 | gemini-2.5-pro, gpt-5.2, claude-opus-4.8, deepseek-v3.2 |
| S2 | 7 | + qwen3-235b-thinking, mistral-large-2512, kimi-k2-thinking |
| S3 | 2 | gemini-2.5-pro, gpt-5.2 |
| S4 | 4 | gemini-2.5-pro, gpt-5.2, claude-opus-4.8, deepseek-v3.2 |
| S5 | 8 | + qwen3-235b-thinking, kimi-k2-thinking, glm-5.2, mistral-large-2512 |
| S6 | 4 | gemini-2.5-pro, gpt-5.2, claude-opus-4.8, deepseek-v3.2 |
| S7 | 4 | gemini-2.5-pro, gpt-5.2, claude-opus-4.8, deepseek-v3.2 |

Per model:

| Model (OpenRouter slug) | Calls | Fleet cost | in/out tokens | Failures |
|---|---|---|---|---|
| `anthropic/claude-opus-4.8` | 6 | $0.6158 | 2,766 / 24,079 | 0 |
| `google/gemini-2.5-pro` | 7 | $0.3733 | 1,893 / 37,088 | 0 |
| `openai/gpt-5.2` | 7 | $0.3387 | 1,526 / 24,006 | **1** |
| `moonshotai/kimi-k2-thinking` | 2 | $0.0269 | 557 / 10,612 | 0 |
| `z-ai/glm-5.2` | 1 | $0.0167 | 314 / 3,975 | 0 |
| `mistralai/mistral-large-2512` | 2 | $0.0117 | 592 / 7,628 | 0 |
| `deepseek/deepseek-v3.2` | 6 | $0.0046 | 1,685 / 12,758 | 0 |
| `qwen/qwen3-235b-a22b-thinking-2507` | 2 | $0.0007 | 565 / 6,733 | 0 |

The one failure was `openai/gpt-5.2` on S5 (`peer closed connection without sending complete message body —
incomplete chunked read`) — recorded, not silently dropped.

## 5. Deep-research passes (Perplexity Sonar)

S1, S5, and S7 additionally received a Perplexity **`sonar-deep-research`** pass. Metadata only — the response
bodies are retained privately:

| Stream | Status | Elapsed | Response size | SHA-256 (source payload) |
|---|---|---|---|---|
| S1 | COMPLETED | 292 s | 75,405 chars | `85b90643ba365ed4…` |
| S5 | COMPLETED | 355 s | 98,683 chars | `8e15154c3e85029e…` |
| S7 | COMPLETED | 274 s | 86,157 chars | `53a96a446fa9a5ae…` |

## 6. Hard-skeptic verification layer (V1–V9) — the verify-to-kill record

This is the differentiating layer: **nine primary-source verification ledgers** that treated every model-emitted
proper noun as a claim to disprove. Primary sources used across the ledgers: the live OpenRouter `/models`
catalogue, arXiv abstract pages + the arXiv/Crossref APIs, the GitHub API (authenticated) for repos + raw
LICENSE files, PyPI's JSON API, the Hugging Face Hub, the U.S. Federal Register, NIST CSRC, and official
vendor documentation.

| Ledger | Cluster | Representative outcome |
|---|---|---|
| **V1** | Durable-execution framework licenses (Temporal, Inngest, Restate, DBOS, Hatchet, Camunda/Zeebe, Dagster, LangGraph, Prefect, Conductor) | Licenses resolved against raw `LICENSE` files: **Restate = BSL-1.1 not "Apache-style"; Hatchet = MIT not Apache**; a load-bearing "don't use Zeebe for months-long workflows" quote traced to a *stale community post* the vendor walked back. |
| **V2** | Windows + Claude Code headless mechanisms | Confirmed the static-API-key-vs-OAuth split (desktop app is OAuth-exclusive → blocks a headless design); flagged the blanket "no native resumable-workflow primitive" as **misleading** (one now exists — but is not reboot-durable). |
| **V3** | "Best blunt-critic" model slugs + critique benchmarks | Of the fleet-named slugs, **zero were both live and current-gen: ≥6 FABRICATED** (absent from the live catalogue), 5+ superseded. The "Claude = best blunt critic" ranking is **unverified** (SycEval does not crown a Claude model). Real benchmarks confirmed at exact IDs: Sharma `2310.13548`, SycEval `2502.08177`, CriticEval `2402.13764`, FindTheFlaws `2503.22989`. |
| **V4** | Model-vendor governance / ownership | **"China Investment Corp 36.7% Alibaba stake" = FABRICATED** (no such holding in any filing); **"Microsoft 49% stake / de-facto control of OpenAI" = MISLEADING** (49% was a profit-share cap, not equity; post-restructure MSFT ≈ 27%, nonprofit controls the board); **"Zhipu on the BIS Entity List" = CONFIRMED** against the Federal Register primary. |
| **V5** | Provider timeout figures | **Two model-cited doc URLs FABRICATED** (do not resolve); **"OpenRouter 600 s global sync timeout" = FABRICATED** (no such documented cap); a "webhook" async variant FABRICATED. The one high-value survivor: **Google Vertex Gemini's 300 s hard server cap = CONFIRMED**; Perplexity async `POST /v1/async/sonar` (poll-based) = CONFIRMED. |
| **V6** | Redaction / PII / secret-scanning libraries | Licenses resolved against raw files: **Presidio = MIT, TruffleHog = AGPL-3.0** (both model claims of Apache/GPL wrong); one **fabricated HF model ID** (`lakshyagupta/roberta-base-ner-pii`); a "suspected-fake" model (**Piiranha**) verified **REAL** (false suspicion refuted); a paper citation with a **real title but fabricated author** ("Petsko et al.") isolated. |
| **V7a** | Real novelty / AI-scientist papers | All six canonical anchors confirmed at exact IDs — AI Scientist `2408.06292`, Stanford ideation `2409.04109`, MAP-Elites `1504.04909`, Eureka `2310.12931`, PromptBreeder `2309.16797`, MT-Bench `2306.05685`. Two arXiv **ID-collisions** resolved cleanly (ChemCrow `2304.05376` vs Coscientist preprint `2304.05332`; Webb analogy `2212.09196` vs two unrelated real papers). |
| **V7b** | Suspected fabrications (novelty systems) | **Five placeholder-pattern arXiv IDs** (`2403.12345`-style) each resolve to a *real but unrelated* paper — the model attached a fabricated title to a real ID; multiple fabricated "systems" (A-SOB, NoveltyForge, SciNovelty, …) and **three fabricated DOIs (404)** isolated. **And the reverse:** two future-dated 2026 papers the synthesis flagged as "prime fabrication suspects" (`2605.27130`, `2605.11258`) were verified **REAL** — verify-to-kill correcting a *false* fabrication flag. |
| **V8** | Knowledge-graph / memory-backend licenses | Redis tri-license (RSALv2\|SSPLv1\|AGPLv3) confirmed against the raw file → **"RSALv3" = FABRICATED** (no such version); **"Graphiti on Postgres" = FABRICATED** (no Postgres backend exists); FalkorDB = SSPL (a source-available disqualifier, not permissive); Kuzu = MIT but **archived/dead**. |
| **V9** | Competitor products (Elicit, Consensus, Scite, Perplexity, FutureHouse/PaperQA2, Undermind, STORM) | FutureHouse mis-identification ("UK AISI / Inspect") = FABRICATED; PaperQA2 confirmed (`2409.13740`). **The uniqueness claim was itself audited and narrowed:** no competitor was found to do independent primary-source *entity* re-verification as a gating pass — but PaperQA2's retraction-check + contradiction-detection narrows the moat to *the integrated combination*, not any single axis. |

**Aggregate (a conservative floor, enumerated per-ledger above):** across the nine ledgers, **more than two
dozen distinct outright fabrications** — fabricated arXiv IDs, DOIs, model slugs, doc URLs, and whole
"systems" — were isolated against primary sources, plus a comparable number of *misleading / stale /
misattributed* claims (the "real ID, wrong paper/author" trap recurred repeatedly). Two **false** fabrication
suspicions were also overturned (real papers wrongly doubted). This two-directional record — killing confabulations *and* rescuing
wrongly-doubted truths — is the concrete evidence behind the verify-to-kill claim.

## 7. Integrity manifest (SHA-256 of the private source artifacts)

Each artifact of the run is fingerprinted below so this extract is **bound** to the exact bytes it was drawn
from. The raw files are private (§8), so these hashes are an **integrity anchor / commitment**, not
reader-reproducible — if the raw run is ever audited or released, the hashes verify that what is shown here
corresponds to those exact artifacts. Paths are relative to the run's private workspace. *(The four
orchestration scripts are omitted — they carry machine-local paths.)*

| SHA-256 (first 16) | Bytes | Artifact |
|---|---|---|
| `3ed636edaabf7cfe` | 5,841 | `00-decomposition.md` |
| `2bbde63f428497cb` | 5,984 | `_fanout-summary.json` |
| `dc36b737edc2bfac` | 56,413 | `audit/S1-fleet-raw.md` |
| `29722bc7c4ba202b` | 12,499 | `audit/S1-harvest.md` |
| `85b90643ba365ed4` | 76,873 | `audit/S1-perplexity-dr.json` |
| `e13cd48bc09474da` | 75,512 | `audit/S2-fleet-raw.md` |
| `0d8d9abd6d133a5f` | 6,622 | `audit/S2-harvest.md` |
| `efea48b328e0b065` | 10,694 | `audit/S3-fleet-raw.md` |
| `0f0fca847d3a8837` | 8,588 | `audit/S3-harvest.md` |
| `cbc248188fb5a017` | 33,731 | `audit/S4-fleet-raw.md` |
| `dfcd7f9e62d4ba50` | 10,215 | `audit/S4-harvest.md` |
| `d4925c3859db1ce8` | 78,719 | `audit/S5-fleet-raw.md` |
| `da0c5cb9f95a827a` | 7,086 | `audit/S5-harvest.md` |
| `8e15154c3e85029e` | 99,783 | `audit/S5-perplexity-dr.json` |
| `9edf7edd30737489` | 57,747 | `audit/S6-fleet-raw.md` |
| `2eb60bf3fa52a46a` | 7,378 | `audit/S6-harvest.md` |
| `7aac24a1e19fedd9` | 35,748 | `audit/S7-fleet-raw.md` |
| `37023433d7a69806` | 12,539 | `audit/S7-harvest.md` |
| `53a96a446fa9a5ae` | 87,845 | `audit/S7-perplexity-dr.json` |
| `296eab36fdd6ce73` | 33,120 | `research/S1-synthesis.md` |
| `6ae89eb0db97c5c5` | 22,542 | `research/S2-synthesis.md` |
| `57320401c8c1817f` | 16,094 | `research/S3-synthesis.md` |
| `a378f691c4d104fc` | 21,585 | `research/S4-synthesis.md` |
| `f100fc550bc870fb` | 28,373 | `research/S5-synthesis.md` |
| `58e8be5d00fdd663` | 21,815 | `research/S6-synthesis.md` |
| `476e30e91a6c3ef5` | 22,940 | `research/S7-synthesis.md` |
| `72dac194a02baf0b` | 5,521 | `verify/V1-ledger.md` |
| `a1e0e70fc0f509b5` | 7,810 | `verify/V2-ledger.md` |
| `d6f8f06d6dd4ba92` | 6,833 | `verify/V3-ledger.md` |
| `1e993c5e5dcb3dc6` | 9,618 | `verify/V4-ledger.md` |
| `de32c4228622ad84` | 11,981 | `verify/V5-ledger.md` |
| `7e9183ae88a2d738` | 7,683 | `verify/V6-ledger.md` |
| `0cba057891483914` | 6,867 | `verify/V7a-ledger.md` |
| `e7a2db10a4a6f6b6` | 8,982 | `verify/V7b-ledger.md` |
| `be411490d0098218` | 7,341 | `verify/V8-ledger.md` |
| `236a378088032358` | 5,532 | `verify/V9-ledger.md` |

*(36 artifacts fingerprinted; 4 orchestration scripts omitted. Full byte-for-byte hashes are held with the
private workspace.)*

## 8. What is withheld, and why

The **raw fleet outputs, the Perplexity deep-research response bodies, and the per-stream syntheses** are
**not** reproduced here. They are retained in the run's private workspace because:

1. **Copyright.** The deep-research payloads and fleet prose quote source passages; republishing them verbatim
   is not appropriate. This extract carries facts, counts, verified IDs, and verdicts — not the prose.
2. **Redaction safety.** The workspace is a working research environment; it contains machine-local paths and,
   in its Phase-0 scoping notes, references to *excluded* private material (deliberately kept out of the
   research). None of that appears in this extract — but a bulk copy of the workspace would carry it, which is
   exactly why this is a hand-built extract rather than a raw dump.

What **is** here is the publishable skeleton: the questions, the fleet + cost ledger, the deep-research
metadata, the verification outcomes, and an integrity manifest binding it all to the private originals.

## 9. Honest limits

- **This is a provenance skeleton, not the raw research.** It lets you see the method, the spend, and the
  verification record; it does not let you re-run the study.
- **It is a curated extract.** Fidelity rests on the transcription — which is deliberately confined to
  machine-computed figures (the call ledger, hashes) and verdict-level summaries of the ledgers, not
  re-narrated findings.
- **It documents one run** (2026-06-20). Later labcoat passes (e.g. the 2026-07 finish-line review) are
  separate and are not covered here.
- The integrity hashes are a **commitment**, not a reader-side reproduction — the private artifacts are not
  shipped.

---

*Provenance extract generated for finish-line item #1 (raw-run surfacing, Shape B). Governed by the labcoat
honesty stake: ambition is unbounded in the engine; claims are bounded by verification.*
