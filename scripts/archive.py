"""labcoat raw-stream ARCHIVE — durable, append-only, content-addressed store of raw research streams.
PURE CORE (hashing/schema/JSONL/queries: no I/O, clock, or network) + thin I/O shell + reader CLI + capture hook.
Storage _internal/archive/ is PRIVATE (never mirrored). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import hashlib, json, os, pathlib, re

SCHEMA_VERSION = 1


def content_sha256(data) -> str:
    """SHA-256 hex of str (utf-8) or bytes. The integrity anchor + dedup key + B/C join key."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def safe_artifact_name(stream: str, model: str) -> str:
    """Filesystem-safe basename `<stream>__<model>` (slashes/colons/etc. -> '_')."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", f"{stream}__{model}")


def make_entry(*, run_id, ts, question, stream, model, source_type, content,
               prompt="", cost_usd=None, in_tokens=None, out_tokens=None, ok=True, error=None, ext="md"):
    """Build a validated index entry (schema_version stamped). `content` MUST be str — serialize dict/JSON
    payloads to text before calling, so the stored bytes == content_sha256 by construction. Prompts are HASHED,
    not stored (redaction-safe). Pure — no I/O; `ts` is supplied by the caller."""
    if not isinstance(content, str):
        raise TypeError("archive content must be str (serialize JSON payloads to text before calling)")
    name = safe_artifact_name(stream, model)
    return {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "ts": ts, "question": question,
        "stream": stream, "model": model, "source_type": source_type,
        "prompt_sha256": content_sha256(prompt), "content_sha256": content_sha256(content),
        "content_bytes": len(content.encode("utf-8")),
        "cost_usd": cost_usd, "in_tokens": in_tokens, "out_tokens": out_tokens,
        "path": f"{run_id}/{name}.{ext}", "ok": ok, "error": error,
    }


def index_line(entry) -> str:
    """Serialize an entry to one JSONL line (sorted keys → stable/diffable; ensure_ascii=False keeps utf-8)."""
    return json.dumps(entry, ensure_ascii=False, sort_keys=True)


def parse_index_line(line: str) -> dict:
    return json.loads(line)


def filter_entries(entries, *, run_id=None, model=None, source_type=None, since=None, until=None):
    """Filter entries by run/model/source and ISO8601-UTC ts window (ts sorts lexicographically). Pure."""
    out = []
    for e in entries:
        if run_id is not None and e["run_id"] != run_id: continue
        if model is not None and e["model"] != model: continue
        if source_type is not None and e["source_type"] != source_type: continue
        if since is not None and e["ts"] < since: continue
        if until is not None and e["ts"] > until: continue
        out.append(e)
    return out


def list_runs(entries):
    """One rollup per run_id: {run_id, ts (earliest), question, n_artifacts, cost_usd (sum)}, sorted by ts."""
    by_run = {}
    for e in entries:
        r = by_run.setdefault(e["run_id"], {"run_id": e["run_id"], "ts": e["ts"], "question": e["question"],
                                            "n_artifacts": 0, "cost_usd": 0.0})
        r["n_artifacts"] += 1
        r["cost_usd"] += (e.get("cost_usd") or 0.0)
        if e["ts"] < r["ts"]: r["ts"] = e["ts"]
    return sorted(by_run.values(), key=lambda r: r["ts"])


def run_view(entries, run_id):
    """All entries for one run, in insertion order."""
    return [e for e in entries if e["run_id"] == run_id]


def grep_entries(entries, pattern, text_loader, *, flags=re.I):
    """Regex-search each entry's text (loaded via the injected `text_loader` -> pure/testable). Returns
    [{entry, snippet}] for matches; the snippet is ~40 chars of context around the first match."""
    rx = re.compile(pattern, flags)
    out = []
    for e in entries:
        text = text_loader(e)
        m = rx.search(text)
        if m:
            a, b = max(0, m.start() - 40), min(len(text), m.end() + 40)
            out.append({"entry": e, "snippet": text[a:b].replace("\n", " ")})
    return out


# ---- I/O shell (the only fs-touching layer; durable append-only writes + reads) ----

def _read_lines(path: pathlib.Path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _fsync_write(path: pathlib.Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())


def record_artifact(root, entry, content) -> bool:
    """Write the artifact file + append its line to the run's index.jsonl shard (both fsync'd). Idempotent by
    content_sha256 (a re-record of identical content is a no-op → returns False). Append-only; never mutates."""
    root = pathlib.Path(root)
    shard = root / entry["run_id"] / "index.jsonl"
    if entry["content_sha256"] in {parse_index_line(l)["content_sha256"] for l in _read_lines(shard)}:
        return False
    _fsync_write(root / entry["path"], content)
    shard.parent.mkdir(parents=True, exist_ok=True)
    with open(shard, "a", encoding="utf-8") as f:
        f.write(index_line(entry) + "\n"); f.flush(); os.fsync(f.fileno())
    return True


def record_run(root, *, run_id, ts, question, artifacts):
    """Promote a finished run's artifacts into the archive. Each artifact = {stream, model, source_type, content,
    [prompt, cost_usd, in_tokens, out_tokens, ok, error, ext]}. Returns the entries (recorded or already-present)."""
    entries = []
    for a in artifacts:
        e = make_entry(run_id=run_id, ts=ts, question=question, stream=a["stream"], model=a["model"],
                       source_type=a["source_type"], content=a["content"], prompt=a.get("prompt", ""),
                       cost_usd=a.get("cost_usd"), in_tokens=a.get("in_tokens"), out_tokens=a.get("out_tokens"),
                       ok=a.get("ok", True), error=a.get("error"), ext=a.get("ext", "md"))
        record_artifact(root, e, a["content"])
        entries.append(e)
    return entries


def iter_index(root):
    """Read + merge all per-run index.jsonl shards under root (globbed, sorted). Returns a flat list of entries."""
    root = pathlib.Path(root)
    out = []
    for shard in sorted(root.glob("*/index.jsonl")):
        out.extend(parse_index_line(l) for l in _read_lines(shard))
    return out


def load_text(root, path):
    """Read one stored artifact's text (the grep text_loader)."""
    return (pathlib.Path(root) / path).read_text(encoding="utf-8")


