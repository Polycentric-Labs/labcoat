---
name: polycentric-labcoat
description: The rigorous NET-NEW research-investigation engine. Use when a question demands deep, multi-model, hard-skeptic, web-grounded investigation rather than a quick lookup — e.g. "investigate X with the fleet", "rigorous research on Y", "fan this out across models", "hard-skeptic research", "net-new investigation", "is this novel / does this already exist", or /polycentric-labcoat. Runs a 6-phase pipeline (scope+redact+cost → harvest → multi-model OpenRouter divergence → hard-skeptic primary-source verification → 3× adversarial validation → ranked synthesis → capture) with a STOP-AND-ASK user gate at every phase, and web-confirms EVERY proper noun (CVE/advisory ID, arXiv ID, repo, version, citation, tool name, stat) before it reaches the user as fact. NOT for refreshing an existing synthesis doc on a cadence (that is research-resync, which this FEEDS) and NOT for a single-shot cited report (that is deep-research). Triggers also on "multi-model research", "polycentric", "investigate with Gemini + GPT + Grok + DeepSeek".
license: MIT
---

# /polycentric-labcoat — The rigorous net-new research engine

A 6-phase investigation methodology that fans a question across a live multi-model fleet, then **kills** every finding it can't trace to a primary source, validates the survivors three ways, and hands back a ruthlessly ranked synthesis. It asks you at every gate. It web-grounds every proper noun. It is built to be wrong-proof, not fast.

This skill codifies the method that worked in the 2026-06-01 multi-model research passes: **harvest → multi-model divergence → hard-skeptic web-grounded verification → 3× adversarial validation → ruthless ranking → standardized synthesis**, writing as you go and asking the user at every gate.

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
4. **Redaction gate (interactive + programmatic).** Decide what must NOT leave the machine in any outbound prompt. *Ask the user explicitly* what to redact (client names, internal paths, anything sensitive), then 3×-verify the assembled prompt is clean. The programmatic gate is `redaction_gate.redact(prompt, client_terms=[...])` (v2, two-class): a **Class-A secret → `hard_block`** (HALT + rotate; nothing leaves), a **Class-B path/email/client-term → surgical typed-placeholder redact-and-continue**, with a **`signal.recommend_stop`** flag when the redaction guts the query (pause and ask before sending). It is necessary-not-sufficient — run it on every outbound prompt *and* do the human pass. See §"The redaction gate".
5. **Pick a depth tier + show the two-line cost estimate + ask a TOLERANCE.** Recommend a tier from the scope dial (below). Show `spend.two_line_estimate(model_specs, n_agents=...)` — **both** lines (the OpenRouter fleet cost *and* the dominant, variable Claude-orchestration cost) plus its `confidence` label (`tight` for a one-off, `very-rough` for a loop cycle) — and ask the user for a spend **TOLERANCE** (the hard ceiling). Get explicit confirmation. Exhaustive requires a literal "yes, burn it".

**Gate:** user signs off on scope, decomposition, depth tier, redaction list, and cost. Nothing fans out until they do.

### Phase 1 — HARVEST  →  *gate: user reviews the harvest before the fleet runs*

Gather internal context + answer the decomposed sub-questions with parallel agents. **Each agent owns one non-overlapping sub-question and writes its own file** to `<project>/<TopicName>/_internal/audit/` (write-as-you-go). → template `references/output-templates/research-stream.md`. This is local/cheap grounding *before* you spend on the fleet: existing docs, repo reads, prior art you already have access to.

**Gate:** user reviews the harvested context and the sub-question split; confirms the fleet is pointed at the right things.

### Phase 2 — MULTI-MODEL DIVERGENCE (the fleet)  →  *gate: user picks the fleet + approves the spend*

The signature phase. Fan each sub-question across a live, multi-vendor fleet so you get genuine divergence, not one model's opinion.

1. **Route each query** through sonar-router (`route_integration.route_query`) so you use the right web-research tool per query shape. Note: `route_integration.route_query(query)` and any fleet call must run AFTER `redaction_gate.redact(query, client_terms=[...])` clears it (a `hard_block` → HALT; a `signal.recommend_stop` → pause and ask) — the query transits a subprocess arg (visible in a process listing) and every outbound prompt must clear the gate first. **Send the returned `clean_text`, not the raw query.** See §"How it invokes the scripts".
2. **Check the OpenRouter catalogue LIVE** — `fleet.list_models(api_key)` or the `openrouter-multimodal` MCP `search_models` — never assume a model id from memory; ids drift.
3. **Recommend a fleet by comparative advantage, then ASK** which models for which function. Reason over the live catalogue — match each sub-question to the model with the edge for it (reasoning depth vs. breadth vs. grounding). `model_selector.propose_fleet(candidate_model_ids, sub_questions, tier=...)` enriches your candidates with each model's risk card, the derived `gov_adjacent_safe` flag, the tier fleet-size, Sonar-split advice, and the blunt-critic benchmark pointers — it does **not** pick (the comparative-advantage reasoning is yours). **Mandatory floor: Gemini + OpenAI (GPT) + Grok + DeepSeek** (Grok is `optional_only` — never the default, always caveated). Add HuggingFace-hosted and other models per the use-case. The point is cross-vendor disagreement.
4. **Fan out in parallel** via `fleet.run_fleet(...)` (or the `openrouter-multimodal` MCP for interactive one-offs).
5. **Write each model's raw output** to disk *plus* a cross-model agreement/disagreement synthesis as you go. `run_fleet` streams + disk-captures each model to `<capture_dir>/<safe-model-id>.partial` as tokens arrive (pass `capture_dir=`), so a mid-stream break never loses partial output. Disagreement is a verification target for Phase 3, not noise to average away.
6. **Honor `completion_status`.** Each result carries `completion_status ∈ {complete, known-incomplete, deterministic-fail, unavailable}`; `ok` is `True` only when it is `complete`. Treat anything else as the **known-incomplete honesty flag** — surface it to the user, and never silently use a truncated / failed stream as if it were whole. (Same rule the audit ledger enforces: a known-incomplete stream is never promoted to `confirmed`.)
7. **Record every outbound query in the audit ledger** (append-only). `audit.ledger_record_from_fleet(timestamp=…, loop_id=…, query_id=…, sub_question=…, redaction_applied=True, fleet_result=r)` → `audit.append_ledger(ledger_path, rec)` — one JSONL row per query; `model` / `capture_path` / `completion_status` / `cost` pull through the fleet result. Log any question or idea **the instant it arises** with `audit.append_question(...)`. As Phase 3/4 resolve a query, append a NEW row with the updated `validation_verdict` (never edit a prior row; a known-incomplete stream is never moved to `confirmed`). See §"How it invokes the scripts".

