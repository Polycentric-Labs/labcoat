# Anti-hallucination spine (the reason this skill exists)

The fleet is an **idea generator, not a fact source.** Opinion models — even frontier ones, even several of them agreeing — invent proper nouns with total fluency and zero tells. A research method that relays a fleet model's CVE number, repo name, version string, or citation as fact will confidently ship fiction. Phase 3 exists to stop that, every time, for every proper noun.

## F1 — the case study (the receipts)

In the 2026-06-01 session that produced this skill, an **8-model fleet** was asked to surface security/research findings. Across the raw outputs it fabricated:

- **~9 CVE IDs** — well-formed `CVE-YYYY-NNNNN` strings that do not exist in NVD.
- **~6 academic citations** — including the worst-case failure mode: a **real arXiv ID paired with a completely hallucinated paper title.** The ID resolved; the title it was attached to was invented. A reader who spot-checked "is this a real arXiv ID?" would have been *reassured by the lie.*

Per-item web-grounding — `gh api` for repos, NVD for CVEs, arXiv/Semantic-Scholar for papers, `WebFetch`/Playwright for pages — **caught every single one.** Not most. Every one. The cost of the grounding pass was minutes of tool calls. The cost of skipping it would have been a synthesis full of fiction handed back as fact.

The lesson is not "those models are bad." The lesson is **structural**: opinion-model output about any proper noun is a *claim to disprove*, never a fact to relay. The rules below operationalize that.

## The rules

### R-1 — Opinion-model output is NEVER trusted for a proper noun

A CVE / security-advisory ID, an arXiv ID, a repo name, a version number, a citation, a tool/product name, or a statistic produced by a fleet model is a **claim**, never a fact, until it is **web-confirmed against a primary source.** It does not reach the user as fact before that confirmation.

The unmissable form: **a model that names a CVE is a model that may have invented that CVE.** Treat the well-formed-ness of a proper noun as *evidence of nothing* — fabrications are perfectly well-formed.

### R-2 — Every "X exists / X is novel / X says Y" gets a primary-source check

Map each claim type to its authoritative source and check it there:

| Claim type | Primary source | Tool |
|---|---|---|
| Repo / org / file exists, stars, license | GitHub | `gh api repos/<owner>/<repo>` |
| Paper exists, title, authors, year | arXiv / Semantic Scholar | `WebFetch arxiv.org/abs/<id>`; HuggingFace `paper_search` MCP |
| CVE / advisory is real + its details | NVD / vendor advisory | `WebFetch nvd.nist.gov/vuln/detail/<id>` |
| Web page says Y (static) | the page itself | `WebFetch <url>` |
| Web page says Y (JS-heavy / login-walled-public / trending) | the rendered page | Playwright / `browser_*` MCP |
| Package exists, version | the registry | `WebFetch` PyPI/npm; `gh api` |

"It's novel" is the highest-risk claim of all — it's a *negative* that the model cannot actually verify. Convert it to a positive search: try hard to find prior art (papers, repos, products). Absence-after-a-real-search is weak evidence of novelty; a model's say-so is none.

### R-3 — A dedicated FABRICATION-PURGE pass

Do not fold verification into synthesis as an afterthought. Run an explicit pass whose *stated assumption is that the fleet fabricated.* Diff every model-produced proper noun against web truth and **quarantine each one that doesn't confirm.** Default posture: guilty until a primary source proves innocent. The F1 numbers (9 + 6 fabrications in one session) are why this is a named pass and not a vibe.

### R-4 — Hard-skeptic posture: try to KILL each finding

Phase 3 is adversarial toward its *own* findings. For each surviving claim, actively argue it down:

- **Saturation** — is the space already crowded? (a "novel tool" idea dies if ten exist)
- **Prior art** — has someone published/built this? (search for it; don't assume not)
- **No demand** — even if real and novel, does anyone need it?

A finding that survives a genuine attempt to kill it has *earned* its place in the synthesis. A finding that was only ever "confirmed" was never really tested.

### R-5 — Playwright / fetch are first-class; grounding is mandatory, the tool is whatever renders the truth

`WebFetch` is the default, but it can't render every page (heavy JS, login-walled-but-public content, trending/feed pages that need a real browser). When it can't, use the Playwright / `browser_*` MCP. The rule is **grounding is non-negotiable**; the *tool* is negotiable — reach for whatever actually shows the real page. "WebFetch returned nothing" is never a reason to fall back to trusting the model; it's a reason to use a heavier renderer.

## The TRIPWIRE

**If a synthesis (Phase 5) would surface a proper noun that no Phase-3 verification record confirms — BLOCK it and flag it to the user.**

This is the hard backstop behind R-1..R-4. It does not matter how plausible the claim is, how many models agreed, or how well-formed the identifier looks. No confirming verification-ledger row → it does not appear as fact in the synthesis. The options at the tripwire are: (a) go verify it now and add the ledger row, (b) surface it explicitly as *unverified / model-claimed*, clearly labeled, or (c) drop it. Silently promoting an unverified proper noun to fact is the one failure this skill exists to prevent.

## Cross-references

- The pipeline that enforces these rules: `../SKILL.md` (Phase 3, and the gate before Phase 5).
- The ledger that records each check: `output-templates/verification-ledger.md`.
- Per-query tool routing for the grounding calls: the `sonar-router` skill.
