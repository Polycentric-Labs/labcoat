# Research-skill router — which of the three to use

> A standalone decision rule for choosing among the three research skills. Pointed at from
> `SKILL.md`. They COMPOSE; they do not overlap. Keep this in sync with the SKILL.md comparison table.

## The 4-line decision rule (copy-pasteable)

1. **Need a doc you already trust kept FRESH on a cadence?** → `research-resync` (or a variant).
2. **Investigating something NET-NEW where a wrong fact would be costly** (novel? exists? real state of the art? build/publish/pursue?) → `polycentric-labcoat` (this skill).
3. **Just want a quick one-shot cited report**, no multi-round skeptic ceremony → `deep-research`.
4. **A single fact you can verify in one call** (does `foo/bar` exist? its star count?) → `gh api` / `perplexity_ask`; consult `sonar-router` for the right tool.

## The three skills

| Skill | Owner | Job | Interaction model | Models |
|---|---|---|---|---|
| **deep-research** | builtin/plugin | one-shot cited report | runs autonomously → report | Claude + web search |
| **polycentric-labcoat** | this skill (MIT) | net-new, multi-round, hard-skeptic, 3×-validated investigation | **STOP-AND-ASK at every gate**; redaction-approval before any outbound prompt | **full OpenRouter fleet** (Gemini/GPT/Grok/DeepSeek) + web grounding |
| **research-resync** (×5) | companion | maintain an existing synthesis doc; detect decay | scheduled/cadence | re-runs the doc's original streams |

## How they compose (the pipeline)

```
polycentric-labcoat  ──Phase-5 synthesis doc──►  research-resync (stream)  ──cadence──►  re-run → semantic-diff → flag decay
   (rigorous FIRST pass)                              (keeps it FRESH)                          │
        ▲                                                                                       │
        └───────────────── when resync flags MATERIAL decay, re-run labcoat for a fresh pass ◄──┘
```

- **labcoat → research-resync:** labcoat's Phase 6 offers to register its synthesis as a research-resync
  *stream* (per-project YAML under `~/.claude/research/<project>/`). labcoat does the rigorous first pass;
  research-resync maintains it. This is the composition seam.
- **labcoat → deep-research (optional):** labcoat MAY *call* deep-research as a fast grounding sub-pass
  if it wants a quick cited report mid-investigation — as a CALLER, never by absorbing it.
- **labcoat's Phase 0 redundancy check:** if a doc already exists that research-resync should refresh
  instead of investigating cold, labcoat says so and stops. (Don't point research-resync at a question
  that was never investigated — investigate with labcoat first, then hand off.)

## Why NOT merge them (the decision, 2026-06-01)

- **deep-research is builtin (not part of this suite)** — it's a plugin skill. Folding it in means forking
  (maintenance + license burden) or depending (fragile). labcoat is MIT/Polycentric-owned; keep it clean.
- **Conflicting interaction models** — deep-research runs autonomously to a report; labcoat's whole value is
  the per-gate STOP-AND-ASK + redaction approval + 3× validation. Absorbing deep-research's autonomy would
  dilute the exact discipline that caught the F1 fabrications.
- **Different model substrate** — labcoat's differentiator is multi-vendor fleet *divergence*; deep-research is
  Claude+web. Merging blurs it.
- **Leaf-only / YAGNI** — three small, crisply-scoped, description-gated skills beat one mega-skill. Compose, don't merge.

## Which research-resync variant (solo-Windows setup)

- **`research-resync` (base)** or **`research-resync-routine`** (Anthropic-cloud-scheduled; survives laptop-close)
  for the durable cadence.
- Skip **`-gha`** (needs the doc in a public repo) and **`-librarian`** (event-driven; still a blueprint) unless
  a specific doc warrants them.
