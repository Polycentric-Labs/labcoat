"""Tests for scripts/archive.py — the raw-stream archive (pure core + I/O shell + CLI)."""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import archive


# ---- Task 1: hashing + safe names ----

def test_content_sha256_stable_and_str_bytes_equivalent():
    h = archive.content_sha256("hello")
    assert h == archive.content_sha256(b"hello")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_safe_artifact_name_sanitizes_slashes_and_colons():
    assert archive.safe_artifact_name("S1", "openai/gpt-5.2") == "S1__openai_gpt-5.2"
    assert "/" not in archive.safe_artifact_name("S1", "z-ai/glm-5.2:beta")
    assert ":" not in archive.safe_artifact_name("S1", "z-ai/glm-5.2:beta")


# ---- Task 2: entry schema + JSONL round-trip ----

def _entry(**kw):
    base = dict(run_id="r1", ts="2026-07-20T00:00:00Z", question="is X novel?",
                stream="S1", model="openai/gpt-5.2", source_type="fleet", content="answer text")
    base.update(kw)
    return archive.make_entry(**base)


def test_make_entry_computes_hash_bytes_path_and_schema():
    e = _entry()
    assert e["schema_version"] == archive.SCHEMA_VERSION
    assert e["content_sha256"] == archive.content_sha256("answer text")
    assert e["content_bytes"] == len(b"answer text")
    assert e["path"] == "r1/S1__openai_gpt-5.2.md"
    assert e["prompt_sha256"] == archive.content_sha256("")  # empty prompt hashed, not stored
    assert e["ok"] is True and e["error"] is None


def test_index_line_roundtrip_is_lossless_single_line():
    e = _entry(cost_usd=0.067, in_tokens=343, out_tokens=4767)
    line = archive.index_line(e)
    assert "\n" not in line.rstrip("\n")
    assert archive.parse_index_line(line) == e


def test_perplexity_source_uses_json_ext():
    e = _entry(source_type="perplexity_dr", model="perplexity/sonar-deep-research", ext="json")
    assert e["path"].endswith(".json")


# ---- Task 3: query helpers ----

def test_filter_and_list_runs_and_run_view():
    es = [_entry(run_id="r1", stream="S1", model="openai/gpt-5.2", cost_usd=0.1),
          _entry(run_id="r1", stream="S2", model="google/gemini-2.5-pro", cost_usd=0.2, ts="2026-07-20T01:00:00Z"),
          _entry(run_id="r2", stream="S1", model="openai/gpt-5.2", cost_usd=0.3, ts="2026-07-21T00:00:00Z")]
    assert len(archive.filter_entries(es, run_id="r1")) == 2
    assert len(archive.filter_entries(es, model="openai/gpt-5.2")) == 2
    assert len(archive.filter_entries(es, since="2026-07-21T00:00:00Z")) == 1
    runs = {r["run_id"]: r for r in archive.list_runs(es)}
    assert runs["r1"]["n_artifacts"] == 2
    assert abs(runs["r1"]["cost_usd"] - 0.3) < 1e-9  # sums the run's costs
    assert runs["r1"]["ts"] == "2026-07-20T00:00:00Z"  # earliest ts in the run
    assert [e["stream"] for e in archive.run_view(es, "r1")] == ["S1", "S2"]


# ---- Task 4: grep ----

def test_grep_entries_matches_via_injected_loader_with_snippet():
    es = [_entry(run_id="r1", stream="S1", content="talks about SemMedDB predications"),
          _entry(run_id="r1", stream="S2", content="unrelated content")]
    texts = {e["content_sha256"]: c for e, c in
             zip(es, ["talks about SemMedDB predications", "unrelated content"])}
    hits = archive.grep_entries(es, r"semmeddb", text_loader=lambda e: texts[e["content_sha256"]])
    assert len(hits) == 1
    assert hits[0]["entry"]["stream"] == "S1"
    assert "SemMedDB" in hits[0]["snippet"]


# ---- Task 5: I/O shell (record/read/idempotency) ----

def test_record_run_writes_files_index_and_is_idempotent(tmp_path):
    root = str(tmp_path / "archive")
    arts = [dict(stream="S1", model="openai/gpt-5.2", source_type="fleet", content="alpha", cost_usd=0.1),
            dict(stream="S2", model="google/gemini-2.5-pro", source_type="fleet", content="beta")]
    entries = archive.record_run(root, run_id="r1", ts="2026-07-20T00:00:00Z", question="q?", artifacts=arts)
    assert len(entries) == 2
    assert len(archive.iter_index(root)) == 2
    assert archive.load_text(root, entries[0]["path"]) == "alpha"
    # content_sha256 MUST equal the hash of the stored bytes (integrity invariant)
    assert entries[0]["content_sha256"] == archive.content_sha256(archive.load_text(root, entries[0]["path"]))
    # idempotent re-record: no new index lines
    archive.record_run(root, run_id="r1", ts="2026-07-20T00:00:00Z", question="q?", artifacts=arts)
    assert len(archive.iter_index(root)) == 2


