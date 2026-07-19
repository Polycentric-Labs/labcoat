#!/usr/bin/env python3
"""verify_prereg — hash-bind + verify the N2 cross-lit pre-registration provenance chain.

Binds each pre-registration to its signed freeze commit -> governed run -> honest outcome, and lets anyone
re-verify the binding. Pure stdlib. Two modes, auto-detected per freeze commit:
  * commit PRESENT in this clone  -> full verify (recompute content SHA-256 + author/committer dates + signed-status).
  * commit ABSENT (e.g. the public mirror, whose history was re-synced) -> SKIP with a note; the recorded
    content SHA-256 stands as an auditable claim, and the current working-tree file is still verified.

Freeze timestamp = git AUTHOR date. The commit HASHES + committer-dates are 2026-07-18 repo-split artifacts
(history rewrite preserved author-dates + re-signed); never treat a hash as the original or a committer-date as
a freeze time. See references/prereg-manifest.md for the human view. [labcoat honesty stake]
"""
import argparse
import hashlib
import json
import pathlib
import subprocess


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def repo_root() -> str:
    """Absolute path of the enclosing git repo (falls back to this file's grandparent)."""
    here = str(pathlib.Path(__file__).resolve().parent)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=here, capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip()
    return str(pathlib.Path(__file__).resolve().parent.parent)


def git_file_at(commit: str, path: str, root: str | None = None) -> bytes | None:
    """Raw bytes of `path` as of `commit`, or None if the commit/path is absent in this clone."""
    root = root or repo_root()
    r = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def git_commit_meta(commit: str, root: str | None = None) -> dict | None:
    """{'author_utc','committer_utc','signed'} for `commit`, or None if absent in this clone.

    author_utc = the TRUE freeze time (preserved through the repo split). committer_utc = split artifact.
    signed = a good signature is present here (%G? in G/U); False may just mean the signing key is not imported.
    """
    root = root or repo_root()
    r = subprocess.run(
        ["git", "log", "--format=%aI%n%cI%n%G?", "-1", commit], cwd=root, capture_output=True, text=True
    )
    if r.returncode != 0:
        return None
    lines = r.stdout.strip().split("\n")
    if len(lines) < 3:
        return None
    return {"author_utc": lines[0], "committer_utc": lines[1], "signed": lines[2] in ("G", "U")}


