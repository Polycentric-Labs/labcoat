# scripts/audit.py
"""labcoat audit-trail v2 — an append-only audit substrate.

Canonical SESSION-LEDGER (JSONL, one record per outbound query) + a generated human Markdown view,
an append-only QUESTIONS-IDEAS Markdown log, and a 3-bucket RESURFACE generator. The ledger doubles
as the orchestrator checkpoint/resume store.

Invariants:
  * APPEND-ONLY: writers open in "a" mode; there is no overwrite/delete API.
  * DETERMINISTIC: every timestamp is PASSED IN as an ISO-8601 string; this module NEVER calls
    datetime.now() (so runs are reproducible and tests can inject time).
  * HONESTY: validation_verdict="confirmed" is allowed ONLY when completion_status="complete".
    A known-incomplete / deterministic-fail / unavailable stream is recorded AS-IS and can never be
    silently promoted to a confirmed finding (mirrors the robustness layer's completion rule).

SEAM (#2 robustness): a ledger record is built straight from a fleet.run_fleet result dict — the
model-keyed capture file `<capture_dir>/<safe-model-id>.partial` (fleet._safe_name convention) is the
audit raw substrate, stored verbatim as raw_capture_path.

License: MIT. Author: Allen Byrd.
"""
from __future__ import annotations
import json
import os
import re

# Frozen enums (sourced from scripts/fleet.py + Phase 3/4).
COMPLETION_STATUSES = frozenset({"complete", "known-incomplete", "deterministic-fail", "unavailable"})
VALIDATION_VERDICTS = frozenset({"pending", "confirmed", "fabricated", "unverifiable"})

_LEDGER_FIELDS = ("timestamp", "loop_id", "query_id", "sub_question", "model",
                  "redaction_applied", "raw_capture_path", "completion_status",
                  "validation_verdict", "cost", "claim_text")


def make_ledger_record(*, timestamp: str, loop_id: str, query_id: str, sub_question: str,
                       model: str, redaction_applied: bool, raw_capture_path: str | None,
                       completion_status: str, validation_verdict: str = "pending",
                       cost: float = 0.0, claim_text: str = "") -> dict:
    """Build one validated ledger record (a plain dict). Enforces the enums, the ISO-string timestamp
    contract, and the HONESTY invariant (confirmed requires complete). Raises ValueError on violation."""
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("timestamp must be a non-empty ISO-8601 string (passed in, never datetime.now())")
    if completion_status not in COMPLETION_STATUSES:
        raise ValueError(f"completion_status {completion_status!r} not in {sorted(COMPLETION_STATUSES)}")
    if validation_verdict not in VALIDATION_VERDICTS:
        raise ValueError(f"validation_verdict {validation_verdict!r} not in {sorted(VALIDATION_VERDICTS)}")
    if validation_verdict == "confirmed" and completion_status != "complete":
        raise ValueError(
            f"HONESTY invariant: validation_verdict='confirmed' requires completion_status='complete', "
            f"got completion_status={completion_status!r} — a non-complete stream is never promoted.")
    return {"timestamp": timestamp, "loop_id": loop_id, "query_id": query_id,
            "sub_question": sub_question, "model": model, "redaction_applied": bool(redaction_applied),
            "raw_capture_path": raw_capture_path, "completion_status": completion_status,
            "validation_verdict": validation_verdict, "cost": cost, "claim_text": claim_text}


def append_ledger(ledger_path: str, record: dict, *, fsync: bool = False) -> None:
    """Append ONE validated record to the canonical JSONL ledger (append-only; opens in 'a' mode).
    The record is re-validated (enums + honesty invariant) so a malformed dict never reaches disk.
    Uses .get() throughout so a missing field surfaces as a ValueError from make_ledger_record
    (e.g. missing timestamp -> None -> ValueError), never a raw KeyError.

    fsync=True forces the record to physical disk (os.fsync == FlushFileBuffers on Windows/NTFS) before
    returning — use it for the durable 'record-the-intent-BEFORE-the-outbound-call' ordering a reboot-safe
    orchestrator needs (default off = the OS flushes on close, fast but a hard reboot can lose the last
    record). Pair with atomic os.replace for any snapshot file; directory-fsync is unavailable on Windows."""
    valid = make_ledger_record(
        timestamp=record.get("timestamp"), loop_id=record.get("loop_id"), query_id=record.get("query_id"),
        sub_question=record.get("sub_question"), model=record.get("model"),
        redaction_applied=record.get("redaction_applied", False),
        raw_capture_path=record.get("raw_capture_path"),
        completion_status=record.get("completion_status"),
        validation_verdict=record.get("validation_verdict", "pending"),
        cost=record.get("cost", 0.0), claim_text=record.get("claim_text", ""))
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(valid, ensure_ascii=False) + "\n")
        if fsync:
            fh.flush()
            os.fsync(fh.fileno())


