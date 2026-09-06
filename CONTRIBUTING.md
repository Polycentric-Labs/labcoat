# Contributing to Labcoat

Thanks for your interest in labcoat, the rigorous net-new research-investigation
skill for Claude Code.

## Setup

```bash
pip install -r requirements.txt -r requirements-dev.txt   # core + test deps
export OPENROUTER_API_KEY=...                              # env only: never hardcode, never log
```

`requirements-n1.txt` adds the optional live-N1 literature-index extras
(numpy, faiss-cpu, torch, transformers, adapters). It is not needed to import,
test, or run labcoat's default paths, only the live N1 adapter.

## Running the tests

```bash
python -m pytest tests/ -q
```

On the core install plus dev deps, with no N1 extras installed, the suite
passes clean: 570 passed, 7 skipped, 0 failed. The skips are live-adapter
tests, guarded to skip rather than fail when `faiss`/`torch` are absent; adding
`requirements-n1.txt` un-skips 5 of them (575 passed, 2 skipped).

## Scope

Labcoat's spine is the anti-hallucination rule set in
[`references/anti-hallucination.md`](references/anti-hallucination.md): every
fleet-produced proper noun is a claim to disprove, not a fact to relay.
Contributions that weaken a stop-and-ask gate, bypass the redaction gate on
outbound prompts, or let an unconfirmed proper noun reach a synthesis without
being quarantined are out of scope.

## Commits

Keep changes focused and describe the "why," not just the "what."

## AI-assisted contributions

You may use AI tools while contributing. Two rules apply, and they mirror the
project's own disclosure in [`docs/ai-assistance.md`](docs/ai-assistance.md):

- **You are the author.** Understand the change and be able to explain it in
  your own words; review questions are answered by you, not by a tool. Pull
  requests opened by autonomous agents are closed.
- **Disclose significant assistance.** Say so in the pull request description,
  or add an `Assisted-by: <tool>` trailer to the commit message. Do not add
  `Co-authored-by` trailers naming AI tools: they create a contributor identity
  in the repository record, and only people are contributors here.
