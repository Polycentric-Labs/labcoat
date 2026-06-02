---
name: polycentric-labcoat
description: The rigorous NET-NEW research-investigation engine. Use when a question demands deep, multi-model, hard-skeptic, web-grounded investigation rather than a quick lookup — e.g. "investigate X with the fleet", "rigorous research on Y", "fan this out across models", "hard-skeptic research", "net-new investigation", "is this novel / does this already exist", or /polycentric-labcoat. Runs a 6-phase pipeline (scope+redact+cost → harvest → multi-model OpenRouter divergence → hard-skeptic primary-source verification → 3× adversarial validation → ranked synthesis → capture) with a STOP-AND-ASK user gate at every phase, and web-confirms EVERY proper noun (CVE/advisory ID, arXiv ID, repo, version, citation, tool name, stat) before it reaches the user as fact. NOT for refreshing an existing synthesis doc on a cadence (that is research-resync, which this FEEDS) and NOT for a single-shot cited report (that is deep-research). Triggers also on "multi-model research", "polycentric", "investigate with Gemini + GPT + Grok + DeepSeek".
license: MIT
---

# /polycentric-labcoat — The rigorous net-new research engine

A 6-phase investigation methodology that fans a question across a live multi-model fleet, then **kills** every finding it can't trace to a primary source, validates the survivors three ways, and hands back a ruthlessly ranked synthesis. It asks you at every gate. It web-grounds every proper noun. It is built to be wrong-proof, not fast.

This skill codifies the method that worked in the 2026-06-01 VM-Deployer + Opportunity-Audit research passes: **harvest → multi-model divergence → hard-skeptic web-grounded verification → 3× adversarial validation → ruthless ranking → standardized synthesis**, writing as you go and asking the user at every gate.

## Why this exists (and why it is NOT redundant)

Opinion models hallucinate proper nouns. In the session that produced this skill, an 8-model fleet fabricated **~9 CVE IDs and ~6 academic citations** — including a *real* arXiv ID paired with a *hallucinated* title. Per-item web-grounding caught every single one. A research method that trusts model output for a CVE number, a repo name, a version string, or a citation will confidently ship fiction. This skill's entire reason to exist is the **anti-hallucination spine** (Phase 3 + `references/anti-hallucination.md`): treat every fleet-produced proper noun as a *claim to disprove*, not a fact to relay.

It occupies a niche the other research skills do not:

| Skill | Job | Shape |
|---|---|---|
| **deep-research** (builtin) | A one-shot, cited report on a topic | Single fan-out → synthesize → done |
| **research-resync** (×5 variants) | MAINTAIN an existing synthesis doc on a cadence; detect decay | Re-run prior streams → semantic-diff → score materiality |
| **polycentric-labcoat** (this) | A NET-NEW, multi-round, multi-model, hard-skeptic, 3×-validated investigation | 6 gated phases; verify-to-kill; ranked output |

**It feeds research-resync.** A labcoat synthesis doc (Phase 5 output) becomes a *stream* that research-resync can re-run on a cadence later. labcoat does the rigorous first pass; research-resync keeps it fresh. They compose; they do not overlap. **Phase 0 includes its own redundancy check** — if a doc already exists that research-resync should refresh instead, labcoat says so and stops.