**Bake in the hard-won fleet quirks (these are rules, not tips):**

| Quirk | Rule |
|---|---|
| Reasoning models burn hidden reasoning tokens | Set `max_tokens >= 8000` for any reasoning model. `2200` *truncated* Gemini/GPT and *zeroed* DeepSeek's visible output this session. `fleet.effective_max_tokens` enforces the 8000 floor for `reasoning: true` specs — set the flag correctly. |
| `~google/gemini-pro-latest` returns HTTP 400 | Use `google/gemini-2.5-pro`. `fleet.resolve_model_id` applies this alias fallback automatically and the result reports the substituted id. (the `google/gemini-2.5-pro` target is session-dated 2026-06-01 and self-validates: `resolve_model_id` only applies it if it's in the live `available` list, else returns None — always re-confirm ids via `list_models` at fire time) |
| Model ids drift; aliases 400 | Resolve exact ids at fire time against the live catalogue, and **report every substitution** to the user (the result dict's `model` field is the id actually used). |
| `perplexity_reason` times out on deep prompts | Use `perplexity_search` / `perplexity_ask` for fleet-adjacent web grounding, NOT `perplexity_reason`. (See sonar-router for the full matrix.) |
| A single model failing | Never kills the fleet. `run_fleet` captures per-model errors into that model's result (`ok: False`, `error: "..."`); the others still return. |
| A truncated / never-stopped stream | `run_fleet` trusts a generation complete **only** on an explicit stop reason; `length`/no-stop → `known-incomplete`, re-run within `max_attempts`, then surfaced as-is — never silently promoted to complete. A deterministic 4xx fails fast (no wasted reruns). |

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
2. **Leaf-only memory capture.** Add a per-project pointer + register the synthesis as a research-resync stream. **No global hub** — per the leaf-only invariant, projects point DOWN at their own docs, never UP at a shared audit folder. See §"Capture / hand-off".
3. **Hand off to research-resync** so the synthesis stays fresh on a cadence.
4. **Close the audit cycle.** Regenerate the human ledger view — `audit.render_ledger_markdown(audit.read_ledger(ledger_path))` — and emit `audit.generate_resurface(records, questions, timestamp=…)`: the 3 end-of-cycle buckets — *apply the validated findings now* · *new research paths to pursue* · *unresolved / uncertain*. Bucket 2's "which paths to pursue" is a STOP-AND-ASK gate, never auto-pursued.

**Gate:** user approves the memory writes, the research-resync registration, and the resurface buckets.

## The anti-hallucination spine

This is summarized inline above (Phase 3, R-1..R-5) and spelled out in full — with the F1 case study (the receipts) and the TRIPWIRE — in **`references/anti-hallucination.md`**. Read it. The one-line version: **the fleet is an idea generator, not a fact source; nothing it names reaches the user as fact until a primary source confirms it.**

## The north star (governing personality)

labcoat runs on one ethos at **every** stage, from invocation to the last documented finding: **intense curiosity** (dig deeper, dream bigger — if a deeper dive has even a *tiny* chance of uncovering something novel, pursue it), **obsessive skepticism toward validated truth** (nothing is fact until a primary source confirms it), and **religious devotion to dreaming bigger** (take validated truth to its conclusion — what can it *do*?). Full rationale + the per-phase hooks: **`references/north-star.md`**; the machine form is `scripts/north_star.py`.

**The honesty stake (hard rule):** ambition is *unbounded* in the engine; *claims* are bounded by verification. Curiosity drives the search; skepticism gates the claims. This is the same spine as the anti-hallucination rules — overclaiming is forbidden; trustworthiness is the moat.

**Enforced-lite per-phase hooks:** at each gate, *before* proposing to the user, emit the 1–2 line reflection for that phase — `north_star.reflection_for_phase(n)` (n = 0..6) — in the spirit of the pillar that phase serves (curiosity for scope / harvest / divergence; skepticism for verify / validate; dreaming-bigger for synthesize / capture).

## The fleet — how to pick it

1. **Check OpenRouter LIVE.** `fleet.list_models(api_key)` (needs `OPENROUTER_API_KEY` in env) or the `openrouter-multimodal` MCP `search_models`. Never hardcode a model id from memory — ids drift and stale aliases 400.
2. **Recommend a set**, then **ASK the user** which models for which function (some questions want a big reasoning model; some want breadth across cheap models).
3. **Mandatory floor: Gemini + OpenAI (GPT) + Grok + DeepSeek.** HuggingFace-hosted + others per use-case. Cross-vendor coverage is the point.
4. **Honor the quirks table** in Phase 2: `max_tokens >= 8000` for reasoning models; `google/gemini-2.5-pro` not `~google/gemini-pro-latest`; `perplexity_search`/`perplexity_ask` not `perplexity_reason`; resolve exact ids at fire time and report substitutions.
5. **Safety-screen the fleet** with `model_selector.propose_fleet` → each candidate's risk card + the derived `gov_adjacent_safe` flag (jurisdiction + export-control status from `references/model-risk-cards.md`; the four PRC-hosted providers are gov-adjacent-**FALSE** for hosted use, flipping only on self-hosted open weights). Surface any government-adjacent-unsafe pick before firing.
6. **Sonar-Pro split → offer the upgrade.** When the question splits into more distinct subjects than one deep query handles well (`model_selector.needs_sonar_split`), recommend either many Sonar-Pro queries **or ask the user to upgrade to Sonar Deep Research** — name the tradeoff (cost vs. depth) and let them choose.
7. **Pick the blunt critic empirically.** The Phase-4 blunt critic is chosen at selection time by an **A/B flawed-claim critique eval** (inject known methodological flaws; measure each candidate's recall) — NOT hardcoded. Sycophancy/critique benchmarks (`propose_fleet` returns the pointers) are a *prior*, not the answer.

Two execution paths — present both:

- **Programmatic / batch** — `fleet.run_fleet(...)` from a short Python snippet (below). Best for a planned, parallel fan-out of one prompt across N models with structured results.
- **Interactive** — the `openrouter-multimodal` MCP (`chat_completion`, `search_models`, `validate_model`). Best for ad-hoc, conversational one-offs where you want to eyeball one model's answer before fanning wider.

**MCP fan-out is serialized — fire models SEQUENTIALLY.** The `openrouter-multimodal` MCP processes `chat_completion` calls one at a time; issuing many in parallel makes the later calls time out (observed 2026-06-01: a 4-way parallel fan-out timed out the 3rd and 4th models). Fire one model per turn when using the MCP path. Very large/slow models (e.g. a 1.6T-param DeepSeek V4 Pro) can time out even when called solo — substitute a faster same-vendor variant (e.g. DeepSeek V4 Flash) and report the substitution. For genuine parallel fan-out with a per-call timeout, use `scripts/fleet.py` (ThreadPoolExecutor, 180 s/call) instead of the MCP.

## The redaction gate

A two-layer, fail-closed, **two-class** gate. **Both layers run; neither alone is sufficient.**

1. **Programmatic (necessary):** run `redaction_gate.redact(prompt, client_terms=[...])` on **every** outbound prompt *before it leaves the machine*. It splits findings into two classes:
   - **Class A — true secrets** (API-key shapes, PEM keys, AWS ids, `.secrets` references): `hard_block=True`, `clean_text=None`. **HALT** — nothing leaves; rotate if it was a live secret.
   - **Class B — contextual** (absolute user paths, emails, caller-supplied `client_terms`, optional Presidio NER PII): **surgically replaced** with typed, indexed placeholders (`<PATH_1>`, `<EMAIL_1>`, `<CLIENT_1>`) so the query stays useful — redact-and-continue, not block.
   A post-redaction **`signal`** then sets `recommend_stop` when the surgical redaction guts the query — `(>15% of non-ws chars redacted AND ≥3 Class-B entities) OR <10 non-ws chars left`; on that flag, **pause and ask the user** before sending. Findings carry **offsets only — never the matched value** (so logging a finding cannot leak a secret); non-str input raises `TypeError` (fail-closed). `redaction_gate.assert_clean(prompt)` remains a fast **Class-A-only** wrapper (raises `SensitiveDataError`) for hot paths.
2. **Human (sufficient-completing):** *ask the user* what to redact, then 3×-verify the assembled prompt by eye. The regex/NER gate catches shapes; the human catches *context* (a client name, a matter reference, a sensitive topic) that no detector knows about.

**`git@host` SSH URLs — fixed in v2.** The email detector now allowlists `git@host`-style SSH URLs (e.g. `git@github.com:...`) via an SSH-URL exclusion, so they no longer false-positive. The gate still fails *closed* on anything genuinely ambiguous — erring toward blocking is the correct direction for a secret gate.

## The scope dial

Recommend a tier, show the cost estimate, get confirmation. **Honor the R8 gate: any paid batch > USD 25 needs explicit operator confirmation.** Exhaustive *always* requires a literal "yes, burn it".

| Tier | Models | Rounds | Agents | Cost est. | Use |
|---|---|---|---|---|---|
| **Quick** | 1–2 | 1 | few | ~USD 0.10–0.50 | a fast fact-find |
| **Standard** | full fleet (4–5) | 1 + verify | ~10 | ~USD 1–3 | a normal investigation |
| **Deep** | full fleet | R1 → R2 → R3 (verify + validate) | ~20–30 | ~USD 3–10 | this-session-grade rigor |
| **Exhaustive** | every available model, max thinking/effort | multi-round until convergence | hundreds (dynamic workflows) | uncapped (estimate shown) | "no tomorrow" — requires explicit "yes, burn it" |

The cost estimate is exactly that — an estimate. `run_fleet` returns a `cost_est` per model computed from per-million-token prices you supply (`in_price`/`out_price` on each model spec); sum them for the run total. Show the projected number *before* firing, and the actual after.

**Live tracking + the per-loop tolerance gate.** `spend.Tracker` accumulates ACTUAL spend (both lines) for a running health ticker; before each loop of a multi-round / Nuclear run, `spend.would_next_loop_breach(spent_so_far, next_loop_est, tolerance)` checks whether the next loop would cross the ceiling. If it would, **STOP that loop (not the session)** and surface the over-tolerance option menu — let the user choose:

1. **Raise** the tolerance (set a new explicit ceiling).
2. **Reduce variants** — fewer models / a smaller fan-out next loop.
3. **Cheap wrap-up** — synthesize what's validated so far, no new spend.
4. **Free validate-and-save** — run only the no-cost validation + capture, then stop.
5. **Other** — the user directs.

## Standardization & write-as-you-go

Every run writes to a gitignored, standardized workspace so output is recognizable across projects and a crash never loses work:

```
<project>/<TopicName>/_internal/        # gitignored
  audit/
    SESSION-LEDGER.jsonl     # canonical append-only audit ledger — one row per outbound query (Phase 2)
    QUESTIONS-IDEAS.md       # append-only questions/ideas log (any phase, the instant they arise)
    RESURFACE.md             # end-of-cycle 3-bucket resurface (Phase 6)
    <safe-model-id>.partial  # Phase 2 streamed model captures (the ledger's raw substrate)
    ...                      # Phase 1 harvest + per-stream raw outputs
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

## Durable autonomy (Tier 2 — opt-in)

The interactive pipeline above stops and asks at every gate. The **Tier-2 durable orchestrator** is the opt-in *autonomous* mode: it drives multi-loop runs of the 6-phase pipeline unattended, **survives a host reboot**, and resumes mid-run. Operator spec + bring-up smoke checklist: **`references/orchestrator-host.md`**; the pure decision core is `scripts/orchestrator.py` + `scripts/pacing.py` + the `spend.Tracker` reservation.

- **Resume:** on restart, `orchestrator.plan_resume(audit.read_ledger(path))` replays only the not-yet-`complete` queries (skip `complete`, re-drive `known-incomplete` / `unavailable`, never `deterministic-fail`). The append-only ledger IS the checkpoint store.
- **Guarantee = at-least-once + idempotency** (the upstream gateway has no request dedup). Cost backstop = **pessimistic spend reservation**: `Tracker.reserve(est)` before the call (with `audit.append_ledger(intent, fsync=True)`), released only on a confirmed result — the in-memory reservation prevents live (within-process) over-spend; the REBOOT-durable backstop is the fsync'd `known-incomplete` intent record on disk, which resume re-drives (at-least-once).
- **Pacing:** `pacing.pacing_decision(signals)` → proceed / graceful-pause (429 / low `anthropic-ratelimit-*`) / hard-stop (Anthropic monthly cap / OpenRouter 402); `pacing.ramp_after_idle` ramps traffic up gradually after a pause.
- **Per-loop gate:** `orchestrator.loop_decision` composes pacing + the spend-tolerance breach → continue / pause / stop, surfacing the over-tolerance OPTION MENU (the §"The scope dial" menu).
- **Novelty / saturation gate (CALIBRATED + ENFORCING by default):** `novelty_gate.cny(...)` measures *Confirmed-Novelty Yield* — new confirmed findings per loop, filtered by a two-stage dedup + distance — computed **ONLY over `validation_verdict=='confirmed'` records**, so a loop emitting varied-but-*fabricated* findings scores 0 (the audit-v2 honesty invariant doubles as the anti-gaming property). `novelty_gate.yield_collapse(...)` (an SPC K-consecutive-low run-rule) flags yield-collapse; on collapse `loop_decision` **pauses-and-pings the human — it never auto-stops** (corrigible). **Calibrated 2026-06-23** on 3 diverse multi-loop curves (sharp / steady-productive / bursty): **`tau=0.30` / `floor=0` / `window=3`** classify all three with zero false positives/negatives, so the gate now **ENFORCES by default** (`--novelty-enforcing`; `--no-novelty-enforcing` restores WARN-only). **The curves ship** (`tests/fixtures/novelty-gate-calibration-curves.json`) and `tests/test_novelty_gate.py::test_calibration_*` re-derives the calibration offline (they pass only for `window=3`; `window=2` is shown false-firing in the bursty curve's `[0,0]` valley). Honest caveat: `floor`/`window` are derived from these curves; **`tau` is UNDER-determined** by them (tau-invariant — the seen-set dedup dominates) and is held over from the prior default. Provenance: `references/measured-results.md` §4. It is a *saturation* signal ("still finding new validated things?"), NOT a value-aware fitness function (the Tier-3 value axis below stays ADVISORY — the Goodhart-hard problem).
- **Host:** Agent SDK (Python) under a Windows Service / Task Scheduler `ONSTART /ru System`, `ANTHROPIC_API_KEY` from the service env (never `CLAUDE_CODE_OAUTH_TOKEN`; never Desktop/cloud). TOLERANCE stays a hard ceiling.
- **§5.2 Nuclear engine (`scripts/nuclear.py`):** the autonomous *multi-loop* mode. An async Agent-SDK brain (`claude_agent_sdk.query`) drives, per loop: **decompose** (the FIRST loop decomposes the original question; each LATER loop re-decomposes FROM the prior loop's ranked gaps — the loop-evolution engine, so the engine chases the next question instead of re-asking) → **fleet fan-out** via `orchestrator_host.run_loop` (the durable record-before-call `fsync` + reservation; `query_id` is run-/loop-scoped so evolved loops fan out cleanly) → **hard-skeptic primary-source verify** (the brain with `WebSearch`/`WebFetch`) which writes each *confirmed* finding's `claim_text` into the ledger → **gap-evolution** (`nuclear_core.gap_prompt` → `loop_evolution.parse_gaps`/`rank_gaps`/`select_evolved_questions`: surface gaps + contradictions, rank contradictions first, filter, seed the next loop's decompose) → **novelty** (`novelty_gate.cny` over confirmed-only + `novelty_store` seen-set/corpus/CNY-history persistence + `yield_collapse`, now CALIBRATED + ENFORCING) → **pacing** (the live `RateLimitEvent` / `ResultMessage.api_error` → `pacing.rate_limit_signals` + `spend.quota_signals` → `pacing.pacing_decision`) → **per-loop decision** (`compose_loop_state` → `loop_decision` → the option menu / pause-and-ping) → **synthesize** over the confirmed corpus on stop. Operator subcommands: `estimate` (FREE — two-line estimate, no paid call) and `run --tolerance <usd>` (PAID, tiny by default). Layered money gates: the two-line estimate shown first, TOLERANCE as the hard ceiling, the **R8 burn gate** (`spend.requires_explicit_burn` → estimate over the threshold needs `--confirm "yes, burn it"`), and `ClaudeAgentOptions.max_budget_usd` per brain call. Keys come from the environment (`OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` — the primary path); as an optional convenience the operator scripts also read `$LABCOAT_SECRETS_DIR/*.env` (default `~/.secrets/*.env` — one author's local layout, not a requirement), loading in-process, never printing the value, and announcing the source path so a credential is never picked up implicitly.
- **Tier-3 — value-aware novelty + memory + degeneracy (ADVISORY):** the `cny` count axis is the *diversity* signal; Tier-3 adds the **quality** axis it omits. `value_axis.py` weights a confirmed finding by the number of **independent primary sources** that confirmed it (`source_count` → capped `quality_weight`), reports a quality-weighted yield (`weighted_cny`), keeps a MAP-Elites-lite **best-per-cell archive** (`qd_archive_update`), and runs the **degeneracy detector** (`weighted_yield_collapse` — the *same* SPC rule on the weighted scalar) plus `cost_per_verified_finding`. Persistence is the pluggable **`MemoryBackend` seam** (`memory_backend.py`): a stdlib-SQLite append-only **bi-temporal + provenance** backend (the §6.3 default; `--backend sqlite`) or a zero-dependency flat-file backend (`--backend file`) — drop-in interchangeable. **Every value-aware signal is ADVISORY: reported each loop, never consumed by `loop_decision`**, until calibrated on a recorded run (the value axis is the honestly-unsolved Goodhart-hard problem — the weight is capped, computed only over `confirmed`, and pairs with the detector as defense-in-depth, none Goodhart-proof).

- **North-Star capabilities — WIRED-LIVE, validated to an ADVISORY bar.** **Loop-evolution** (`loop_evolution.py` + `run_scope.py`): each loop after the first re-decomposes from the prior loop's ranked gaps (contradictions first), so the engine *chases* the next question instead of re-asking; plus the run-scoped ledger fix so a shared workspace no longer collides across questions. The three research axes each have a **pure, unit-tested core AND a live adapter that runs end-to-end** — what each is *measured* to do, stated honestly:
  - **N1 literature-grounded novelty** (`n1_novelty.py` core — RND-style relative-neighbor-density + a mandatory date-cutoff; `n1_embedder`/`n1_index`/`n1_corpus*`/`n1_build` adapters). **Runs live** over a SPECTER2 + faiss index (arXiv + an OpenAlex ~25k-work corpus). Its out-of-distribution gate is MEASURED: **held-out-field AUROC 0.889 [0.874, 0.904]**. Read it correctly — it is an **anti-out-of-corpus detector, NOT a general novelty oracle**; it is field-dependent, and it tells you a claim is far from *this corpus*, not that it is new to the world.
  - **N3 combinatorial / analogical synthesis** (`combinatorial.py` core — a MAP-Elites archive over `(domainA,domainB,mechanism)` + multiplicative `creativity = novelty × utility` + a proposer⊥judge separation; `combine_live.py` adapter). **Runs live** end-to-end: propose → N1-novelty → judge → ground. A measured comparison **CONFIRMED the engine beats raw prompting on prior-art distance for DISTANT domain pairs only** (CMH p=7.4e-5; cluster-bootstrap CI [0.104, 0.320]). It does **not** beat raw prompting on near pairs. Its **soundness axis is HUMAN-GATED**: an LLM judge could not be validated past ~0.70 on hard negatives — it catches clear named-law violators but cannot separate a subtly incoherent cross-domain mapping from genuine novelty, so *verified-non-obvious* needs a human expert, not the panel.
  - **N2 gap / whitespace channels** (`gap_channels.py` core — Swanson-ABC + future-work + contradiction → reconciliation; `gaps_live`/`n2_extract_llm`/`n2_crosslit`/`pubmed_adapter` adapters). **Runs live** — and carries an **HONEST NEGATIVE**: the count/co-occurrence Swanson-ABC channel **cannot discriminate a documented cross-literature discovery from big-literature spurious pairs** (the confound is literature SIZE; neither an IDF-specificity priority nor size-normalization rescued it). A PPMI + hub-exclusion fix removed **~99.85% of the noise flood**, which is a real win for the machinery — but the channel is not a discovery detector on raw co-occurrence. A **SEMANTIC substrate** (MeSH/UMLS semantic-type prefilter, SemMedDB predications, or LLM-relevance) is the known **deferred** next step.

⚠ Built + how it's validated: `orchestrator_host.py` + **§5.2 Nuclear (`scripts/nuclear.py`)** are built and live-validated; the **loop-evolution engine is WIRED-LIVE** and the **saturation gate is CALIBRATED + ENFORCING** (2026-06-23, 3-curve calibration — see the gate bullet above). The **N1 / N3 / N2 live adapters are WIRED and run end-to-end live, but are validated only to an ADVISORY bar** — each carries the measured scope + the honest limit named in the bullet above (N1 = anti-out-of-corpus, not a novelty oracle; N3 = confirmed on distant pairs only, soundness human-gated; N2 = count-ABC honest negative, semantic substrate deferred). The **Tier-3 value-axis + `MemoryBackend` + degeneracy detector stay ADVISORY** (the value axis is the honestly-unsolved Goodhart-hard problem). The pure core throughout (`nuclear_core`, `loop_evolution`, `n1_novelty`, `combinatorial`, `gap_channels`, `roc`, `spc`, `enrichment_stats`, `novelty_store`, `value_axis`, `memory_backend`, `spend`, `pacing`, `run_scope`) is unit-tested (**577 tests**); the live async `run` path + the operator adapters are operator-gated + smoke-validated (estimate-first). Still open: the N2 semantic substrate, human-expert gating for the N3 sound axis, broader multi-field N1 calibration, and a broader multi-run calibration before the value axis could ever move from advisory to enforcing.

## How it invokes the scripts

All scripts live in `scripts/` and are libraries (no CLI on `fleet.py`/`redaction_gate.py`/`novelty_log.py`; `route_integration.py` shells the sonar-router CLI internally). Invoke them from a short `python` snippet with `OPENROUTER_API_KEY` in the env (never on the command line, never hardcoded, never logged).

**Route a query (Phase 2):**
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("scripts").resolve()))
import route_integration
verdict = route_integration.route_query("does repo trailofbits/skills exist and what is its license")
# -> {"recommended_tool": ..., "fallback": ..., "score": {...}, "rationale": ...}  (exact shape depends on the installed sonar-router version)
#    or a safe default {"recommended_tool": "perplexity_ask", ..., "degraded": True} if the router can't run
```

**Redaction gate (before EVERY outbound prompt) — v2 two-class:**
```python
import redaction_gate
r = redaction_gate.redact(prompt, client_terms=["AcmeCorp"])   # offsets only — never echoes a matched value
if r["hard_block"]:                       # Class-A secret detected -> HALT + rotate; nothing leaves (signal is None here)
    raise SystemExit("secret in outbound prompt: " + str([f["label"] for f in r["findings"]]))
# past the hard_block guard, signal is always present (never check it before the hard_block guard):
if r["signal"]["recommend_stop"]:         # surgical redaction gutted the query -> pause + ask the user
    ...                                   # confirm (or re-scope) before sending
outbound = r["clean_text"]                # Class-B spans -> typed placeholders <PATH_1> / <EMAIL_1> / <CLIENT_1>
# redaction_gate.assert_clean(prompt) remains a fast Class-A-only wrapper for hot paths
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
results = fleet.run_fleet("<sub-question prompt>", models, available=available, temperature=0.4,
                          parallel=True, capture_dir="_internal/audit/captures")  # stream -> disk per model
# each result carries: {model, ok, text, in_tokens, out_tokens, cost_est, error,
#   completion_status, rerun_count, capture_path}; ok is True ONLY when completion_status == "complete"
# treat completion_status != "complete" as the known-incomplete honesty flag (surface, never silently use)
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

**Audit trail (Phase 2 ledger + Phase 6 resurface):**
```python
import audit
rec = audit.ledger_record_from_fleet(timestamp=ts, loop_id="L1", query_id="q1",
        sub_question="is X novel?", redaction_applied=True, fleet_result=r)   # r from run_fleet
audit.append_ledger(ledger_path, rec)                                          # append-only JSONL (fsync=True for durable runs)
audit.append_question(questions_path, timestamp=ts, text="try MAP-Elites", kind="idea")  # the instant it arises
# end of cycle:
md = audit.render_ledger_markdown(audit.read_ledger(ledger_path))             # human Markdown view
resurface = audit.generate_resurface(audit.read_ledger(ledger_path),
                                     audit.read_questions(questions_path), timestamp=ts)  # 3 buckets
```
(All timestamps are passed IN as ISO-8601 strings — `audit` never calls `datetime.now()`.)

## Sub-skills it leans on

- **superpowers:using-superpowers** — establishes how to find and use skills; invoke at the start of any session that will use the pipeline.
- **superpowers:brainstorming** — for Phase 0 critical-framing / decomposition when the question is fuzzy. Recommend-install if absent.
- **sonar-router** — the per-query tool-routing matrix; `route_integration.route_query` wraps its classifier. Used in Phase 2. Public companion: [Polycentric-Labs/sonar-router](https://github.com/Polycentric-Labs/sonar-router). `route_integration` degrades gracefully to a safe default if sonar-router is absent.
- **superpowers:dispatching-parallel-agents** / **subagent-driven-development** — for the parallel harvest (Phase 1) and the 3× distinct validators (Phase 4).

## What this skill is NOT

- **Not a one-shot report** — that's deep-research. labcoat is multi-round and gated.
- **Not a doc-refresher** — that's research-resync. labcoat does the rigorous *first* pass and feeds research-resync.
- **Not a fact source** — the fleet generates ideas; only Phase 3 primary-source checks produce facts.
- **Not autonomous by default** — the interactive pipeline stops and asks at every gate; it never auto-fans-out, auto-spends, or auto-writes-to-memory. (The opt-in **Tier-2 durable orchestrator** IS the autonomous mode — see §"Durable autonomy" — and even it keeps TOLERANCE a hard ceiling + the per-loop option menu.)
- **Not a hardcoded model list** — it checks OpenRouter live and asks which models to use each run.

## Cross-references

Everything under `references/` is listed here — nothing in that directory is orphaned.

**Method + doctrine**
- Anti-hallucination rules + F1 case study: `references/anti-hallucination.md`
- **Provenance for every measured number** (scope · harness · repro command · honest limit · what is NOT verifiable from a clone): `references/measured-results.md`
- North star (governing personality) + honesty stake: `references/north-star.md`
- Which of the three research skills to use (labcoat vs research-resync vs deep-research): `references/research-skill-router.md`
- Durable orchestrator host (Tier-2 shell spec + bring-up smoke checklist): `references/orchestrator-host.md`
- Model provider risk cards (gov-adjacent-safe inputs): `references/model-risk-cards.md`
- Output templates: `references/output-templates/{decomposition,research-stream,verification-ledger,validation-record,ranked-synthesis}.md`
- Seed source list: `references/good-sources.md`

**Frozen pre-registrations (the honesty record — read these first if you are auditing a claim)**
- `references/n2-crosslit-prereg.md` — committed **BEFORE** the N2 cross-literature run to lock every knob, with pre-committed PASS/VOID/KILL semantics and an explicit anti-rescue rule (no config-relaxation run can upgrade the verdict). The run then returned a **KILL**, and it was published as one.
- `references/n2-crosslit-optionC-prereg.md` — the Option-C gate-discrimination pre-registration; its own decision rule returned **INCONCLUSIVE (underpowered)**, and that is what is reported.

**Operator runbooks (how to reproduce the live claims)**
- `references/n1-live-runbook.md` — the live N1 adapter (SPECTER2 + faiss index) bring-up.
- `references/n1-openalex-runbook.md` — the OpenAlex ~25k-work deep-corpus build behind the N1 AUROC result.
- `references/n1-offdist-roc-runbook.md` — the off-distribution **ROC harness** that produced the measured AUROC 0.889 [0.874, 0.904].
- `references/n2-live-runbook.md` — the N2 gap/whitespace channels (free path; no ML extras needed).
- `references/n3-live-runbook.md` — the N3 combinatorial propose→judge→ground slice, and the scope of the Stage-B distance CONFIRM.
- `references/spc-detector-runbook.md` — the Poisson-CUSUM yield-collapse detector (owner-gated upgrade; the K-rule stays default).
- Scripts (47), grouped. Pure cores are stdlib-only + unit-tested; operator entrypoints (marked ⚙) are live shells — NOT unit-tested, estimate-first, tolerance-gated, keys loaded in-process and never printed.

  **Core pipeline (9)**
  | Script | Role |
  |---|---|
  | `fleet.py` | parallel multi-model fleet runner (reasoning-safe defaults; no secrets in results) |
  | `redaction_gate.py` | fail-closed v2 two-class outbound gate (Class-A halt / Class-B typed placeholders) |
  | `novelty_log.py` | persistent high-signal source-domain log |
  | `route_integration.py` | sonar-router wrapper with a safe-default degrade |
  | `model_selector.py` | fleet proposal — risk cards, `gov_adjacent_safe`, Sonar-split advice |
  | `spend.py` | spend/tolerance/quota tracking + the R8 burn gate + two-line estimate |
  | `audit.py` | append-only ledger, questions log, resurface buckets |
  | `north_star.py` | the governing-ethos per-phase reflections |
  | `run_scope.py` | run-scoped ids so a shared workspace never collides across questions |

  **Durable autonomy (11)**
  | Script | Role |
  |---|---|
  | `orchestrator.py` | pure per-loop decision core (pacing + tolerance → continue/pause/stop) |
  | `orchestrator_host.py` | durable fleet-loop driver (record-before-call fsync + reservation) |
  | `pacing.py` | rate-limit / quota signals → proceed / graceful-pause / hard-stop |
  | `novelty_gate.py` | CNY saturation gate + SPC yield-collapse (CALIBRATED + ENFORCING) |
  | `novelty_store.py` | novelty seen-set / corpus / CNY-history persistence |
  | `nuclear_core.py` | Nuclear pure core (parsers, decisions, prompt builders) |
  | `nuclear.py` | ⚙ §5.2 async multi-loop autonomous engine (operator entrypoint) |
  | `loop_evolution.py` | loop-evolution next-question generator (WIRED-LIVE) |
  | `value_axis.py` | Tier-3 advisory quality axis + degeneracy detector |
  | `memory_backend.py` | pluggable MemoryBackend (SQLite bi-temporal+provenance / flat file) |
  | `smoke_host.py` | ⚙ durable-host live smoke |

  **N1 — literature-grounded novelty (10; live, ADVISORY: anti-out-of-corpus, not a novelty oracle)**
  | Script | Role |
  |---|---|
  | `n1_novelty.py` | pure RND relative-neighbor-density scorer + date-cutoff + index seam |
  | `n1_corpus.py` | arXiv corpus shell — pure Atom parse + cached fetch |
  | `n1_corpus_openalex.py` | OpenAlex corpus adapter (free, no key) — pure normalize/reconstruct |
  | `n1_embedder.py` | pinned citation-aware embedder (SPECTER2 asymmetric two-adapter) |
  | `n1_index.py` | faiss IndexFlatIP ANN index agreeing with the pure in-memory oracle |
  | `n1_build.py` | shared embed → build → calibrate → save flow (source-agnostic) |
  | `n1_distance_fn.py` | Seam-1 adapter — embedder → a `(a,b)→[0,1]` distance_fn |
  | `build_openalex_index.py` | ⚙ deep-corpus snapshot build over ~10 OpenAlex concepts |
  | `smoke_n1_live.py` | ⚙ live N1 smoke (downloads SPECTER2, builds a real index) |
  | `n1_redteam.py` | ⚙ embedder red-team / bake-off (paraphrase + jargon-inflation) |

  **N3 — combinatorial / analogical synthesis (6; live, ADVISORY: confirmed on DISTANT pairs only; sound axis human-gated)**
  | Script | Role |
  |---|---|
  | `combinatorial.py` | pure MAP-Elites archive + multiplicative creativity + proposer⊥judge |
  | `combine_live.py` | ⚙ the live propose → N1-novelty → judge → ground loop |
  | `stage_a.py` | pure Stage-A measurement core (cite-or-fail prior-art, blinding, attribution) |
  | `stage_a_measure.py` | ⚙ Stage-A live machinery-attribution + ruler-validity run |
  | `stage_b.py` | pure Stage-B core (dual-leg prior-art, soundness panel, cluster-robust stats) |
  | `stage_b_measure.py` | ⚙ Stage-B live powered measurement run |

  **N2 — gap / whitespace channels (7; live, HONEST NEGATIVE on the count-ABC channel)**
  | Script | Role |
  |---|---|
  | `gap_channels.py` | pure ABC + future-work + contradiction → reconciliation, PPMI-context + hub-exclusion |
  | `gaps_live.py` | ⚙ live gap channels over a real corpus (free stdlib path) |
  | `n2_extract_llm.py` | LLM-tagged extraction — pure prompt/parse/ground + injected-brain shell |
  | `pubmed_adapter.py` | PubMed/MEDLINE E-utilities adapter (free; XXE/entity-expansion hardened) |
  | `n2_crosslit.py` | answer-blind cross-literature ABC pipeline over a PubMed/MeSH corpus |
  | `n2_crosslit_measure.py` | pure known-answer (Swanson) measurement → VOID/KILL/PASS verdict |
  | `n2_feasibility.py` | pure Phase-0 feasibility probe — can a sub-corpus carry the bridge before spend |

  **Measurement / statistics cores (4; pure, stdlib only — never scipy/numpy)**
  | Script | Role |
  |---|---|
  | `roc.py` | pure OOD evaluation — AUROC, FPR@TPR95, stratified-bootstrap CIs |
  | `n1_offdist_roc.py` | ⚙ the live off-distribution ROC harness (calib/test split, field-stratified) |
  | `spc.py` | pure count-data Poisson-CUSUM yield-collapse detector (owner-gated upgrade; the K-rule stays default) |
  | `enrichment_stats.py` | pure size-stratified empirical-null percentile + exact binomial (Clopper-Pearson) enrichment |
- Tests: `tests/` — `pip install -r requirements.txt -r requirements-dev.txt` then `python -m pytest tests/ -q` from the skill root (**577 tests**; 570 passed / 7 skipped without the optional `requirements-n1.txt` ML extras — the skips are the live-N1 adapter tests). `pytest-asyncio` is required, not optional: two tests are `async`.
- Reference docs: `references/` — the method/doctrine docs, the **frozen pre-registrations**, and the per-axis operator runbooks. See §"Cross-references" above for the full annotated list.
- Companion skill (per-query routing): [`sonar-router`](https://github.com/Polycentric-Labs/sonar-router)

## Validation

1. **Static:** `python -c "import yaml; yaml.safe_load(open('SKILL.md').read().split('---')[1])"` — frontmatter parses as valid YAML.
2. **Runtime:** invoke a real net-new investigation; observe that each phase stops at its gate, that every proper noun in the synthesis traces to a Phase-3 verification record, and that the redaction gate runs on every outbound prompt.
