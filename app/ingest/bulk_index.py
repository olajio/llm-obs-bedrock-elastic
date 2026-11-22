#!/usr/bin/env python3
"""Bulk-index the Phase 1 chunk file into the rag-corpus index.

Usage:
    python app/ingest/bulk_index.py corpus.jsonl

Needs these environment variables (set in Phase 2, Step 0):
    ES_URL, ES_ADMIN_USER, ES_ADMIN_PW, and optionally ES_CA_CERT
"""
import json
import os
import sys
from datetime import datetime, timezone

from elasticsearch import Elasticsearch, helpers

ES_URL = os.environ["ES_URL"]
ES_ADMIN_USER = os.environ.get("ES_ADMIN_USER", "elastic")
ES_ADMIN_PW = os.environ["ES_ADMIN_PW"]
ES_CA_CERT = os.environ.get("ES_CA_CERT") or None
INDEX = os.environ.get("ES_INDEX", "rag-corpus")
BATCH_SIZE = 20  # documents per bulk request; lower it if you see timeouts or 429 errors


def connect():
    options = {"basic_auth": (ES_ADMIN_USER, ES_ADMIN_PW), "request_timeout": 300}
    if ES_CA_CERT:
        options["ca_certs"] = ES_CA_CERT
    es = Elasticsearch(ES_URL, **options)
    info = es.info()
    print(f"Connected to cluster '{info['cluster_name']}' running Elasticsearch {info['version']['number']}")
    return es


def actions(path):
    """Yield one bulk 'index' action per line of the JSONL file."""
    now = datetime.now(timezone.utc).isoformat()
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping line {line_no}: not valid JSON ({exc})")
                continue
            yield {
                "_op_type": "index",
                "_index": INDEX,
                "_id": doc["chunk_id"],
                "_source": {
                    "content": doc["text"],
                    "source_doc": doc["source_doc"],
                    "chunk_id": doc["chunk_id"],
                    "section": doc.get("section"),
                    "ingested_at": now,
                },
            }


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    es = connect()
    if not es.indices.exists(index=INDEX):
        sys.exit(f"Index '{INDEX}' does not exist yet. Run Phase 2, Step 3 first.")

    ok_count = 0
    failures = []
    for ok, result in helpers.streaming_bulk(
        es,
        actions(path),
        chunk_size=BATCH_SIZE,
        raise_on_error=False,
        max_retries=3,
        initial_backoff=5,
    ):
        if ok:
            ok_count += 1
        else:
            failures.append(result)
        done = ok_count + len(failures)
        if done % BATCH_SIZE == 0:
            print(f"  ...{ok_count} indexed, {len(failures)} failed")

    es.indices.refresh(index=INDEX)
    total = es.count(index=INDEX)["count"]
    print(f"Done: {ok_count} indexed, {len(failures)} failed. '{INDEX}' now holds {total} documents.")
    for failure in failures[:5]:
        print(json.dumps(failure, indent=2))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
