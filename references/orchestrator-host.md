# Orchestrator host — the durable Tier-2 shell (operator spec)

The labcoat durable orchestrator is a **functional core + imperative shell**. The pure decision core
(`scripts/orchestrator.py`, `scripts/pacing.py`, the `scripts/spend.py` reservation) is unit-tested and
deterministic. THIS doc specs the thin **imperative shell** — the live Agent-SDK host + Windows-Service wrapper.
It is validated by a one-time bring-up **smoke checklist**, not unit tests.

## Guarantee
**At-least-once + application idempotency** (no durable-execution engine does better; the OpenRouter gateway has
no request dedup). The cost backstop is **pessimistic spend reservation**: reserve the estimate before the call,
release only on a confirmed result, so a crash leaves the reservation standing.

## Auth (resolved by the Tier-2 gate research)
- Run the brain via the **Agent SDK (Python)** or CLI `--bare -p`, authenticated **only** from `ANTHROPIC_API_KEY`
  in the service environment (file-to-file from `%USERPROFILE%\.secrets\`, never echoed). Read fresh from the
  env at each startup; `setx` / service env persists in the Registry → survives reboot.
- Do **NOT** use `CLAUDE_CODE_OAUTH_TOKEN` (it expires; `--bare` ignores it — the silent-expiry bug is
  structurally avoided). Do **NOT** rely on `%USERPROFILE%\.claude\.credentials.json` under Session 0. Desktop /
  cloud sessions are OAuth-only → must use the CLI/SDK.

## Per-loop wiring (the shell)
1. `plan_resume(audit.read_ledger(path))` → the re-drive set (skip `complete`, re-drive `known-incomplete` /
   `unavailable`, never `deterministic-fail`).
2. For each re-drive query: `redaction_gate.redact(q)` (hard_block → halt; recommend_stop → pause) →
   `Tracker.reserve(est)` → `audit.append_ledger(intent, fsync=True)` → `fleet.run_fleet(..., capture_dir=)` →
   on result: `Tracker.release(est)` + `add_openrouter(actual)` + `audit.append_ledger(result_record)`.
3. Feed the response's rate-limit signals to `pacing.pacing_decision`; compute `would_breach` via
   `spend.would_next_loop_breach` on the reserved-aware total; call `loop_decision` →
   **continue / pause (`Monitor` sleep `resume_after_s`, ramp via `pacing.ramp_after_idle`) / stop**.

## Host
- Windows Service via NSSM, or Task Scheduler `ONSTART` with `/ru System`. The Agent-SDK `Monitor` primitive
  drives the poll-loop. Set explicit `maxTurns` + per-task timeouts (Session 0 receives no console signals).

## Bring-up SMOKE CHECKLIST (run once; NOT unit tests)
1. `ANTHROPIC_API_KEY` resolves under the service account **after a reboot** (Registry-persisted env).
2. **Reboot-resume dry-run:** kill the host mid-loop, restart, confirm `plan_resume` re-drives ONLY the
   incomplete queries (none of the `complete` ones).
3. The five **Session 0** gotchas: a writable `CLAUDE_CONFIG_DIR` / project dir under LocalSystem; `claude` on
   the service PATH; the Task-Scheduler privilege can read the key env value; `maxTurns` + timeouts set; env-var
   precedence when set at multiple Windows levels.

## Built on top of this host — the §5.2 Nuclear engine
`scripts/nuclear.py` is the autonomous *multi-loop* engine that drives this host's `run_loop` with an async
Agent-SDK brain (decompose → fleet → hard-skeptic verify → synthesize), plus the novelty seen-set/corpus
persistence (`novelty_store`) and the live `RateLimitEvent`/`ResultMessage` → `pacing` wiring. Its pure core
(`nuclear_core`, the `spend.quota_signals`/`requires_explicit_burn` gates) is unit-tested; the live `run` path
is operator-gated (estimate-first + TOLERANCE + the R8 burn gate) and smoke-validated. See SKILL.md
§"Durable autonomy". The research-gated novelty gate is built (`novelty_gate`, WARN-only until calibrated).

## Out of scope (later)
The DBOS/Postgres managed-durability upgrade (the append-only ledger is the v1 substrate). (The value-aware
Tier-3 novelty engine + the SQLite `MemoryBackend` + the degeneracy detector are now BUILT — advisory / WARN-only
until calibrated on a recorded run; see SKILL.md §"Durable autonomy".)