# ---- Capture-hook adapter (orchestrator fleet results -> archive) ----

def _stream_from_query_id(query_id) -> str:
    """Short filename-safe stream id from an orchestrator query_id `loop::subq::model` by dropping the trailing
    model segment -> `loop::subq` (model is a separate field). Legacy/plain ids pass through unchanged."""
    parts = str(query_id).split("::")
    return "::".join(parts[:-1]) if len(parts) > 1 else str(query_id)


def record_fleet_results(root, *, run_id, ts, question, driven_results) -> list:
    """CAPTURE-HOOK adapter: archive a loop's driven fleet results. Each item = {query_id, [sub_question,] result},
    where `result` is a fleet.run_fleet() dict (model / text / cost_est / in_tokens / out_tokens /
    completion_status / error). Empty-text results (unavailable/failed models) are skipped. Returns the entries."""
    arts = []
    for d in driven_results:
        fr = d.get("result") or {}
        text = fr.get("text") or ""
        if not text:
            continue
        arts.append(dict(stream=_stream_from_query_id(d.get("query_id", "")),
                         model=fr.get("model") or "unknown", source_type="fleet", content=text,
                         cost_usd=fr.get("cost_est"), in_tokens=fr.get("in_tokens"), out_tokens=fr.get("out_tokens"),
                         ok=fr.get("completion_status") == "complete", error=fr.get("error")))
    return record_run(root, run_id=run_id, ts=ts, question=question, artifacts=arts)


# ---- Reader CLI ----

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="archive", description="labcoat raw-stream archive reader")
    ap.add_argument("--root", default="_internal/archive")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list", help="list archived artifacts")
    p_list.add_argument("--run"); p_list.add_argument("--model"); p_list.add_argument("--source")
    sub.add_parser("show", help="show a run's artifacts").add_argument("run_id")
    sub.add_parser("get", help="print a raw artifact by content_sha256 or path").add_argument("ref")
    p_grep = sub.add_parser("grep", help="regex-search stored text")
    p_grep.add_argument("pattern"); p_grep.add_argument("--source")
    a = ap.parse_args(argv)
    entries = iter_index(a.root)
    if a.cmd == "list":
        for e in filter_entries(entries, run_id=a.run, model=a.model, source_type=a.source):
            print(f"{e['run_id']}  {e['ts']}  {e['stream']:6} {e['model']:38} {e['source_type']:12} {e['content_bytes']:>8}B  {e['path']}")
    elif a.cmd == "show":
        for e in run_view(entries, a.run_id):
            print(f"{e['stream']:6} {e['model']:38} {e['source_type']:12} {e['path']}")
    elif a.cmd == "get":
        e = next((x for x in entries if x["content_sha256"] == a.ref or x["path"] == a.ref), None)
        if not e:
            print(f"not found: {a.ref}")
            return 1
        print(load_text(a.root, e["path"]))
    elif a.cmd == "grep":
        pool = filter_entries(entries, source_type=a.source) if a.source else entries
        for h in grep_entries(pool, a.pattern, text_loader=lambda e: load_text(a.root, e["path"])):
            e = h["entry"]
            print(f"{e['run_id']}  {e['stream']:6} {e['model']:30}  …{h['snippet']}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
