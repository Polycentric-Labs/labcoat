# Pre-registration hash-bind manifest

> Generated from `references/prereg-manifest.json` by `scripts/verify_prereg.py` — do NOT hand-edit.
> Last refreshed: 2026-07-19.

Each pre-registration below was frozen and signed BEFORE its run (author-dates shown). The honesty stake: no post-hoc tuning; any change after seeing results converts a run to exploratory, not a PASS. On 2026-07-18 the labcoat subtree was split into this standalone repo via a history rewrite, which preserved author-dates + commit messages and re-signed every commit -- so the commit HASHES are post-split and the committer-dates are 2026-07-18/19 artifacts, NOT freeze times. Each content SHA-256 is of the git blob (LF-normalised, reproducible cross-platform); the original pre-split signed commits pushed at the author-dates are the deepest timestamp anchor (owner-auditable). A file's current SHA differs from its last-frozen SHA only where noted, and only by mirror-safety redaction of private-path references -- no pre-registered knob, criterion, gold set, or statistical method changed.

## How to verify

Every SHA-256 below is of the git **blob** (LF-normalised), so it reproduces on any platform:

```
git show <freeze_commit>:<file> | sha256sum   # a frozen pre-registration
git show HEAD:<file>            | sha256sum   # the current (published) content
python scripts/verify_prereg.py --check       # recompute + check everything
```

Freeze time = git **author** date. The commit **hashes** and **committer** dates are 2026-07-18
repo-split artifacts (history rewrite preserved author-dates + re-signed); a hash is NOT the original
pre-split commit, and 2026-07-19 is NOT a freeze time. Where a freeze commit is absent from a clone
(e.g. the re-synced mirror) its content SHA-256 stands as an auditable claim, owner-verifiable.

## `references/n2-crosslit-prereg.md`

- current blob SHA-256: `84676c43f0d07f0a6b9ab7f8f179ef7b20ed0da47f925fa141959836f304df83`
- last-frozen blob SHA-256: `5ac5250283b4befbc9a629c18ab1fc02856c0f53e4acda27a6af6c910936d0db` — current DIFFERS from the last frozen state (see drift note below).
- drift: current differs from last-frozen ONLY by mirror-safety redaction of private-path references (genericized to "private working notes"); no pre-registered knob, criterion, gold set, or method changed.

| event | freeze commit (post-split) | author-date (freeze) | signed | content SHA-256 | governed run | honest outcome |
|---|---|---|---|---|---|---|
| crosslit-phase3 | `2e521967a51b6bbb6b440943f184cc7480c6076b` | 2026-07-01T23:08:39-04:00 | True | `73da4651676c1a9576efc090f5918f7d97430a1c21478a795cffdac34d13784e` | raw + specificity priorities; fish-oil<->Raynaud + Mg<->migraine; answer-blind PubMed/MeSH corpus, publication year <=1985 | KILL (fish-oil<->Raynaud, both priorities -- literature-size-confounded) / VOID (Mg<->migraine, bridge absent) |
| crosslit-as | `85c006bc1987791ca18963ef3b0bc05e0dd9e0df` | 2026-07-02T13:19:26-04:00 | True | `6054777133668e26699d35d47f73a1a3f7b2769908d0ac6cab1f27a0c85ba8d2` | association_strength (c_AC / deg_A.deg_C) + hypergeom significance gate + salton_cosine; SAME <=1985 corpus / pairs / answer-blindness as Phase-3 | NARROW gate-carried PASS, n=1 (fish-oil<->Raynaud clears the size-controlled gate; still bottom-ranked by effect size) -- reported truncation-free after Addendum 3 |
| crosslit-probe | `fa19d0de3757e349dc20c4800b80ca7185252c64` | 2026-07-02T15:13:09-04:00 | True | `7433499b4a29c94eefc6deb3267d616cf4f7bd90c8995f73755140455c2073c6` | diagnostic-only hub-relaxation sweep (C0-C3) attributing the AS residual to STRUCTURAL vs SEMANTIC; fish-oil<->Raynaud only | diagnostic-only; its premise (target VOID at C0) was superseded by the Addendum-3 re-run (target CLEARS the gate at C0) -- residual re-characterized truncation-free |
| crosslit-trunc-fix | `60d2b6954161c4bc9c0bad02cdd899fbb4b827c7` | 2026-07-02T15:40:45-04:00 | True | `a4a1c3247767a14dcacd7a591041605b345ee5b66298f2169e23e3d5e1346e2d` | add max_gaps param to measure_case + re-run the entire headline (both cases x all 4 priorities) + the Addendum-2 probe with no truncation | completeness correction (no criterion changed); FALSIFIED the Plan-4 hub-antagonism diagnosis -- the AS VOID was a 100k-gap truncation artifact, not hub exclusion (target has 67 non-hub bridges, clears the gate p=4.8e-4) |
| crosslit-optionC-ptr | `6e04e6967779fcda2937faf8a8e1c2b916f7548b` | 2026-07-02T21:49:18-04:00 | True | `5ac5250283b4befbc9a629c18ab1fc02856c0f53e4acda27a6af6c910936d0db` | n/a (pointer addendum; the Option-C run is a separate pre-registration -- see the optionC entry) | n/a -- see optionC |