→ **Quick routing:** net-new rigorous investigation → this skill; keeping an existing doc fresh on a cadence → a research-resync-style tool; a one-shot cited report → `deep-research`; a single fact → `gh api`/`perplexity_ask` (see the [`sonar-router` companion](https://github.com/Polycentric-Labs/sonar-router) for the full decision matrix).

## When to invoke

- A net-new question that materially affects a decision and is worth getting *right*: "is this technique novel?", "does this tool/repo/paper actually exist?", "what's the real state of the art in X?", "should we build/publish/spin-off Y?"
- Anything where a wrong proper noun (a fabricated CVE, a non-existent repo, a misattributed paper) would be costly or embarrassing.
- When you want genuine model *divergence* — Gemini, GPT, Grok, and DeepSeek disagreeing is signal — not a single model's confident monologue.
- When the user says "investigate with the fleet", "rigorous/deep research", "hard-skeptic research", "fan this out across models", or invokes `/polycentric-labcoat`.

### When NOT to invoke

- **Refreshing an existing synthesis doc** on a schedule → use **research-resync** (this skill feeds it; it does not replace it).
- **A single one-shot cited report** where multi-round skeptic validation is overkill → use **deep-research**.
- **A single fact you can verify in one call** ("does repo `foo/bar` exist?", "what's its star count?") → just use `gh api` or `perplexity_ask`. Consult **sonar-router** for the right tool. Spinning up the full pipeline for one fact is waste; the Quick tier (below) exists for the in-between.

## The 6-phase pipeline

The pipeline is the core of the skill. **Every phase ends at a STOP-AND-ASK gate — no phase auto-advances past a material decision.** You propose; the user confirms, redirects, or kills. Write findings to disk *as you go* (Phase 4 §"Standardization & write-as-you-go"), so a session interruption never loses work.

### Phase 0 — SCOPE + REDACT + COST  →  *gate: user approves scope, depth, redaction, and cost*

The most important phase. Do not skip it.

1. **Decompose** the question into non-overlapping sub-questions. → template `references/output-templates/decomposition.md`.
2. **Critical-framing pushback.** Challenge the premise *before* spending a dollar. Is this actually two separate investigations? Has it already been done (does a doc exist to refresh via research-resync instead)? Is the framing leading? Is the real question underneath the asked question? Say so plainly.
3. **Pull relevant PAST research** cross-project (memory, prior pass-notes, sibling-repo docs) so you don't re-investigate what's already known. Cite what you found.
4. **Redaction gate (interactive + programmatic).** Decide what must NOT leave the machine in any outbound prompt. *Ask the user explicitly* what to redact (client names, internal paths, anything sensitive), then 3×-verify the assembled prompt is clean. The programmatic gate (`redaction_gate.assert_clean`) is necessary-not-sufficient — run it on every outbound prompt *and* do the human pass. See §"The redaction gate".
5. **Pick a depth tier + show the cost estimate.** Recommend a tier from the scope dial (below), show the dollar estimate, and get explicit confirmation. Exhaustive requires a literal "yes, burn it".

**Gate:** user signs off on scope, decomposition, depth tier, redaction list, and cost. Nothing fans out until they do.

### Phase 1 — HARVEST  →  *gate: user reviews the harvest before the fleet runs*

Gather internal context + answer the decomposed sub-questions with parallel agents. **Each agent owns one non-overlapping sub-question and writes its own file** to `<project>/<TopicName>/_internal/audit/` (write-as-you-go). → template `references/output-templates/research-stream.md`. This is local/cheap grounding *before* you spend on the fleet: existing docs, repo reads, prior art you already have access to.

**Gate:** user reviews the harvested context and the sub-question split; confirms the fleet is pointed at the right things.

### Phase 2 — MULTI-MODEL DIVERGENCE (the fleet)  →  *gate: user picks the fleet + approves the spend*

The signature phase. Fan each sub-question across a live, multi-vendor fleet so you get genuine divergence, not one model's opinion.

1. **Route each query** through sonar-router (`route_integration.route_query`) so you use the right web-research tool per query shape. Note: `route_integration.route_query(query)` and any fleet call must run AFTER `redaction_gate.assert_clean(query)` has passed — the query transits a subprocess arg (visible in a process listing) and every outbound prompt must clear the gate first. See §"How it invokes the scripts".
2. **Check the OpenRouter catalogue LIVE** — `fleet.list_models(api_key)` or the `openrouter-multimodal` MCP `search_models` — never assume a model id from memory; ids drift.
3. **Recommend a fleet, then ASK** which models for which function. **Mandatory floor: Gemini + OpenAI (GPT) + Grok + DeepSeek.** Add HuggingFace-hosted and other models per the use-case. The point is cross-vendor disagreement.
4. **Fan out in parallel** via `fleet.run_fleet(...)` (or the `openrouter-multimodal` MCP for interactive one-offs).
5. **Write each model's raw output** to disk *plus* a cross-model agreement/disagreement synthesis as you go. Disagreement is a verification target for Phase 3, not noise to average away.

**Bake in the hard-won fleet quirks (these are rules, not tips):**

| Quirk | Rule |
|---|---|
| Reasoning models burn hidden reasoning tokens | Set `max_tokens >= 8000` for any reasoning model. `2200` *truncated* Gemini/GPT and *zeroed* DeepSeek's visible output this session. `fleet.effective_max_tokens` enforces the 8000 floor for `reasoning: true` specs — set the flag correctly. |
| `~google/gemini-pro-latest` returns HTTP 400 | Use `google/gemini-2.5-pro`. `fleet.resolve_model_id` applies this alias fallback automatically and the result reports the substituted id. (the `google/gemini-2.5-pro` target is session-dated 2026-06-01 and self-validates: `resolve_model_id` only applies it if it's in the live `available` list, else returns None — always re-confirm ids via `list_models` at fire time) |
| Model ids drift; aliases 400 | Resolve exact ids at fire time against the live catalogue, and **report every substitution** to the user (the result dict's `model` field is the id actually used). |
| `perplexity_reason` times out on deep prompts | Use `perplexity_search` / `perplexity_ask` for fleet-adjacent web grounding, NOT `perplexity_reason`. (See sonar-router for the full matrix.) |
| A single model failing | Never kills the fleet. `run_fleet` captures per-model errors into that model's result (`ok: False`, `error: "..."`); the others still return. |

**Gate:** user approves the chosen fleet and the spend before the fan-out fires.

### Phase 3 — HARD-SKEPTIC WEB-GROUNDED VERIFICATION  →  *gate: user reviews the verification ledger*

**Non-negotiable. This is the reason the skill exists.** Full rules in `references/anti-hallucination.md` (R-1..R-5). Summary:

- **R-1 — Never trust an opinion-model proper noun.** A CVE/advisory ID, arXiv ID, repo, version, citation, tool name, or statistic from a fleet model is a *claim*, never a fact, until web-confirmed. This is unmissable: **a model that names a CVE is a model that may have invented that CVE.**
- **R-2 — Primary-source check, every claim.** `gh api` for repos; arXiv / Semantic Scholar (or the HuggingFace `paper_search` MCP) for papers; `WebFetch` (or the Playwright/`browser_*` MCP for JS-heavy or login-walled-public pages) for web pages; NVD / vendor advisory for CVEs.
- **R-3 — A dedicated FABRICATION-PURGE pass.** *Expect* fabrication. Diff every model claim against web truth and quarantine each unconfirmed proper noun.
- **R-4 — Hard-skeptic posture.** Actively try to *kill* each finding (saturation, prior art, no demand), not confirm it. Survivors earned their place.
- **R-5 — Whatever renders the truth.** If `WebFetch` can't render a page (JS-heavy, login-walled-public, trending feed), use the Playwright MCP. Grounding is mandatory; the tool is whatever shows the real page.

Record every check in a ledger → template `references/output-templates/verification-ledger.md`: each claim/proper-noun → the primary-source check performed → VERDICT (confirmed / fabricated / unverifiable) → the evidence (URL, API response, commit SHA).

**TRIPWIRE:** if a synthesis would surface a proper noun that **no Phase-3 verification record confirms**, BLOCK it and flag it to the user. An unverifiable claim is never silently promoted to fact.

**Gate:** user reviews the ledger — especially the fabricated/unverifiable rows — before synthesis.

### Phase 4 — 3× ADVERSARIAL VALIDATION  →  *gate: user reviews findings + corrections*

Run **three distinct validation passes** (separate agents, distinct lenses — do not collapse them into one):

1. **Fidelity** — does the synthesis faithfully represent what the verified sources actually say? No drift, no overclaim.
2. **Soundness** — is the reasoning valid? Do the conclusions follow from the evidence? Are there logical gaps?
3. **Completeness** — what's missing? Unanswered sub-questions, an un-checked claim, an obvious counter-source not consulted?

→ template `references/output-templates/validation-record.md`. Each pass logs its findings + the corrections made.

**Gate:** user reviews the validation findings and the corrections applied.

### Phase 5 — RANK (when warranted) + SYNTHESIZE  →  *gate: user reviews the synthesis*

Produce the standardized output doc(s). When the question calls for prioritization (what to build / publish / pursue), **rank ruthlessly with per-item evidence** and keep an **honest SKIP/KILL list** with reasons — saying "don't do this, because X" is as valuable as the ranking. → template `references/output-templates/ranked-synthesis.md`.

**Gate:** user reviews the ranked synthesis and the skip list.

### Phase 6 — CAPTURE  →  *gate: user approves what's written to memory*

1. **Append high-signal source domains** discovered this run via `novelty_log.append_good_sources([...])` so the next run is seeded. AND **always also hunt NEW sources this run** (arXiv-recent, GitHub-trending, niche feeds, primary docs) — never just reuse the list. See §"Novelty / good-sources".
2. **Leaf-only memory capture.** Add a per-project pointer + register the synthesis as a research-resync stream. **No global hub** — per Allen's leaf-only invariant, projects point DOWN at their own docs, never UP at a shared audit folder. See §"Capture / hand-off".
3. **Hand off to research-resync** so the synthesis stays fresh on a cadence.

**Gate:** user approves the memory writes and the research-resync registration.

## The anti-hallucination spine

This is summarized inline above (Phase 3, R-1..R-5) and spelled out in full — with the F1 case study (the receipts) and the TRIPWIRE — in **`references/anti-hallucination.md`**. Read it. The one-line version: **the fleet is an idea generator, not a fact source; nothing it names reaches the user as fact until a primary source confirms it.**

## The fleet — how to pick it

1. **Check OpenRouter LIVE.** `fleet.list_models(api_key)` (needs `OPENROUTER_API_KEY` in env) or the `openrouter-multimodal` MCP `search_models`. Never hardcode a model id from memory — ids drift and stale aliases 400.
2. **Recommend a set**, then **ASK the user** which models for which function (some questions want a big reasoning model; some want breadth across cheap models).
3. **Mandatory floor: Gemini + OpenAI (GPT) + Grok + DeepSeek.** HuggingFace-hosted + others per use-case. Cross-vendor coverage is the point.
4. **Honor the quirks table** in Phase 2: `max_tokens >= 8000` for reasoning models; `google/gemini-2.5-pro` not `~google/gemini-pro-latest`; `perplexity_search`/`perplexity_ask` not `perplexity_reason`; resolve exact ids at fire time and report substitutions.

Two execution paths — present both:

- **Programmatic / batch** — `fleet.run_fleet(...)` from a short Python snippet (below). Best for a planned, parallel fan-out of one prompt across N models with structured results.
- **Interactive** — the `openrouter-multimodal` MCP (`chat_completion`, `search_models`, `validate_model`). Best for ad-hoc, conversational one-offs where you want to eyeball one model's answer before fanning wider.

**MCP fan-out is serialized — fire models SEQUENTIALLY.** The `openrouter-multimodal` MCP processes `chat_completion` calls one at a time; issuing many in parallel makes the later calls time out (observed 2026-06-01: a 4-way parallel fan-out timed out the 3rd and 4th models). Fire one model per turn when using the MCP path. Very large/slow models (e.g. a 1.6T-param DeepSeek V4 Pro) can time out even when called solo — substitute a faster same-vendor variant (e.g. DeepSeek V4 Flash) and report the substitution. For genuine parallel fan-out with a per-call timeout, use `scripts/fleet.py` (ThreadPoolExecutor, 180 s/call) instead of the MCP.

## The redaction gate

A two-layer, fail-closed gate. **Both layers run; neither alone is sufficient.**

1. **Programmatic (necessary):** run `redaction_gate.assert_clean(prompt)` on **every** outbound prompt *before it leaves the machine*. It raises `SensitiveDataError` (fail-CLOSED) if it finds a secret shape (API-key shapes, PEM keys, AWS ids), an absolute user path, a `.secrets` reference, or an email. The error lists **labels + count only — never the matched value** (and `scan_for_sensitive` returns OFFSETS, never the secret), so logging a finding cannot leak a secret. Non-str input raises `TypeError` (fail-closed — you must pass the assembled string).
2. **Human (sufficient-completing):** *ask the user* what to redact, then 3×-verify the assembled prompt by eye. The regex gate catches shapes; the human catches *context* (a client name, a matter reference, a sensitive topic) that no regex knows about.

**Known v1 limitation (documented, fail-SAFE):** the email pattern also matches `git@host`-style SSH URLs (e.g. `git@github.com:...`). This is a *false positive that blocks, never one that leaks* — the gate fails closed, the human confirms it's just an SSH URL, and proceeds. Erring toward blocking is the correct direction for a secret gate.

## The scope dial

Recommend a tier, show the cost estimate, get confirmation. **Honor the R8 gate: any paid batch > USD 25 needs explicit Allen confirmation.** Exhaustive *always* requires a literal "yes, burn it".

| Tier | Models | Rounds | Agents | Cost est. | Use |
|---|---|---|---|---|---|
| **Quick** | 1–2 | 1 | few | ~USD 0.10–0.50 | a fast fact-find |
| **Standard** | full fleet (4–5) | 1 + verify | ~10 | ~USD 1–3 | a normal investigation |
| **Deep** | full fleet | R1 → R2 → R3 (verify + validate) | ~20–30 | ~USD 3–10 | this-session-grade rigor |
| **Exhaustive** | every available model, max thinking/effort | multi-round until convergence | hundreds (dynamic workflows) | uncapped (estimate shown) | "no tomorrow" — requires explicit "yes, burn it" |

The cost estimate is exactly that — an estimate. `run_fleet` returns a `cost_est` per model computed from per-million-token prices you supply (`in_price`/`out_price` on each model spec); sum them for the run total. Show the projected number *before* firing, and the actual after.

## Standardization & write-as-you-go

Every run writes to a gitignored, standardized workspace so output is recognizable across projects and a crash never loses work:

```
<project>/<TopicName>/_internal/        # gitignored
  audit/        # Phase 1 harvest + Phase 2 raw model outputs (one file per stream)
  research/     # cross-model synthesis, working notes
  decisions.md  # running decisions for this investigation
```

Mirror the proven layout. The five standardized output shapes live in `references/output-templates/` — copy the relevant one into `_internal/` and fill it in:

| Template | Phase | Shape |
|---|---|---|
| `decomposition.md` | 0 | sub-questions + critical-framing pushback + redaction decisions + chosen tier + cost estimate |
| `research-stream.md` | 1/2 | one non-overlapping sub-question per file; raw findings + provisional sources |
| `verification-ledger.md` | 3 | each claim → primary-source check → VERDICT → evidence |
| `validation-record.md` | 4 | the 3× adversarial passes (fidelity / soundness / completeness) + corrections |
| `ranked-synthesis.md` | 5 | ruthless ranking w/ per-item evidence + honest SKIP/KILL list |

**Confirm `_internal/` is gitignored** before writing anything sensitive into it (Phase 0).

## Capture / hand-off

- **Novelty log:** `novelty_log.append_good_sources([...])` records high-signal domains for next time; `read_good_sources()` seeds Phase 2/3. **Always also hunt NEW sources** — the list seeds, it does not cap.
- **Leaf-only memory:** add a per-project memory pointer to the synthesis doc; do NOT create or point at a global audit hub (the leaf-only invariant — projects point DOWN, never UP).
- **research-resync hand-off:** register the Phase 5 synthesis as a research-resync *stream* (per-project YAML under `~/.claude/research/<project>/`) so it gets re-run on a cadence and decay is detected. This is the composition seam: labcoat does the rigorous first pass, research-resync maintains it.

## How it invokes the scripts

All scripts live in `scripts/` and are libraries (no CLI on `fleet.py`/`redaction_gate.py`/`novelty_log.py`; `route_integration.py` shells the sonar-router CLI internally). Invoke them from a short `python` snippet with `OPENROUTER_API_KEY` in the env (never on the command line, never hardcoded, never logged).

**Route a query (Phase 2):**
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("scripts").resolve()))
import route_integration
verdict = route_integration.route_query("does repo trailofbits/skills exist and what is its license")
# -> {"recommended_tool": ..., "fallback": ..., "score": {...}, "rationale": ..., "schema_version": 2}
#    or a safe default {"recommended_tool": "perplexity_ask", ..., "degraded": True} if the router can't run
```

**Redaction gate (before EVERY outbound prompt):**
```python
import redaction_gate
redaction_gate.assert_clean(prompt)   # raises SensitiveDataError (labels+count only) if anything is flagged
```

**Fan out across the fleet (Phase 2)** — `OPENROUTER_API_KEY` must be set in the env first:
```python
import fleet
available = fleet.list_models(__import__("os").environ["OPENROUTER_API_KEY"])  # live catalogue
models = [
    {"id": "google/gemini-2.5-pro", "reasoning": True,  "in_price": 1.25, "out_price": 5.0,  "max_tokens": 8000},
    {"id": "openai/gpt-5.5",        "reasoning": True,  "in_price": 5.0,  "out_price": 15.0, "max_tokens": 8000},
    {"id": "x-ai/grok-4",           "reasoning": False, "in_price": 3.0,  "out_price": 15.0},
    {"id": "deepseek/deepseek-chat","reasoning": True,  "in_price": 0.27, "out_price": 1.10, "max_tokens": 8000},
]
results = fleet.run_fleet("<sub-question prompt>", models, available=available, temperature=0.4, parallel=True)
# each result has the SAME 7 keys: {model, ok, text, in_tokens, out_tokens, cost_est, error}
# per-model failures are captured (ok=False, error set); the API key never appears in any result
run_cost = sum(r["cost_est"] for r in results)
```
(Model ids/prices above are illustrative — resolve real ids against `available` at fire time and report any substitution.)

**Capture good sources (Phase 6):**
```python
import novelty_log
novelty_log.append_good_sources(["distill.pub", "lwn.net"])   # case-insensitive dedup against references/good-sources.md
seeds = novelty_log.read_good_sources()                        # seed next run's Phase 2/3
```

## Sub-skills it leans on

- **superpowers:using-superpowers** — establishes how to find and use skills; invoke at the start of any session that will use the pipeline.
- **superpowers:brainstorming** — for Phase 0 critical-framing / decomposition when the question is fuzzy. Recommend-install if absent.
- **sonar-router** — the per-query tool-routing matrix; `route_integration.route_query` wraps its classifier. Used in Phase 2. Public companion: [Polycentric-Labs/sonar-router](https://github.com/Polycentric-Labs/sonar-router). `route_integration` degrades gracefully to a safe default if sonar-router is absent.
- **superpowers:dispatching-parallel-agents** / **subagent-driven-development** — for the parallel harvest (Phase 1) and the 3× distinct validators (Phase 4).

## What this skill is NOT

- **Not a one-shot report** — that's deep-research. labcoat is multi-round and gated.
- **Not a doc-refresher** — that's research-resync. labcoat does the rigorous *first* pass and feeds research-resync.
- **Not a fact source** — the fleet generates ideas; only Phase 3 primary-source checks produce facts.
- **Not autonomous** — every phase stops and asks. It never auto-fans-out, auto-spends, or auto-writes-to-memory.
- **Not a hardcoded model list** — it checks OpenRouter live and asks which models to use each run.

## Cross-references

- Anti-hallucination rules + F1 case study: `references/anti-hallucination.md`
- Output templates: `references/output-templates/{decomposition,research-stream,verification-ledger,validation-record,ranked-synthesis}.md`
- Seed source list: `references/good-sources.md`
- The fleet runner + gate + novelty log + router wrapper: `scripts/{fleet,redaction_gate,novelty_log,route_integration}.py`
- Tests: `tests/` (run `python -m pytest tests/ -q` from the skill root)
- v2 remote-MCP plan (future): `docs/MCP-V2-PLAN.md`
- Companion skill (per-query routing): [`sonar-router`](https://github.com/Polycentric-Labs/sonar-router)

## Validation

1. **Static:** `python -c "import yaml; yaml.safe_load(open('SKILL.md').read().split('---')[1])"` — frontmatter parses as valid YAML.
2. **Runtime:** invoke a real net-new investigation; observe that each phase stops at its gate, that every proper noun in the synthesis traces to a Phase-3 verification record, and that the redaction gate runs on every outbound prompt.
