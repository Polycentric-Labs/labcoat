import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pytest
import audit

_BASE = dict(
    timestamp="2026-06-21T12:00:00Z", loop_id="L1", query_id="q1",
    sub_question="Is X novel?", model="openai/gpt-5.2",
    redaction_applied=True, raw_capture_path="caps/openai_gpt-5.2.partial",
    completion_status="complete",
)

def test_make_ledger_record_has_all_eleven_fields_and_defaults():
    rec = audit.make_ledger_record(**_BASE)
    assert set(rec) == {"timestamp", "loop_id", "query_id", "sub_question", "model",
                        "redaction_applied", "raw_capture_path", "completion_status",
                        "validation_verdict", "cost", "claim_text"}
    assert rec["validation_verdict"] == "pending"   # default
    assert rec["cost"] == 0.0                         # default
    assert rec["completion_status"] == "complete"

def test_make_ledger_record_rejects_bad_enums():
    with pytest.raises(ValueError):
        audit.make_ledger_record(**{**_BASE, "completion_status": "donezo"})
    with pytest.raises(ValueError):
        audit.make_ledger_record(**{**_BASE, "validation_verdict": "true-ish"})

def test_make_ledger_record_requires_iso_string_timestamp():
    with pytest.raises(ValueError):
        audit.make_ledger_record(**{**_BASE, "timestamp": ""})
    with pytest.raises(ValueError):
        audit.make_ledger_record(**{**_BASE, "timestamp": 1718971200})  # not a string

def test_honesty_known_incomplete_can_never_be_confirmed():
    # the core invariant: a non-complete stream may NOT carry validation_verdict="confirmed"
    with pytest.raises(ValueError):
        audit.make_ledger_record(**{**_BASE, "completion_status": "known-incomplete",
                                    "validation_verdict": "confirmed"})

def test_honesty_deterministic_fail_and_unavailable_cannot_be_confirmed():
    for status in ("deterministic-fail", "unavailable"):
        with pytest.raises(ValueError):
            audit.make_ledger_record(**{**_BASE, "completion_status": status,
                                        "validation_verdict": "confirmed"})

def test_honesty_known_incomplete_records_as_is_with_pending():
    # recorded AS-IS (not dropped) — just never silently promoted
    rec = audit.make_ledger_record(**{**_BASE, "completion_status": "known-incomplete"})
    assert rec["completion_status"] == "known-incomplete"
    assert rec["validation_verdict"] == "pending"


def test_append_and_read_ledger_round_trips(tmp_path):
    led = tmp_path / "SESSION-LEDGER.jsonl"
    r1 = audit.make_ledger_record(**_BASE)
    r2 = audit.make_ledger_record(**{**_BASE, "query_id": "q2", "model": "x-ai/grok-4",
                                     "completion_status": "known-incomplete"})
    audit.append_ledger(str(led), r1)
    audit.append_ledger(str(led), r2)
    rows = audit.read_ledger(str(led))
    assert [x["query_id"] for x in rows] == ["q1", "q2"]
    assert rows[1]["completion_status"] == "known-incomplete"

def test_append_ledger_is_append_only_never_truncates(tmp_path):
    led = tmp_path / "SESSION-LEDGER.jsonl"
    audit.append_ledger(str(led), audit.make_ledger_record(**_BASE))
    audit.append_ledger(str(led), audit.make_ledger_record(**{**_BASE, "query_id": "q2"}))
    # second append must not overwrite the first
    assert len(audit.read_ledger(str(led))) == 2

def test_read_ledger_missing_file_is_empty(tmp_path):
    assert audit.read_ledger(str(tmp_path / "nope.jsonl")) == []

def test_read_ledger_skips_blank_lines(tmp_path):
    led = tmp_path / "SESSION-LEDGER.jsonl"
    audit.append_ledger(str(led), audit.make_ledger_record(**_BASE))
    with open(led, "a", encoding="utf-8") as fh:
        fh.write("\n   \n")   # stray blank lines must not crash the reader
    assert len(audit.read_ledger(str(led))) == 1

def test_append_ledger_validates_records(tmp_path):
    led = tmp_path / "SESSION-LEDGER.jsonl"
    with pytest.raises(ValueError):
        # valid timestamp so the bogus completion_status is the genuine trigger (ValueError, not KeyError)
        audit.append_ledger(str(led), {"timestamp": "2026-06-21T12:00:00Z",
                                       "completion_status": "bogus"})


def test_render_ledger_markdown_table_shape():
    rows = [audit.make_ledger_record(**_BASE),
            audit.make_ledger_record(**{**_BASE, "query_id": "q2",
                                        "completion_status": "known-incomplete"})]
    md = audit.render_ledger_markdown(rows)
    assert md.startswith("# Session Ledger")
    assert "| timestamp | loop | query | model | redacted | status | verdict | cost |" in md
    assert "| --- |" in md
    assert "q1" in md and "q2" in md
    assert "known-incomplete" in md

