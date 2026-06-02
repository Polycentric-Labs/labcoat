# polycentric-labcoat v2 — remote MCP plan (SPECCED, NOT BUILT)

> **Status: FUTURE / v2. Nothing in this doc is built.** v1 is the skill + the standalone Python fleet runner
> (`scripts/fleet.py` et al.) driven by `SKILL.md`. This is the design for a later cross-platform wrapper.
> Build only after v1 has been exercised on real investigations and the public-repo decision is made (with Allen's approval).

## The idea

Wrap the **already-built, provider-agnostic** `fleet.py` runner (and the verification primitives) as a **remote HTTP MCP server** — call it `labcoat-fleet` — published from a **public repo**. The fleet runner was deliberately shaped as a pure library (no CLI, env-only key, structured 7-key results) precisely so a v2 MCP server is a thin wrapper, not a rewrite.

## Why an MCP server (the cross-platform reach)

MCP is the universal connector. A single `labcoat-fleet` MCP server becomes callable from essentially every agentic surface:

- **Claude** (Claude Code, Desktop, Cowork)
- **ChatGPT** (Developer Mode MCP)
- **Cursor**, **VS Code** (Copilot/agent), **Windsurf**
- **Codex**, **Gemini CLI**

So the same hardened multi-model fan-out + verification primitives Allen built for Claude become reusable from any of those clients without re-implementation.

**Caveat — Perplexity:** Perplexity has **no general MCP client** (its MCP support is scoped to Spaces, not a general tool-calling client). So the v2 server reaches Claude/ChatGPT/Cursor/VS Code/Windsurf/Codex/Gemini-CLI, but *not* Perplexity as a host. Don't claim universal coverage.

**Agent Skills Standard angle:** the `SKILL.md` itself is portable too — the Agent Skills Standard lets a single SKILL.md run on Claude Code + Codex + Gemini CLI. So v2 has two distribution vectors: the MCP server (the fleet/verification *engine*) and the skill (the *orchestration*).

## The hard design constraint — keep orchestration in the skill

A single MCP **tool call is atomic** — it cannot stop mid-call to ask the user "approve this fleet?", "approve this $4 spend?", "review this verification ledger?". The whole value of v1 is the **per-phase STOP-AND-ASK gate**, and that interactivity lives in the *agent loop*, not in a tool.

Therefore v2 splits the surface:

- **The MCP server exposes PRIMITIVES** — the mechanical, non-interactive pieces:
  - `run_fleet` (fan a prompt across N models → the 7-key result dicts)
  - `list_models` (live OpenRouter catalogue)
  - `redaction_scan` / `redaction_assert` (the fail-closed gate — labels+offsets only, never the value)
  - `route_query` (the sonar-router verdict)
  - possibly thin verification helpers (e.g. a `gh api` / NVD / arXiv check wrapper)
- **The full per-phase orchestration stays in the skill** (`SKILL.md`) — the gates, the user approvals, the cost confirmations, the 3× validation choreography. The host agent drives the phases and *calls* the MCP primitives at the mechanical steps.

This keeps the gated, ask-at-every-step rigor (the differentiator) intact while making the engine reusable everywhere.

## Prior art — and the real differentiator

Multi-model fan-out MCP servers *reportedly* already exist — the names below are model-claimed and UNVERIFIED (confirm each against a primary source via a Phase-3 pass before relying on them): e.g. Proxima, the Pal MCP, "roundtable"-style aggregators. **"Call many models at once" is not novel and is not the pitch.** The differentiator is the **rigor**: the hard-skeptic web-grounded verification (the F1 anti-hallucination spine), the 3× adversarial validation, the per-phase user gates, the ruthless ranking with per-item evidence, and the fail-closed redaction. The market is full of "ask five models"; it is thin on "disprove what the five models told you before you believe any of it." That's the moat — verification + validation, not breadth.

> Treat the prior-art list above as *unverified pending a Phase-3 pass* — when v2 is actually scoped, run labcoat on itself: confirm each named project (Proxima / Pal MCP / roundtable) against its primary source before relying on the comparison.

## Security posture (carry forward from v1 + the MCP standard)

- **Env-only key** — `OPENROUTER_API_KEY` from the environment, never in code/args/logs (already true in `fleet.py`).
- **Redaction gate on inputs** — `redaction_assert` runs fail-closed before any prompt leaves the server.
- **MCP integration standard** — if you self-host the container, it should go through a secrets-management pattern (e.g. a credential sidecar or a secret store); no plaintext keys, no `--env-file` from an unencrypted secrets path.
- **Public repo** — code is public; secrets never are. Standard pre-publish gate (no key shapes, no absolute paths) applies.

## Open questions for when v2 is scoped

- Transport: streamable-HTTP vs SSE; auth model for a remote (multi-client) server.
- Whether verification helpers belong in the MCP at all, or stay agent-side (they need web access the host may already have).
- Rate-limit / cost-guard at the server boundary (an R8-style cap independent of any one client).
- Distribution: registry listing vs self-host-only; license (MIT, matching v1).

---

**Again: v2. Not built. v1 = the skill + the Python runner.** This file is the design intent so a future build doesn't start from a blank page.
