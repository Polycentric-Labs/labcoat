"""labcoat N2 — answer-blind cross-literature ABC pipeline over a multi-topic PubMed/MeSH corpus. PURE inputs/pipeline
(stdlib) + an injected-get fetch shell (via pubmed_adapter). FREE. ADVISORY. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gap_channels as gc
import pubmed_adapter as pa


def build_concept_inputs(records_by_topic) -> tuple:
    """(concept_lists, doc_ids, doc_topic): per-doc lowercased MeSH minus check-tags; a PMID keeps its first-seen
    topic. Pure/deterministic; topic order = dict insertion order."""
    concept_lists, doc_ids, doc_topic = [], [], {}
    for topic, recs in (records_by_topic or {}).items():
        for r in (recs or []):
            pmid = str(r.get("id") or "").strip()
            if not pmid or pmid in doc_topic:
                continue
            cl = gc.strip_check_tags([str(c).strip().lower() for c in (r.get("concepts") or []) if str(c).strip()])
            if not cl:
                continue
            doc_topic[pmid] = topic
            doc_ids.append(pmid)
            concept_lists.append(cl)
    return concept_lists, doc_ids, doc_topic


def topic_degree_map(concept_lists, doc_ids, doc_topic) -> dict:
    """concept -> {topic -> intra-topic degree} (distinct co-tags within that topic's docs). Pure."""
    intra = {}
    for cl, did in zip(concept_lists, doc_ids):
        t = doc_topic.get(did)
        u = sorted(set(cl))
        for x in u:
            d = intra.setdefault(x, {}).setdefault(t, set())
            for y in u:
                if y != x:
                    d.add(y)
    return {c: {t: len(s) for t, s in td.items()} for c, td in intra.items()}


def run_pipeline(concept_lists, doc_ids, doc_topic, *, hub_percentile: float = 0.90, max_edges: int = 200000) -> dict:
    """Answer-blind: provenance -> topic-aware hub -> global cross-paper gap ranking. Pure."""
    edges = gc.cooccurrence_edges_from_concepts(concept_lists, max_edges=max_edges)
    prov = gc.cooccurrence_provenance(concept_lists, doc_ids)
    hub = gc.topic_aware_hub_bridges(edges, topic_degree_map(concept_lists, doc_ids, doc_topic),
                                     percentile=hub_percentile)
    ranked = gc.cross_paper_gaps_ranked(edges, prov, hub_bridges=hub)
    return {"ranked": ranked, "hub_bridges": hub, "n_edges": len(edges),
            "n_concepts": len({c for cl in concept_lists for c in cl})}


def fetch_topic_corpora(topic_terms, *, retmax=500, get=None, sleep=None, cache_dir=None) -> dict:
    """topic -> [normalized pubmed records]. Injected get/sleep (via pubmed_adapter). Shell (network)."""
    out = {}
    for topic, term in (topic_terms or {}).items():
        pmids = pa.esearch_pmids(term, retmax=retmax, get=get) if get else pa.esearch_pmids(term, retmax=retmax)
        recs = pa.efetch_records(pmids, get=get, sleep=sleep, cache_dir=cache_dir)
        out[topic] = [pa.normalize_pubmed_record(r) for r in recs]
    return out
