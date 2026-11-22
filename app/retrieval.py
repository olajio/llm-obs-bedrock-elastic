"""Retrieval for the llm-obs-rag chatbot: semantic search over the rag-corpus index."""
import os

from elasticsearch import Elasticsearch

ES_URL = os.environ["ES_URL"]
ES_API_KEY = os.environ["ES_API_KEY"]
ES_INDEX = os.environ.get("ES_INDEX", "rag-corpus")
ES_CA_CERT = os.environ.get("ES_CA_CERT") or None

_client = None


def get_client():
    """Create the Elasticsearch client once and reuse it (Lambda keeps it between warm requests)."""
    global _client
    if _client is None:
        options = {
            "api_key": ES_API_KEY,
            "request_timeout": 20,
            "retry_on_timeout": True,
            "max_retries": 2,
        }
        if ES_CA_CERT:
            options["ca_certs"] = ES_CA_CERT
        _client = Elasticsearch(ES_URL, **options)
    return _client


def build_query(question):
    # Elasticsearch 8.18+ and 9.x: a plain match query on a semantic_text field runs a semantic search.
    # Elasticsearch 8.15-8.17: replace the return line below with
    #     return {"semantic": {"field": "content", "query": question}}
    return {"match": {"content": question}}


def _text_of(content):
    # 8.18+ returns the original string; 8.15-8.17 returned {"text": ..., "inference": ...}.
    if isinstance(content, dict):
        return content.get("text", "")
    return content or ""


def retrieve(question, k=5):
    """Return the k most relevant chunks as dicts with text, source_doc, chunk_id and score."""
    resp = get_client().search(
        index=ES_INDEX,
        query=build_query(question),
        size=k,
        source_includes=["content", "source_doc", "chunk_id"],
    )
    results = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        results.append(
            {
                "text": _text_of(src.get("content")),
                "source_doc": src.get("source_doc", "unknown"),
                "chunk_id": src.get("chunk_id", hit["_id"]),
                "score": hit["_score"],
            }
        )
    return results
