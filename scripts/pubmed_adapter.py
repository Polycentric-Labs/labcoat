"""labcoat N2 — PubMed/MEDLINE adapter (E-utilities). PURE XML/JSON parsers + an injected-`get` network shell
(mirrors n1_corpus_openalex.py). MeSH descriptor names are the normalized concept list (controlled vocabulary).
FREE (E-utilities, no key at <=3 req/s). Pure layer: stdlib only, no network/key/clock. XML parsing is hardened
against entity-expansion (billion-laughs) + XXE via _safe_fromstring (defusedxml if installed, else stdlib ET +
an internal-<!ENTITY> guard; stdlib ET never fetches external DTDs, so no network). License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET


def _safe_fromstring(xml_text):
    """Parse XML with defense-in-depth against entity-expansion / XXE. Prefer defusedxml (an OPTIONAL hardening dep)
    when installed; otherwise use stdlib ET — which does NOT resolve external entities — plus a guard rejecting any
    internal <!ENTITY> declaration (the billion-laughs vector). Deterministic; no network (external DTDs never fetched).
    NCBI efetch XML uses a DOCTYPE with an external DTD but no internal <!ENTITY> defs + only predefined entities
    (&amp; etc.), so real responses parse cleanly."""
    text = xml_text or ""
    try:
        import defusedxml.ElementTree as _DET  # optional; best-in-class hardening
        return _DET.fromstring(text)
    except ImportError:
        pass
    if re.search(r"<!ENTITY", text, re.IGNORECASE):
        raise ValueError("refusing XML with internal entity declarations (billion-laughs guard)")
    return ET.fromstring(text)


def _year_from_pubdate(pubdate) -> int | None:
    if pubdate is None:
        return None
    y = pubdate.findtext("Year")
    if y and y.strip().isdigit():
        return int(y.strip())
    md = pubdate.findtext("MedlineDate") or ""
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", md)
    return int(m.group(1)) if m else None


def parse_efetch_xml(xml_text: str) -> list:
    """Parse an E-utilities efetch (db=pubmed, retmode=xml) response into record dicts. Pure/deterministic."""
    out = []
    try:
        root = _safe_fromstring(xml_text)
    except (ET.ParseError, ValueError):
        return out
    for cit in root.findall(".//MedlineCitation"):
        pmid = (cit.findtext("PMID") or "").strip()
        art = cit.find("Article")
        title = ((art.findtext("ArticleTitle") if art is not None else "") or "").strip()
        abstract = " ".join(
            (t.text or "").strip() for t in cit.findall(".//Abstract/AbstractText")
        ).strip()
        mesh, seen = [], set()
        for d in cit.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
            name = (d.text or "").strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                mesh.append(name)
        year = _year_from_pubdate(cit.find(".//PubDate"))
        out.append({"pmid": pmid, "title": title, "abstract": abstract, "mesh": mesh, "year": year})
    return out


def mesh_concept_list(record) -> list:
    """The record's MeSH descriptor names as the concept list (deduped case-insensitively, first-seen). Pure."""
    out, seen = [], set()
    for m in (record or {}).get("mesh") or []:
        t = str(m).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def normalize_pubmed_record(record) -> dict:
    """Corpus-builder shape: id=PMID (provenance key), concepts=MeSH list. Pure."""
    r = record or {}
    return {"id": str(r.get("pmid") or ""), "title": r.get("title") or "", "abstract": r.get("abstract") or "",
            "concepts": mesh_concept_list(r), "year": r.get("year")}


def parse_esearch_json(text) -> list:
    """PMID list from an E-utilities esearch (retmode=json) response. Pure; [] on malformed. """
    try:
        data = json.loads(text or "")
    except (ValueError, TypeError):
        return []
    ids = (((data or {}).get("esearchresult") or {}).get("idlist")) or []
    return [str(i) for i in ids if str(i).strip()]


import hashlib
import os
import pathlib

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_CONTACT_ENV = "NCBI_CONTACT_EMAIL"