## `references/n2-crosslit-optionC-prereg.md`

- current blob SHA-256: `9f4afc3fa86f6f39854d03de3ae6fe2bcc24ead0b322eabedde0a44931998eab`
- last-frozen blob SHA-256: `912d98ce004d2083cbd80604038d069296b20146f299d056582ca526667be1e4` — current DIFFERS from the last frozen state (see drift note below).
- drift: current differs from last-frozen ONLY by mirror-safety redaction of private-path references (genericized to "private working notes"); no pre-registered knob, criterion, gold set, or method changed.

| event | freeze commit (post-split) | author-date (freeze) | signed | content SHA-256 | governed run | honest outcome |
|---|---|---|---|---|---|---|
| optionC | `6e04e6967779fcda2937faf8a8e1c2b916f7548b` | 2026-07-02T21:49:18-04:00 | True | `912d98ce004d2083cbd80604038d069296b20146f299d056582ca526667be1e4` | size-band empirical-null percentile + exact binomial (Clopper-Pearson) enrichment test; owner-ratified n=3 strict-clean primary + n=5 sensitivity; answer-blind per-positive corpora | INCONCLUSIVE (underpowered -- clean time-sliced Swanson gold is scarce; only 2 strict-clean pairs survived boundary triage) + a per-pair honest negative: the n=1 gate-clearance does NOT reproduce |

## `references/divergence-prereg.md`

- current blob SHA-256: `d14f5a39b54bc99871ebf3001f4d079686fc5695aa10055c1d0bcf40f765a14a`
- last-frozen blob SHA-256: `ed74b1fe7891e680b91c95422c2bc6529e55a13cede51c348399e8015dcfe13f` — current DIFFERS from the last frozen state (see drift note below).
- drift: current differs from last-frozen ONLY by mirror-safety redaction of private-path references (genericized to "private working data"); no pre-registered knob, criterion, statistic, or endpoint changed.

| event | freeze commit (post-split) | author-date (freeze) | signed | content SHA-256 | governed run | honest outcome |
|---|---|---|---|---|---|---|
| divergence-retro | `4fa0cd031f40469c750b687d1f0f619411e58d36` | 2026-07-19T13:02:08-04:00 | True | `ed74b1fe7891e680b91c95422c2bc6529e55a13cede51c348399e8015dcfe13f` | AUROC of (D-1)/(V-1) vendor-collapsed divergence vs fabricated-vs-confirmed label (roc.py Mann-Whitney + auc_ci bootstrap); k_min=15, seed=20260719, n_boot=2000; secondary = (fabricated U misleading) vs confirmed | INCONCLUSIVE (primary n_fabricated=3 < k_min=15; secondary n=6 < 15) on 38 curated shared-referent slots. Structural finding: fabrications were mostly SOLO (single-vendor, invisible to a cross-vendor statistic), and the recovered shared-referent slots skew high-divergence across ALL labels (confirmed mean 0.807 vs fabricated 0.944) -> directionally consistent with the hypothesis but unmeasurable at n=3. Machinery validated (14 tests); the instrument accumulates forward calibration. |