def load_manifest(path: str) -> dict:
    """Parse the manifest JSON."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# refresh — fill machine-computed fields from git (curated fields untouched)
# ---------------------------------------------------------------------------
def refresh(manifest: dict, root: str | None = None) -> dict:
    """Populate computed fields (SHAs, author/committer dates, signed) from git. Mutates + returns manifest.

    Content SHA-256 is always taken from the git BLOB (git show <ref>:<path>) — LF-normalised, so the value is
    reproducible across platforms and identical in the re-synced mirror. Curated fields (governed_run, outcome,
    measured_ref, titles, drift_note, provenance_note) are left exactly as authored.
    """
    root = root or repo_root()
    for pf in manifest["prereg_files"]:
        f = pf["file"]
        head_blob = git_file_at("HEAD", f, root)
        pf["current_sha256"] = sha256_hex(head_blob) if head_blob is not None else None
        last_frozen = None
        for ev in pf["events"]:
            blob = git_file_at(ev["freeze_commit"], f, root)
            if blob is not None:
                ev["content_sha256"] = sha256_hex(blob)
                last_frozen = ev["content_sha256"]
            meta = git_commit_meta(ev["freeze_commit"], root)
            if meta is not None:
                ev["freeze_author_utc"] = meta["author_utc"]
                ev["committer_utc"] = meta["committer_utc"]
                ev["signed"] = meta["signed"]
        pf["frozen_sha256"] = last_frozen  # SHA of the file as of its LAST freeze commit
    return manifest


# ---------------------------------------------------------------------------
# render — the human-readable Markdown view (generated; never hand-edited)
# ---------------------------------------------------------------------------
def _current_vs_frozen(pf: dict) -> str:
    cur, frozen = pf.get("current_sha256"), pf.get("frozen_sha256")
    if cur is None or frozen is None:
        return "current-vs-frozen relationship: unknown."
    if cur == frozen:
        return "current MATCHES the last frozen state."
    return "current DIFFERS from the last frozen state (see drift note below)."


def render_markdown(manifest: dict) -> str:
    """Deterministic, LF-only Markdown view of the manifest. Byte-stable so the md-sync check is reliable."""
    L = []
    L.append("# Pre-registration hash-bind manifest")
    L.append("")
    L.append("> Generated from `references/prereg-manifest.json` by `scripts/verify_prereg.py` — do NOT hand-edit.")
    L.append(f"> Last refreshed: {manifest.get('generated', '?')}.")
    L.append("")
    L.append(manifest.get("provenance_note", "").strip())
    L.append("")
    L.append("## How to verify")
    L.append("")
    L.append("Every SHA-256 below is of the git **blob** (LF-normalised), so it reproduces on any platform:")
    L.append("")
    L.append("```")
    L.append("git show <freeze_commit>:<file> | sha256sum   # a frozen pre-registration")
    L.append("git show HEAD:<file>            | sha256sum   # the current (published) content")
    L.append("python scripts/verify_prereg.py --check       # recompute + check everything")
    L.append("```")
    L.append("")
    L.append("Freeze time = git **author** date. The commit **hashes** and **committer** dates are 2026-07-18")
    L.append("repo-split artifacts (history rewrite preserved author-dates + re-signed); a hash is NOT the original")
    L.append("pre-split commit, and 2026-07-19 is NOT a freeze time. Where a freeze commit is absent from a clone")
    L.append("(e.g. the re-synced mirror) its content SHA-256 stands as an auditable claim, owner-verifiable.")
    L.append("")
    for pf in manifest["prereg_files"]:
        L.append(f"## `{pf['file']}`")
        L.append("")
        L.append(f"- current blob SHA-256: `{pf.get('current_sha256')}`")
        L.append(f"- last-frozen blob SHA-256: `{pf.get('frozen_sha256')}` — {_current_vs_frozen(pf)}")
        note = (pf.get("drift_note") or "").strip()
        if note:
            L.append(f"- drift: {note}")
        L.append("")
        L.append("| event | freeze commit (post-split) | author-date (freeze) | signed | content SHA-256 | governed run | honest outcome |")
        L.append("|---|---|---|---|---|---|---|")
        for ev in pf["events"]:
            L.append(
                f"| {ev['id']} | `{ev['freeze_commit']}` | {ev.get('freeze_author_utc')} | "
                f"{ev.get('signed')} | `{ev.get('content_sha256')}` | {ev['governed_run']} | {ev['outcome']} |"
            )
        L.append("")
    return "\n".join(L).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# verify — recompute from git + assert the manifest matches (two-mode)
# ---------------------------------------------------------------------------
def verify(manifest: dict, root: str | None = None, md_path: str | None = None) -> dict:
    """Recompute SHAs + git metadata and assert they match the manifest.

    FAIL (fatal) only on a real mismatch: a current-blob SHA, a present freeze-commit content SHA, an author/
    committer date, or an MD drift. A freeze commit absent from this clone -> SKIP (its SHA is an auditable claim).
    Signature status is environment-dependent (key may not be imported) -> mismatch is SKIP, never FAIL.
    """
    root = root or repo_root()
    checks: list[dict] = []

    def add(name, status, detail=""):
        checks.append({"name": name, "status": status, "detail": detail})

    for pf in manifest["prereg_files"]:
        f = pf["file"]
        head_blob = git_file_at("HEAD", f, root)
        if head_blob is None:
            add(f"current:{f}", "FAIL", "HEAD blob not found")
        else:
            got = sha256_hex(head_blob)
            if got == pf.get("current_sha256"):
                add(f"current:{f}", "PASS", got)
            else:
                add(f"current:{f}", "FAIL", f"expected {pf.get('current_sha256')} got {got}")
        for ev in pf["events"]:
            c = ev["freeze_commit"]
            blob = git_file_at(c, f, root)
            if blob is None:
                add(f"frozen:{ev['id']}", "SKIP", "freeze commit not in this clone; content_sha256 is an auditable claim")
                continue
            got = sha256_hex(blob)
            if got == ev.get("content_sha256"):
                add(f"frozen:{ev['id']}", "PASS", got)
            else:
                add(f"frozen:{ev['id']}", "FAIL", f"expected {ev.get('content_sha256')} got {got}")
            meta = git_commit_meta(c, root)
            if meta is not None:
                if meta["author_utc"] == ev.get("freeze_author_utc") and meta["committer_utc"] == ev.get("committer_utc"):
                    add(f"meta:{ev['id']}", "PASS", meta["author_utc"])
                else:
                    add(f"meta:{ev['id']}", "FAIL", "author/committer date differs from manifest")
                if meta["signed"] == ev.get("signed"):
                    add(f"sig:{ev['id']}", "PASS", f"signed={meta['signed']}")
                else:
                    add(f"sig:{ev['id']}", "SKIP", f"signature status differs here ({meta['signed']}); signing key may not be imported")

    if md_path is not None:
        want = render_markdown(manifest)
        try:
            with open(md_path, encoding="utf-8") as fh:  # universal-newline read normalises CRLF -> LF
                have = fh.read()
        except FileNotFoundError:
            have = None
        add("md-sync", "PASS" if have == want else "FAIL", md_path if have == want else "generated MD != on-disk MD (run --emit-md)")

    return {"ok": all(c["status"] != "FAIL" for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _write_lf(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify / refresh the pre-registration hash-bind manifest.")
    ap.add_argument("--manifest", default="references/prereg-manifest.json")
    ap.add_argument("--md", default="references/prereg-manifest.md")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--check", action="store_true", help="recompute + verify (default); exit 1 on any FAIL")
    grp.add_argument("--refresh", action="store_true", help="fill computed fields from git + rewrite JSON and MD")
    grp.add_argument("--emit-md", action="store_true", help="regenerate the MD view from the JSON")
    args = ap.parse_args(argv)
    root = repo_root()
    manifest = load_manifest(args.manifest)

    if args.refresh:
        refresh(manifest, root)
        _write_lf(args.manifest, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        _write_lf(args.md, render_markdown(manifest))
        print(f"refreshed {args.manifest} + {args.md}")
        return 0
    if args.emit_md:
        _write_lf(args.md, render_markdown(manifest))
        print(f"wrote {args.md}")
        return 0

    report = verify(manifest, root, md_path=args.md)
    for c in report["checks"]:
        print(f"{c['status']:4} {c['name']}  {c['detail']}")
    print("OK" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