def read_ledger(ledger_path: str) -> list[dict]:
    """Read the JSONL ledger back into a list of records. Missing file -> []; blank lines skipped."""
    try:
        with open(ledger_path, "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        return []


def ledger_record_from_fleet(*, timestamp: str, loop_id: str, query_id: str, sub_question: str,
                             redaction_applied: bool, fleet_result: dict,
                             validation_verdict: str = "pending", claim_text: str = "") -> dict:
    """The SEAM into #2 robustness: build a ledger record straight from a fleet.run_fleet() result dict.
    model / capture_path (the model-keyed `<capture_dir>/<safe-model-id>.partial`) / completion_status /
    cost_est pull through verbatim, so the capture file is the audit raw substrate. The honesty invariant
    still applies (a known-incomplete result cannot be passed validation_verdict='confirmed')."""
    return make_ledger_record(
        timestamp=timestamp, loop_id=loop_id, query_id=query_id, sub_question=sub_question,
        model=fleet_result.get("model"), redaction_applied=redaction_applied,
        raw_capture_path=fleet_result.get("capture_path"),
        completion_status=fleet_result.get("completion_status"),
        validation_verdict=validation_verdict, cost=fleet_result.get("cost_est", 0.0),
        claim_text=claim_text)


def _md_cell(value) -> str:
    """Escape a value for a Markdown table cell (pipes would break the column count)."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_ledger_markdown(records: list[dict]) -> str:
    """Render the JSONL ledger as a human-readable Markdown table (JSONL stays canonical)."""
    head = "# Session Ledger\n\n"
    if not records:
        return head + "_No records yet._\n"
    cols = "| timestamp | loop | query | model | redacted | status | verdict | cost |\n"
    rule = "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    body = "".join(
        f"| {_md_cell(r.get('timestamp'))} | {_md_cell(r.get('loop_id'))} | "
        f"{_md_cell(r.get('query_id'))}: {_md_cell(r.get('sub_question'))} | {_md_cell(r.get('model'))} | "
        f"{_md_cell(r.get('redaction_applied'))} | {_md_cell(r.get('completion_status'))} | "
        f"{_md_cell(r.get('validation_verdict'))} | {_md_cell(r.get('cost'))} |\n"
        for r in records)
    return head + cols + rule + body


QUESTION_KINDS = frozenset({"question", "idea"})
_Q_LINE = re.compile(r"^- \[(?P<timestamp>[^\]]+)\] \((?P<kind>question|idea)\) (?P<text>.*)$")


def append_question(questions_path: str, *, timestamp: str, text: str, kind: str = "question") -> None:
    """Append one question/idea to the Markdown QUESTIONS-IDEAS log the instant it arises (append-only).
    kind ∈ {question, idea}; timestamp is a passed-in ISO-8601 string (never datetime.now())."""
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("timestamp must be a non-empty ISO-8601 string (passed in)")
    if kind not in QUESTION_KINDS:
        raise ValueError(f"kind {kind!r} not in {sorted(QUESTION_KINDS)}")
    line = f"- [{timestamp}] ({kind}) {str(text).replace(chr(10), ' ')}\n"
    with open(questions_path, "a", encoding="utf-8") as fh:
        fh.write(line)


def read_questions(questions_path: str) -> list[dict]:
    """Parse the QUESTIONS-IDEAS log back into {timestamp, kind, text} dicts. Missing file -> [];
    non-bullet / prose lines are ignored."""
    out: list[dict] = []
    try:
        with open(questions_path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = _Q_LINE.match(line.rstrip("\n"))
                if m:
                    out.append({"timestamp": m["timestamp"], "kind": m["kind"], "text": m["text"]})
    except FileNotFoundError:
        return []
    return out


def _is_applyable(record: dict) -> bool:
    """Bucket-1 membership: a confirmed finding (honesty invariant guarantees it is also complete)."""
    return record.get("validation_verdict") == "confirmed"


def generate_resurface(records: list[dict], questions: list[dict], *, timestamp: str) -> str:
    """End-of-cycle RESURFACE doc with three buckets:
      1. apply the validated findings now        (confirmed ledger records)
      2. new research paths (which to pursue)     (kind='idea' questions; the pick is a SKILL.md gate)
      3. unresolved / uncertain                   (non-confirmed/non-complete records + kind='question')
    timestamp is a passed-in ISO-8601 string (never datetime.now())."""
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("timestamp must be a non-empty ISO-8601 string (passed in)")

    applyable = [r for r in records if _is_applyable(r)]
    ideas = [q for q in questions if q.get("kind") == "idea"]
    unresolved_recs = [r for r in records if not _is_applyable(r)]
    open_qs = [q for q in questions if q.get("kind") == "question"]

    def _bullets(lines: list[str]) -> str:
        return ("\n".join(f"- {ln}" for ln in lines) + "\n") if lines else "_None._\n"

    b1 = _bullets([f"`{r.get('query_id')}` ({r.get('model')}): {r.get('sub_question')}" for r in applyable])
    b2 = _bullets([f"[{q.get('timestamp')}] {q.get('text')}" for q in ideas])
    b3 = _bullets(
        [f"`{r.get('query_id')}` [{r.get('completion_status')}/{r.get('validation_verdict')}]: "
         f"{r.get('sub_question')}" for r in unresolved_recs]
        + [f"[{q.get('timestamp')}] {q.get('text')}" for q in open_qs])

    return (f"# Resurface — {timestamp}\n\n"
            f"## Bucket 1 — apply the validated findings now\n\n{b1}\n"
            f"## Bucket 2 — new research paths (which ones to pursue?)\n\n{b2}\n"
            f"## Bucket 3 — unresolved / uncertain\n\n{b3}")