def test_render_ledger_markdown_escapes_pipes_in_sub_question():
    rows = [audit.make_ledger_record(**{**_BASE, "sub_question": "A|B vs C|D?"})]
    md = audit.render_ledger_markdown(rows)
    # a raw pipe would break the table column count -> must be escaped
    assert "A|B" not in md
    assert "A\\|B vs C\\|D?" in md

def test_render_ledger_markdown_empty_says_so():
    md = audit.render_ledger_markdown([])
    assert "# Session Ledger" in md
    assert "_No records yet._" in md


def test_ledger_record_from_fleet_pulls_through_seam_fields():
    # shape mirrors scripts/fleet.run_fleet() result dicts
    fleet_result = {"model": "google/gemini-2.5-pro", "ok": True, "text": "...",
                    "in_tokens": 1500, "out_tokens": 8000, "cost_est": 0.0819,
                    "error": None, "completion_status": "complete", "rerun_count": 1,
                    "capture_path": "caps/google_gemini-2.5-pro.partial"}
    rec = audit.ledger_record_from_fleet(
        timestamp="2026-06-21T12:00:00Z", loop_id="L1", query_id="q7",
        sub_question="Does Y already exist?", redaction_applied=True, fleet_result=fleet_result)
    assert rec["model"] == "google/gemini-2.5-pro"
    assert rec["raw_capture_path"] == "caps/google_gemini-2.5-pro.partial"   # the .partial seam
    assert rec["completion_status"] == "complete"
    assert rec["cost"] == 0.0819
    assert rec["validation_verdict"] == "pending"

def test_ledger_record_from_fleet_honors_honesty_on_known_incomplete():
    fleet_result = {"model": "x-ai/grok-4", "completion_status": "known-incomplete",
                    "cost_est": 0.0, "capture_path": "caps/x-ai_grok-4.partial"}
    # a known-incomplete fleet stream may be recorded, but NOT as confirmed
    with pytest.raises(ValueError):
        audit.ledger_record_from_fleet(
            timestamp="2026-06-21T12:00:00Z", loop_id="L1", query_id="q8",
            sub_question="Q?", redaction_applied=True, fleet_result=fleet_result,
            validation_verdict="confirmed")
    ok = audit.ledger_record_from_fleet(
        timestamp="2026-06-21T12:00:00Z", loop_id="L1", query_id="q8",
        sub_question="Q?", redaction_applied=True, fleet_result=fleet_result)
    assert ok["completion_status"] == "known-incomplete" and ok["validation_verdict"] == "pending"


def test_append_question_writes_markdown_bullet(tmp_path):
    qf = tmp_path / "QUESTIONS-IDEAS.md"
    audit.append_question(str(qf), timestamp="2026-06-21T12:00:00Z",
                          text="Does the novelty metric Goodhart?", kind="question")
    audit.append_question(str(qf), timestamp="2026-06-21T12:05:00Z",
                          text="Try MAP-Elites for idea-selection", kind="idea")
    txt = qf.read_text(encoding="utf-8")
    assert "- [2026-06-21T12:00:00Z] (question) Does the novelty metric Goodhart?" in txt
    assert "- [2026-06-21T12:05:00Z] (idea) Try MAP-Elites for idea-selection" in txt

def test_append_question_is_append_only(tmp_path):
    qf = tmp_path / "QUESTIONS-IDEAS.md"
    audit.append_question(str(qf), timestamp="2026-06-21T12:00:00Z", text="one", kind="question")
    audit.append_question(str(qf), timestamp="2026-06-21T12:01:00Z", text="two", kind="idea")
    assert len(audit.read_questions(str(qf))) == 2

def test_append_question_rejects_bad_kind(tmp_path):
    qf = tmp_path / "QUESTIONS-IDEAS.md"
    with pytest.raises(ValueError):
        audit.append_question(str(qf), timestamp="2026-06-21T12:00:00Z", text="x", kind="musing")

def test_append_question_requires_iso_string_timestamp(tmp_path):
    qf = tmp_path / "QUESTIONS-IDEAS.md"
    with pytest.raises(ValueError):
        audit.append_question(str(qf), timestamp="", text="x", kind="idea")

def test_read_questions_parses_kind_and_text(tmp_path):
    qf = tmp_path / "QUESTIONS-IDEAS.md"
    audit.append_question(str(qf), timestamp="2026-06-21T12:00:00Z", text="a Q", kind="question")
    audit.append_question(str(qf), timestamp="2026-06-21T12:05:00Z", text="an idea", kind="idea")
    parsed = audit.read_questions(str(qf))
    assert parsed[0] == {"timestamp": "2026-06-21T12:00:00Z", "kind": "question", "text": "a Q"}
    assert parsed[1]["kind"] == "idea" and parsed[1]["text"] == "an idea"

def test_read_questions_missing_file_is_empty(tmp_path):
    assert audit.read_questions(str(tmp_path / "nope.md")) == []

