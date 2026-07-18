# scripts/n1_corpus_openalex.py
"""labcoat N1 OpenAlex corpus adapter — PURE parse (reconstruct_abstract / normalize_openalex_record, unit-tested)
+ a network shell (resolve_concepts / fetch_openalex) with an injected get(url, params) -> (status, json) seam so
the cursor/dedupe/verify logic is deterministically testable. OpenAlex is FREE (no API key). Normalized records
match n1_corpus's {id,title,abstract,date,categories} shape so everything downstream is reused unchanged.
License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import time
import pathlib
import hashlib

_OA_BASE = "https://api.openalex.org"
_OA_PREFIX = "https://openalex.org/"


def reconstruct_abstract(inverted_index) -> str:
    """OpenAlex abstract_inverted_index ({token: [positions]}) -> plain text: place each token at each of its
    positions, order by position, join by single space. None / empty -> "". Pure."""
    if not inverted_index:
        return ""
    positioned = []
    for token, positions in inverted_index.items():
        for p in (positions or []):
            positioned.append((int(p), token))
    positioned.sort(key=lambda t: t[0])
    return " ".join(tok for _, tok in positioned)


def normalize_openalex_record(work) -> dict:
    """One OpenAlex work dict -> {id, title, abstract, date, categories}. id = bare W-id (prefix stripped);
    title = title|display_name|''; abstract = reconstruct_abstract(...); date = publication_date[:10];
    categories = [primary_topic.display_name] + up to 5 concepts[].display_name (informational). Pure; tolerant."""
    raw_id = str(work.get("id") or "")
    wid = raw_id[len(_OA_PREFIX):] if raw_id.startswith(_OA_PREFIX) else raw_id
    title = (work.get("title") or work.get("display_name") or "").strip()
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    date = (work.get("publication_date") or "")[:10]
    cats = []
    pt = work.get("primary_topic") or {}
    if pt.get("display_name"):
        cats.append(pt["display_name"])
    for c in (work.get("concepts") or [])[:5]:
        if c.get("display_name"):
            cats.append(c["display_name"])
    return {"id": wid, "title": title, "abstract": abstract, "date": date, "categories": cats}


def _default_get(url, params):
    import httpx  # lazy: not needed for the pure parse path
    r = httpx.get(url, params=params, timeout=60.0, follow_redirects=True)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def resolve_concepts(names, *, get=None, mailto=""):
    """Resolve each concept NAME -> {name, id} via /concepts?search=, verifying the top hit's display_name equals
    the requested name (case-insensitive, fail-closed RuntimeError on mismatch/miss). get(url,params)->(status,json)
    is injected (default httpx). Self-verifies the concept proper-noun at build time."""
    get = get or _default_get
    out = []
    for name in names:
        params = {"search": name, "per-page": 1}
        if mailto:
            params["mailto"] = mailto
        status, data = get(f"{_OA_BASE}/concepts", params)
        results = (data or {}).get("results") or []
        if status != 200 or not results:
            raise RuntimeError(f"OpenAlex concept resolve failed for {name!r} (status {status})")
        top = results[0]
        disp = str(top.get("display_name") or "")
        if disp.strip().lower() != str(name).strip().lower():
            raise RuntimeError(f"OpenAlex concept mismatch for {name!r}: top hit was {disp!r} (fail-closed)")
        cid = str(top.get("id") or "")
        cid = cid[len(_OA_PREFIX):] if cid.startswith(_OA_PREFIX) else cid
        out.append({"name": name, "id": cid})
    return out


def fetch_openalex(concept_ids, *, per_concept, cache_dir, get=None, mailto="", from_date="2018-01-01",
                   page_size=200, sleep=None, max_retries=5, retry_backoff_s=5.0) -> list:
    """Fetch up to per_concept works per concept id (cursor pagination), normalize, and DEDUPE by bare id across
    concepts. get(url,params)->(status,json) and sleep injected (sleep forbidden on cache hits). Raw-JSON cache
    keyed by (cid, from_date, page_size, cursor). 429/5xx linear backoff-retry. has_abstract:true so docs embed."""
    get = get or _default_get
    sleep = sleep if sleep is not None else time.sleep
    cache = pathlib.Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    page_size = min(int(page_size), 200)
    seen, records = set(), []
    made_live = False
    for cid in concept_ids:
        cursor = "*"
        fetched = 0
        while cursor and fetched < int(per_concept):
            key = hashlib.sha256(f"{cid}|{from_date}|{page_size}|{cursor}".encode("utf-8")).hexdigest()[:16]
            cf = cache / f"openalex_{key}.json"
            if cf.exists():
                data = json.loads(cf.read_text(encoding="utf-8"))
            else:
                if made_live:
                    sleep(1.0)  # courtesy delay between LIVE requests only
                params = {"filter": f"concepts.id:{cid},from_publication_date:{from_date},has_abstract:true",
                          "per-page": page_size, "cursor": cursor}
                if mailto:
                    params["mailto"] = mailto
                data = None
                for attempt in range(int(max_retries)):
                    status, body = get(f"{_OA_BASE}/works", params)
                    if status in (429, 500, 502, 503, 504):
                        sleep(float(retry_backoff_s) * (attempt + 1))
                        continue
                    if status != 200:
                        raise RuntimeError(f"OpenAlex works fetch failed (status {status}) for concept {cid}")
                    data = body
                    break
                if data is None:
                    raise RuntimeError(f"OpenAlex rate-limited after {max_retries} retries (concept {cid})")
                cf.write_text(json.dumps(data), encoding="utf-8")
                made_live = True
            results = (data or {}).get("results") or []
            if not results:
                break
            for w in results:
                fetched += 1
                rec = normalize_openalex_record(w)
                if rec["id"] and rec["id"] not in seen:
                    seen.add(rec["id"])
                    records.append(rec)
                if fetched >= int(per_concept):
                    break
            next_cursor = (data.get("meta") or {}).get("next_cursor")
            if next_cursor == "*":  # defensive: OpenAlex ends with null; a "*" next_cursor would infinite-loop via cache
                break
            cursor = next_cursor
    return records
