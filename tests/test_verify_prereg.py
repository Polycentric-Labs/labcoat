import sys, pathlib, hashlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import verify_prereg as vp


# ---------- Task 1: pure helpers ----------
def test_sha256_hex_known_vector():
    assert vp.sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_git_file_at_head_matches_worktree():
    data = vp.git_file_at("HEAD", "references/n2-crosslit-optionC-prereg.md")
    assert data is not None and b"Option C" in data


def test_git_file_at_absent_commit_returns_none():
    assert vp.git_file_at("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", "README.md") is None


def test_git_commit_meta_head_has_keys():
    m = vp.git_commit_meta("HEAD")
    assert set(m) == {"author_utc", "committer_utc", "signed"}


def test_git_commit_meta_absent_returns_none():
    assert vp.git_commit_meta("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef") is None


# ---------- Task 2: render / verify / refresh / CLI ----------
def _fixture():
    """A minimal valid manifest whose single event points at HEAD (so full-verify passes here)."""
    f = "references/n2-crosslit-optionC-prereg.md"
    body = vp.git_file_at("HEAD", f)
    meta = vp.git_commit_meta("HEAD")
    sha = vp.sha256_hex(body)
    return {
        "generated": "2026-07-19",
        "provenance_note": "note",
        "prereg_files": [{
            "file": f,
            "current_sha256": sha,
            "frozen_sha256": sha,
            "drift_note": "",
            "events": [{
                "id": "h", "title": "t", "freeze_commit": "HEAD",
                "governed_run": "g", "outcome": "o", "measured_ref": f,
                "content_sha256": sha, "freeze_author_utc": meta["author_utc"],
                "committer_utc": meta["committer_utc"], "signed": meta["signed"],
            }],
        }],
    }


def test_verify_pass_on_fixture():
    assert vp.verify(_fixture())["ok"] is True


def test_verify_fail_on_tampered_current():
    m = _fixture()
    m["prereg_files"][0]["current_sha256"] = "0" * 64
    r = vp.verify(m)
    assert r["ok"] is False and any(c["status"] == "FAIL" for c in r["checks"])


def test_verify_fail_on_tampered_content_sha():
    m = _fixture()
    m["prereg_files"][0]["events"][0]["content_sha256"] = "0" * 64
    r = vp.verify(m)
    assert r["ok"] is False


def test_verify_skip_on_absent_commit():
    m = _fixture()
    m["prereg_files"][0]["events"][0]["freeze_commit"] = "deadbeef" * 5
    r = vp.verify(m)
    # current (HEAD) still verifies -> ok True; the absent freeze commit -> SKIP, not FAIL
    assert r["ok"] is True and any(c["status"] == "SKIP" for c in r["checks"])


def test_render_markdown_deterministic_and_has_verify_block():
    m = _fixture()
    out = vp.render_markdown(m)
    assert out == vp.render_markdown(m)
    assert "How to verify" in out and "git show" in out


def test_render_markdown_drift_line_is_grammatical():
    m = _fixture()
    m["prereg_files"][0]["frozen_sha256"] = "1" * 64  # force current != frozen
    out = vp.render_markdown(m)
    assert "is DIFFERS" not in out  # the old broken phrasing
    assert "DIFFERS from the last frozen state" in out


def test_render_markdown_identical_line_is_grammatical():
    m = _fixture()  # fixture has current == frozen
    out = vp.render_markdown(m)
    assert "MATCHES the last frozen state" in out


def test_md_sync_fail_on_stale(tmp_path):
    m = _fixture()
    p = tmp_path / "manifest.md"
    p.write_text("STALE", encoding="utf-8")
    r = vp.verify(m, md_path=str(p))
    assert any(c["name"] == "md-sync" and c["status"] == "FAIL" for c in r["checks"])


def test_md_sync_pass_when_rendered(tmp_path):
    m = _fixture()
    p = tmp_path / "manifest.md"
    p.write_text(vp.render_markdown(m), encoding="utf-8")
    r = vp.verify(m, md_path=str(p))
    assert any(c["name"] == "md-sync" and c["status"] == "PASS" for c in r["checks"])


def test_refresh_fills_computed_fields():
    m = _fixture()
    # blank the computed fields
    pf = m["prereg_files"][0]
    pf["current_sha256"] = None
    pf["events"][0]["content_sha256"] = None
    pf["events"][0]["freeze_author_utc"] = None
    vp.refresh(m)
    assert pf["current_sha256"] and len(pf["current_sha256"]) == 64
    assert pf["events"][0]["content_sha256"] and pf["events"][0]["freeze_author_utc"]


def test_load_manifest_roundtrip(tmp_path):
    import json
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_fixture()), encoding="utf-8")
    assert vp.load_manifest(str(p))["generated"] == "2026-07-19"


def test_main_check_returns_zero_on_valid(tmp_path):
    import json
    m = _fixture()
    jp = tmp_path / "m.json"
    mp = tmp_path / "m.md"
    jp.write_text(json.dumps(m), encoding="utf-8")
    mp.write_text(vp.render_markdown(m), encoding="utf-8")
    assert vp.main(["--check", "--manifest", str(jp), "--md", str(mp)]) == 0


def test_main_check_returns_one_on_tamper(tmp_path):
    import json
    m = _fixture()
    m["prereg_files"][0]["current_sha256"] = "0" * 64
    jp = tmp_path / "m.json"
    mp = tmp_path / "m.md"
    jp.write_text(json.dumps(m), encoding="utf-8")
    mp.write_text(vp.render_markdown(m), encoding="utf-8")
    assert vp.main(["--check", "--manifest", str(jp), "--md", str(mp)]) == 1
