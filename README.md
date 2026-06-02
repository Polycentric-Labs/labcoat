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

## Components

| Path | Role |
|---|---|
| `SKILL.md` | The 6-phase orchestration, the gates, the anti-hallucination rules |
| `scripts/fleet.py` | Standalone parallel multi-model fleet runner with reasoning-model-safe defaults (no secrets in code) |
| `scripts/redaction_gate.py` | Fail-closed sensitive-data gate for outbound prompts (findings carry offsets, never the secret) |
| `scripts/novelty_log.py` | Persistent high-signal source-domain log |
| `scripts/route_integration.py` | Wrapper over a query-routing classifier with a safe-default degrade; optionally calls the [`sonar-router`](https://github.com/Polycentric-Labs/sonar-router) companion — degrades gracefully if absent |
| `references/anti-hallucination.md` | The R-1..R-5 rules + the case study |
| `references/output-templates/` | Standardized doc shapes for each phase |
| `tests/` | `python -m pytest tests/ -q` |

## Use

**As a Claude Code skill:** place the folder under your skills directory (e.g. symlink/junction it to `~/.claude/skills/polycentric-labcoat`) and invoke `/polycentric-labcoat` or ask for "rigorous research" / "investigate X with the fleet."

**The fleet runner standalone:**
```bash
pip install -r requirements.txt        # httpx
export OPENROUTER_API_KEY=...           # env only — never hardcode, never log
python -m pytest tests/ -q
```
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

## License

MIT — see [LICENSE](LICENSE).

## AI assistance

This project was developed alongside AI platforms.

Models used: Claude Opus 4.6, Claude Opus 4.7, Sonar Deep Research
