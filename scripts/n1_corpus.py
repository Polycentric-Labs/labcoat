# scripts/n1_corpus.py
"""labcoat N1 corpus shell — fetch a small arXiv corpus + PURE Atom parsing. The parse (normalize_record /
embed_text / _parse_feed) is pure + unit-tested; fetch_arxiv does the network I/O (httpx, already a dep) with an
on-disk raw cache and a 3-second courtesy delay (arXiv API user manual). License: MIT. Author: Allen Byrd.

HONEST LIMITS: a few-thousand-abstract corpus via the plain API is fine (OAI-PMH is the path for tens-of-thousands).
The arXiv id is stripped to its bare form (no version); `date` is the v1 <published> date for the temporal cutoff."""
from __future__ import annotations
import re
import time
import pathlib
import hashlib
import xml.etree.ElementTree as ET

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_ARXIV_API = "https://export.arxiv.org/api/query"  # https: export.arxiv.org 301-redirects http -> https


def _collapse(s) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _parse_feed(xml_text: str) -> list:
    """Return the <entry> Elements of an arXiv Atom feed. Pure."""
    return ET.fromstring(xml_text).findall(f"{_ATOM}entry")


def normalize_record(entry) -> dict:
    """Parse ONE Atom <entry> Element -> {id,title,abstract,date,categories}. Pure. id = bare arXiv id (prefix +
    trailing vN stripped); date = <published> (v1) as YYYY-MM-DD; primary category is placed first."""
    raw_id = (entry.findtext(f"{_ATOM}id") or "").strip()
    arxiv_id = raw_id.split("/abs/")[-1]
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
    title = _collapse(entry.findtext(f"{_ATOM}title"))
    abstract = _collapse(entry.findtext(f"{_ATOM}summary"))
    date = (entry.findtext(f"{_ATOM}published") or "").strip()[:10]
    cats = [c.get("term") for c in entry.findall(f"{_ATOM}category") if c.get("term")]
    primary = entry.find(f"{_ARXIV}primary_category")
    pterm = primary.get("term") if primary is not None else None
    if pterm:
        cats = [pterm] + [c for c in cats if c != pterm]
    return {"id": arxiv_id, "title": title, "abstract": abstract, "date": date, "categories": cats}


def embed_text(record) -> str:
    """Canonical join the corpus stores: title + [SEP] + abstract (the embedder substitutes its real sep_token)."""
    return f"{record.get('title', '')}[SEP]{record.get('abstract', '')}"


def fetch_arxiv(query: str, *, max_results: int, cache_dir, start: int = 0, page_size: int = 200,
                delay_s: float = 3.0, sleep=None, max_retries: int = 5, retry_backoff_s: float = 5.0) -> list:
    """Fetch up to max_results normalized records for an arXiv search_query, paging by start+page_size (<=2000),
    with a 3s courtesy delay between LIVE requests and a raw-XML on-disk cache (re-runs read cache, no re-hit).
    `sleep` is injected (defaults to time.sleep) so tests can forbid it on cache hits."""
    import httpx  # lazy: not needed for the pure parse path
    sleep = sleep if sleep is not None else time.sleep
    cache = pathlib.Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    page_size = min(int(page_size), 2000)
    records: list = []
    fetched = 0
    s = int(start)
    made_live_request = False
    while fetched < int(max_results):
        # Always request a FULL page_size page (so the cache file keyed by (query,start,page_size) holds a coherent
        # page regardless of max_results); the caller's max_results is applied by the final slice below.
        key = hashlib.sha256(f"{query}|{s}|{page_size}".encode("utf-8")).hexdigest()[:16]
        cf = cache / f"arxiv_{key}.xml"
        if cf.exists():
            xml_text = cf.read_text(encoding="utf-8")
        else:
            if made_live_request:
                sleep(delay_s)  # courtesy delay between consecutive LIVE requests only
            params = {"search_query": query, "start": s, "max_results": page_size,
                      "sortBy": "submittedDate", "sortOrder": "descending"}
            xml_text = None
            for attempt in range(int(max_retries)):   # linear backoff-retry on arXiv rate-limit (429) / transient (503)
                r = httpx.get(_ARXIV_API, params=params, timeout=60.0, follow_redirects=True)
                if r.status_code in (429, 503):
                    sleep(float(retry_backoff_s) * (attempt + 1))
                    continue
                r.raise_for_status()
                xml_text = r.text
                break
            if xml_text is None:
                raise RuntimeError(f"arXiv rate-limited ({r.status_code}) after {max_retries} retries — wait a few "
                                   "minutes and re-run, or reduce --n / use OAI-PMH for bulk harvesting")
            cf.write_text(xml_text, encoding="utf-8")
            made_live_request = True
        entries = _parse_feed(xml_text)
        if not entries:
            break
        records.extend(normalize_record(e) for e in entries)
        fetched += len(entries)
        s += len(entries)
        if len(entries) < page_size:
            break
    return records[:int(max_results)]
