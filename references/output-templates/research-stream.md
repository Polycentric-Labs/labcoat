# Research stream — <sub-question short name>

> Phase 1/2 output. ONE non-overlapping sub-question per file. Write-as-you-go into `<project>/<TopicName>/_internal/audit/`.
> Raw findings + PROVISIONAL sources only — nothing here is verified yet (that is Phase 3).

**Sub-question:** <the single question this stream answers>
**Owner:** <agent / model> · **Date:** <YYYY-MM-DD>

## Internal / harvested context (Phase 1)
<What local/cheap grounding already exists: repo reads, prior docs, things we have access to without spending.>

## Fleet outputs (Phase 2 — raw, per model)
> Route via `route_integration.route_query` first. Resolve real model ids live; report substitutions.

### <model id (as actually used)>
<raw output>

### <model id>
<raw output>

## Cross-model agreement / disagreement
- **Agree:** <points multiple models converged on>
- **Disagree:** <points they split on — these are Phase-3 verification targets, not noise>
- **Only one model said:** <single-source claims — high suspicion>

## Provisional proper nouns to verify in Phase 3
> Every CVE/advisory ID, arXiv ID, repo, version, citation, tool name, stat the models produced. NONE trusted yet.
- <claim / proper noun> — <which model(s) said it>
- <claim / proper noun>
