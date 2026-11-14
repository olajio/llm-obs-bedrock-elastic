"""Embed every chunk in build/chunks.jsonl with Amazon Titan Text Embeddings V2.

Usage (from the repo root, with .venv active):
    python app/ingest/embed.py

Output: corpus.jsonl (repo root), one JSON object per line:
    {"chunk_id", "source_doc", "section", "text", "embedding": [1024 floats]}
Phase 1 packs this file into the Lambda; Phase 2 bulk-indexes it into Elasticsearch.
"""
import argparse
import json
import time

import boto3
from botocore.config import Config

MODEL_ID = "amazon.titan-embed-text-v2:0"
DIMENSIONS = 1024  # Titan V2 also supports 512 and 256; Phase 2's index must use the same number


def embed_text(client, text):
    """Return (vector, input_token_count) for one piece of text."""
    body = json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True})
    resp = client.invoke_model(
        modelId=MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(resp["body"].read())  # the body is a stream: read it once
    return payload["embedding"], payload.get("inputTextTokenCount", 0)


def main():
    parser = argparse.ArgumentParser(description="Embed chunks with Titan Text Embeddings V2")
    parser.add_argument("--input", default="build/chunks.jsonl", help="chunks file from chunk.py")
    parser.add_argument("--out", default="corpus.jsonl", help="output file (default: corpus.jsonl in the repo root)")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    # Adaptive retries back off automatically if Bedrock throttles you (ThrottlingException).
    client = boto3.client(
        "bedrock-runtime",
        region_name=args.region,
        config=Config(retries={"max_attempts": 8, "mode": "adaptive"}),
    )

    with open(args.input, "r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    if not chunks:
        raise SystemExit(f"{args.input} is empty - run app/ingest/chunk.py first")

    total_tokens = 0
    started = time.time()
    with open(args.out, "w", encoding="utf-8") as out:
        for i, chunk in enumerate(chunks, start=1):
            vector, tokens = embed_text(client, chunk["text"])
            total_tokens += tokens
            record = {
                "chunk_id": chunk["chunk_id"],
                "source_doc": chunk["source_doc"],
                "section": chunk["section"],
                "text": chunk["text"],
                "embedding": vector,
            }
            out.write(json.dumps(record) + "\n")
            print(f"  [{i}/{len(chunks)}] {chunk['chunk_id']} ({tokens} tokens)")

    elapsed = time.time() - started
    print(f"Embedded {len(chunks)} chunks in {elapsed:.1f}s; total input tokens: {total_tokens}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
