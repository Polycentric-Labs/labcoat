# Decomposition — <TopicName>

> Phase 0 output. Fill this in BEFORE any outbound prompt. Copy into `<project>/<TopicName>/_internal/`.
> Gate: the user signs off on scope, depth, redaction, and cost before anything fans out.

**Date:** <YYYY-MM-DD> · **Requested by:** <who> · **One-line ask:** <the question as asked>

## The real question
<What is actually being asked, underneath the asked phrasing? State it plainly.>

## Critical-framing pushback
<Challenge the premise before spending. Address each:>
- **Is this one investigation or several?** <split if so>
- **Has it already been done?** <does a doc exist to refresh via research-resync instead? cite it>
- **Is the framing leading / loaded?** <reframe if so>
- **What would make this a waste of money?** <name the failure mode upfront>

## Sub-questions (non-overlapping)
1. <sub-question — owns one research-stream file>
2. <sub-question>
3. <sub-question>

## Relevant past research pulled
<Prior pass-notes / memory / sibling-repo docs already covering part of this. Cite paths. "None found" is a valid, useful answer.>

## Redaction decisions
- **Must NOT leave the machine:** <client names / internal paths / sensitive topics — the human list>
- **Programmatic gate:** `redaction_gate.assert_clean(prompt)` run on every outbound prompt — <confirmed / pending>
- **3× human verify of the assembled prompt:** <confirmed clean / notes>

## Depth tier + cost
- **Recommended tier:** <Quick / Standard / Deep / Exhaustive> — <why>
- **Fleet (provisional):** <models; floor = Gemini + GPT + Grok + DeepSeek>
- **Cost estimate:** <~$X> · **R8 >$25 gate:** <n/a | needs explicit OK> · **Exhaustive "yes, burn it":** <n/a | obtained>

## Gate
- [ ] User approved scope, decomposition, depth tier, redaction list, and cost.