# ---- Task 6: reader CLI ----

import io, contextlib


def _run_cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = archive._main(list(argv))
    return rc, buf.getvalue()


def test_cli_list_show_get_grep(tmp_path):
    root = str(tmp_path / "archive")
    archive.record_run(root, run_id="r1", ts="2026-07-20T00:00:00Z", question="q?",
        artifacts=[dict(stream="S1", model="openai/gpt-5.2", source_type="fleet", content="mentions SemMedDB")])
    rc, out = _run_cli("--root", root, "list"); assert rc == 0 and "r1" in out
    rc, out = _run_cli("--root", root, "show", "r1"); assert "S1" in out and "openai/gpt-5.2" in out
    sha = archive.iter_index(root)[0]["content_sha256"]
    rc, out = _run_cli("--root", root, "get", sha); assert "mentions SemMedDB" in out
    rc, out = _run_cli("--root", root, "grep", "semmeddb"); assert "r1" in out


# ---- Task 7: capture-hook adapter (maps orchestrator fleet results -> archive) ----

def test_record_fleet_results_maps_query_id_stream_and_cost_est(tmp_path):
    driven = [{"query_id": "L1::sq1::openai/gpt-5.2", "sub_question": "a sub question",
               "result": {"model": "openai/gpt-5.2", "text": "raw fleet answer", "cost_est": 0.067,
                          "in_tokens": 343, "out_tokens": 4767, "completion_status": "complete", "error": None}}]
    entries = archive.record_fleet_results(str(tmp_path / "a"), run_id="r1", ts="2026-07-20T00:00:00Z",
                                           question="top q?", driven_results=driven)
    assert len(entries) == 1
    e = entries[0]
    assert e["stream"] == "L1::sq1"          # model dropped from the query_id
    assert e["model"] == "openai/gpt-5.2"
    assert e["cost_usd"] == 0.067            # cost_est -> cost_usd (the real fleet field is cost_est)
    assert e["ok"] is True                   # completion_status "complete" -> ok
    assert archive.load_text(str(tmp_path / "a"), e["path"]) == "raw fleet answer"


def test_record_fleet_results_skips_empty_text_and_handles_missing_fields(tmp_path):
    driven = [{"query_id": "sq1::m", "result": {"model": "m", "text": "", "completion_status": "unavailable"}},
              {"query_id": "sq2::m", "result": {"model": "m", "text": "kept"}}]
    entries = archive.record_fleet_results(str(tmp_path / "a"), run_id="r1", ts="2026-07-20T00:00:00Z",
                                           question="q", driven_results=driven)
    assert len(entries) == 1 and entries[0]["stream"] == "sq2"  # empty-text result skipped


def test_run_loop_results_flow_into_archive_end_to_end(tmp_path):
    """The whole hook, no spend: orchestrator run_loop accumulates driven fleet results -> record_fleet_results
    archives them retrievably."""
    import orchestrator_host as host, spend
    def ok_fleet(prompt, models, *, available, **kw):
        m = models[0]["id"]
        return [{"model": m, "ok": True, "completion_status": "complete", "cost_est": 0.002,
                 "capture_path": None, "text": f"raw answer for {prompt}"}]
    def clean_redactor(prompt, *, client_terms=()):
        return {"hard_block": False, "clean_text": prompt, "signal": {"recommend_stop": False},
                "findings": [], "redactions_applied": []}
    _seq = iter([f"2026-07-20T00:00:{i:02d}Z" for i in range(20)])
    subqs = [{"id": "s1", "sub_question": "q1", "prompt": "p1"},
             {"id": "s2", "sub_question": "q2", "prompt": "p2"}]
    work = host.expand_fleet_work(subqs, [{"id": "m"}], loop_id="L1")
    out = host.run_loop(work, ledger_path=str(tmp_path / "L.jsonl"), loop_id="L1", clock=lambda: next(_seq),
                        fleet_runner=ok_fleet, redactor=clean_redactor, available=["m"], tracker=spend.Tracker(),
                        est_per_query=0.01, tolerance=100.0, next_loop_est=0.05)
    assert len(out["results"]) == 2
    entries = archive.record_fleet_results(str(tmp_path / "arch"), run_id="r1", ts="2026-07-20T00:00:00Z",
                                           question="top q", driven_results=out["results"])
    by_stream = {e["stream"]: e for e in entries}
    assert set(by_stream) == {"L1::s1", "L1::s2"}   # loop-scoped query_ids -> stream ids (model dropped)
    assert "raw answer for p1" in archive.load_text(str(tmp_path / "arch"), by_stream["L1::s1"]["path"])