def _default_get(url, params):
    import httpx  # lazy; only the LIVE path needs it
    r = httpx.get(url, params=params, timeout=60.0, follow_redirects=True)
    return (r.status_code, r.text)


def _contact_email(email=None) -> str:
    """The E-utilities contact address: explicit arg > $NCBI_CONTACT_EMAIL. FAIL-CLOSED — never falls back to a
    placeholder/fake, because NCBI policy is that the contact is a REAL address they can reach before throttling or
    blocking the caller; a fake would be worse than none. Mirrors fleet.py's OPENROUTER_API_KEY idiom (a required-
    from-env value -> a clear RuntimeError naming the var; SystemExit is this repo's CLI-entrypoint idiom, and this
    is a library module). Resolved at CALL time, never as a default arg / import-time read, so each caller (and each
    test) sets it per-run and no address is baked into the module."""
    resolved = str(email or os.environ.get(_CONTACT_ENV) or "").strip()
    if not resolved:
        raise RuntimeError(
            f"{_CONTACT_ENV} not set — NCBI E-utilities requires a real contact address so NCBI can reach the "
            f"caller before throttling/blocking. Set it to YOUR OWN email (never hardcode one): PowerShell "
            f"$env:{_CONTACT_ENV}='you@example.org' / POSIX export {_CONTACT_ENV}=you@example.org, or pass "
            f"email=... explicitly. Cached-only replays do not need it (no request reaches NCBI)."
        )
    return resolved


def esearch_pmids(term, *, retmax=500, get=None, tool="labcoat", email=None) -> list:
    """Resolve a PubMed query term to PMIDs (retmode=json). get(url,params)->(status,text) injected. Pure-shell.
    `email` defaults to $NCBI_CONTACT_EMAIL; absent -> RuntimeError before any request (see _contact_email)."""
    get = get or _default_get
    params = {"db": "pubmed", "term": term, "retmax": int(retmax), "retmode": "json",
              "tool": tool, "email": _contact_email(email)}
    status, text = get(f"{_EUTILS}/esearch.fcgi", params)
    if status != 200:
        raise RuntimeError(f"esearch HTTP {status}")
    return parse_esearch_json(text)


def efetch_records(pmids, *, get=None, sleep=None, cache_dir=None, batch=200,
                   tool="labcoat", email=None) -> list:
    """Fetch MEDLINE records for PMIDs (retmode=xml), batched + cached; sleep>=0.34s between LIVE batches only.
    `email` defaults to $NCBI_CONTACT_EMAIL, resolved per LIVE batch (see _contact_email) — so a fully-cached replay
    of a frozen corpus still runs offline with no contact set, while any batch that would actually hit NCBI fails
    closed rather than going out anonymously or under someone else's address."""
    ids = [str(p).strip() for p in (pmids or []) if str(p).strip()]
    if not ids:
        return []
    get = get or _default_get
    cdir = pathlib.Path(cache_dir) if cache_dir else None
    if cdir:
        cdir.mkdir(parents=True, exist_ok=True)
    out, first_live = [], True
    for i in range(0, len(ids), int(batch)):
        chunk = ids[i:i + int(batch)]
        key = hashlib.sha1((",".join(chunk)).encode("utf-8")).hexdigest()[:16]
        cache_file = (cdir / f"efetch_{key}.xml") if cdir else None
        if cache_file and cache_file.exists():
            text = cache_file.read_text(encoding="utf-8")
        else:
            if not first_live and sleep is not None:
                sleep(0.34)  # <=3 req/s, LIVE only
            first_live = False
            params = {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml", "tool": tool,
                      "email": _contact_email(email)}
            status, text = get(f"{_EUTILS}/efetch.fcgi", params)
            if status != 200:
                raise RuntimeError(f"efetch HTTP {status}")
            if cache_file:
                cache_file.write_text(text, encoding="utf-8")
        out.extend(parse_efetch_xml(text))
    return out