def test_read_questions_ignores_non_bullet_lines(tmp_path):
    qf = tmp_path / "QUESTIONS-IDEAS.md"
    qf.write_text("# Questions & Ideas\n\nsome prose\n", encoding="utf-8")
    audit.append_question(str(qf), timestamp="2026-06-21T12:00:00Z", text="real", kind="idea")
    parsed = audit.read_questions(str(qf))
    assert len(parsed) == 1 and parsed[0]["text"] == "real"


def test_generate_resurface_three_buckets(tmp_path):
    records = [
        audit.make_ledger_record(**{**_BASE, "query_id": "qC", "validation_verdict": "confirmed"}),
        audit.make_ledger_record(**{**_BASE, "query_id": "qP"}),  # pending
        audit.make_ledger_record(**{**_BASE, "query_id": "qF", "validation_verdict": "fabricated"}),
        audit.make_ledger_record(**{**_BASE, "query_id": "qI",
                                    "completion_status": "known-incomplete"}),
    ]
    questions = [
        {"timestamp": "2026-06-21T12:00:00Z", "kind": "question", "text": "open Q?"},
        {"timestamp": "2026-06-21T12:05:00Z", "kind": "idea", "text": "new path: MAP-Elites"},
    ]
    md = audit.generate_resurface(records, questions, timestamp="2026-06-21T18:00:00Z")
    assert "# Resurface — 2026-06-21T18:00:00Z" in md
    assert "## Bucket 1 — apply the validated findings now" in md
    assert "## Bucket 2 — new research paths" in md
    assert "## Bucket 3 — unresolved / uncertain" in md
    # bucket 1: only the confirmed record
    b1, b2, b3 = md.split("## Bucket 2")[0], md.split("## Bucket 2")[1].split("## Bucket 3")[0], md.split("## Bucket 3")[1]
    assert "qC" in b1 and "qP" not in b1 and "qF" not in b1
    # bucket 2: only ideas
    assert "MAP-Elites" in b2 and "open Q?" not in b2
    # bucket 3: pending + fabricated + known-incomplete records AND the open question
    assert "qP" in b3 and "qF" in b3 and "qI" in b3 and "open Q?" in b3
    assert "qC" not in b3

def test_generate_resurface_empty_buckets_say_none(tmp_path):
    md = audit.generate_resurface([], [], timestamp="2026-06-21T18:00:00Z")
    assert md.count("_None._") == 3   # all three buckets explicitly empty


def test_ledger_record_fields_match_canonical_set():
    # _LEDGER_FIELDS is the authoritative field set; the built record must match it exactly.
    # This pins the constant to make_ledger_record's return dict so the two cannot drift silently.
    rec = audit.make_ledger_record(**_BASE)
    assert set(rec) == set(audit._LEDGER_FIELDS)
    assert len(audit._LEDGER_FIELDS) == 11

def test_generate_resurface_rejects_non_string_timestamp():
    with pytest.raises(ValueError):
        audit.generate_resurface([], [], timestamp="")
    with pytest.raises(ValueError):
        audit.generate_resurface([], [], timestamp=None)


def test_append_ledger_fsync_true_forces_os_fsync(tmp_path, monkeypatch):
    # the durable 'record-the-intent-before-the-outbound-call' path: fsync=True must hit os.fsync
    led = tmp_path / "SESSION-LEDGER.jsonl"
    calls = []
    monkeypatch.setattr(audit.os, "fsync", lambda fd: calls.append(fd))
    audit.append_ledger(str(led), audit.make_ledger_record(**_BASE), fsync=True)
    assert calls, "fsync=True must call os.fsync (FlushFileBuffers on Windows) for reboot-durable ordering"
    assert len(audit.read_ledger(str(led))) == 1   # record still written correctly

def test_append_ledger_fsync_defaults_off_no_os_fsync(tmp_path, monkeypatch):
    # default must NOT change behavior (no fsync) — the fast path stays fast
    led = tmp_path / "SESSION-LEDGER.jsonl"
    calls = []
    monkeypatch.setattr(audit.os, "fsync", lambda fd: calls.append(fd))
    audit.append_ledger(str(led), audit.make_ledger_record(**_BASE))
    assert calls == []
    assert len(audit.read_ledger(str(led))) == 1


def test_make_ledger_record_has_claim_text_field_default_empty():
    rec = audit.make_ledger_record(**_BASE)
    assert "claim_text" in rec and rec["claim_text"] == ""        # new 11th field, default empty
    assert len(audit._LEDGER_FIELDS) == 11

def test_make_ledger_record_carries_claim_text():
    rec = audit.make_ledger_record(**{**_BASE, "validation_verdict": "confirmed",
                                      "claim_text": "GLM is on the BIS Entity List"})
    assert rec["claim_text"] == "GLM is on the BIS Entity List"

def test_ledger_record_from_fleet_defaults_claim_text_empty():
    fr = {"model": "x", "completion_status": "complete", "cost_est": 0.0, "capture_path": "c.partial"}
    rec = audit.ledger_record_from_fleet(timestamp="2026-06-21T12:00:00Z", loop_id="L1", query_id="q1",
                                         sub_question="Q?", redaction_applied=True, fleet_result=fr)
    assert rec["claim_text"] == ""
