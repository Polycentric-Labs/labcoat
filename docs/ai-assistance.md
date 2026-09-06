# AI assistance in Labcoat's development

Last updated: 2026-09-06. Disclosure level: **ai-assisted** (human work completed
with AI assistance and reviewed by the maintainer before it ships).

This page records how AI tools take part in building Labcoat. It covers the
development process only.

## What the maintainer does

- Sets scope, priorities and design, and decides what ships and when.
- Reviews every change before it lands and performs every publish step
  personally (commits, tags and merges).
- Writes the security dispositions, licence decisions and public statements.

## Where AI tools help

| Role in the development workflow | Tools |
|---|---|
| Coding assistant (implementation, tests, refactors, drafting docs) | Claude Code |
| Research and source discovery | Sonar Deep Research (Perplexity) |

The list changes as tools enter or leave the workflow; the date at the top is the
last revision. Custom infrastructure and integrations for each tool were built
in-house.

Labcoat is also an AI system in its own right, not only a project built with AI
help: its fleet runner calls a live, multi-vendor set of hosted models at
runtime as the product's own feature. Per-provider data-governance notes for
that runtime use are in
[`references/model-risk-cards.md`](../references/model-risk-cards.md).

## What is excluded

- No AI identity appears in git metadata. Commits are authored and signed by the
  maintainer, and there are no `Co-authored-by` trailers naming AI tools.
- No autonomous agent opens issues or pull requests, and none publishes anything.
- No AI-drafted text ships unread. Every document, changelog entry and release
  note is reviewed and edited by the maintainer first.

## Contributors

External contributors may use AI tools under the rules in
[`CONTRIBUTING.md`](../CONTRIBUTING.md): the contributor is the author and is
accountable for the change; significant AI assistance is disclosed in the pull
request description or with an `Assisted-by:` commit trailer; `Co-authored-by`
trailers naming AI tools are not accepted.

## Organisation policy

Polycentric Labs maintains one AI-assistance policy shared by its projects,
published at [polycentriclabs.com/ai-policy](https://polycentriclabs.com/ai-policy)
and mirrored in the organisation's GitHub profile as
[AI_POLICY.md](https://github.com/Polycentric-Labs/.github/blob/main/AI_POLICY.md).
This page is the project-level record under that policy.
