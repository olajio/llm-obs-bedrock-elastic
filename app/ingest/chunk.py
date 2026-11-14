"""Split the runbook documents stored in S3 into overlapping chunks.

Usage (from the repo root, with .venv active):
    python app/ingest/chunk.py --bucket "$CORPUS_BUCKET"

Output: build/chunks.jsonl, one JSON object per line:
    {"chunk_id": "...", "source_doc": "...", "section": "...", "text": "...", "word_count": 123}
"""
import argparse
import json
import os

import boto3

CHUNK_WORDS = 200      # target words per chunk (roughly 270 tokens)
OVERLAP_WORDS = 40     # words repeated between neighbouring chunks of the same section
SUPPORTED_SUFFIXES = (".md", ".txt")


def list_documents(s3, bucket, prefix):
    """Yield the S3 key of every .md/.txt object under the prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(SUPPORTED_SUFFIXES):
                yield key


def read_document(s3, bucket, key):
    """Download one object and return its text."""
    resp = s3.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read().decode("utf-8", errors="replace")


def split_sections(text):
    """Split markdown into (heading, body) pairs; every heading line starts a new section."""
    sections = []
    heading = "Introduction"
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        is_heading = stripped.startswith("#") and stripped.lstrip("#").startswith(" ")
        if is_heading:
            if any(existing.strip() for existing in lines):
                sections.append((heading, "\n".join(lines).strip()))
            heading = stripped.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    if any(existing.strip() for existing in lines):
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def window_words(words, size, overlap):
    """Yield overlapping slices of a word list: [0:size], [size-overlap:2*size-overlap], ..."""
    if len(words) <= size:
        yield words
        return
    step = size - overlap
    for start in range(0, len(words), step):
        yield words[start:start + size]
        if start + size >= len(words):
            break


def chunk_document(source_doc, text):
    """Turn one document into a list of chunk dictionaries."""
    doc_title = os.path.splitext(os.path.basename(source_doc))[0]
    chunks = []
    for section, body in split_sections(text):
        for piece in window_words(body.split(), CHUNK_WORDS, OVERLAP_WORDS):
            number = len(chunks) + 1
            chunks.append({
                "chunk_id": f"{source_doc}#{number:04d}",
                "source_doc": source_doc,
                "section": section,
                # Prefixing the document and section names gives the embedding more context.
                "text": f"{doc_title} > {section}: " + " ".join(piece),
                "word_count": len(piece),
            })
    return chunks


def main():
    parser = argparse.ArgumentParser(description="Chunk runbooks from S3 into build/chunks.jsonl")
    parser.add_argument("--bucket", default=os.environ.get("CORPUS_BUCKET"),
                        help="S3 bucket holding the corpus (default: $CORPUS_BUCKET)")
    parser.add_argument("--prefix", default="runbooks/", help="S3 key prefix to read (default: runbooks/)")
    parser.add_argument("--out", default="build/chunks.jsonl", help="output file (default: build/chunks.jsonl)")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    if not args.bucket:
        parser.error("--bucket is required (or run: source .env)")

    s3 = boto3.client("s3", region_name=args.region)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    doc_count = 0
    chunk_count = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for key in list_documents(s3, args.bucket, args.prefix):
            source_doc = key[len(args.prefix):] if key.startswith(args.prefix) else key
            chunks = chunk_document(source_doc, read_document(s3, args.bucket, key))
            for chunk in chunks:
                out.write(json.dumps(chunk) + "\n")
            doc_count += 1
            chunk_count += len(chunks)
            print(f"  {key}: {len(chunks)} chunks")

    print(f"Read {doc_count} documents from s3://{args.bucket}/{args.prefix}")
    print(f"Wrote {chunk_count} chunks to {args.out}")
    if doc_count == 0:
        raise SystemExit("No .md or .txt files found - check --bucket and --prefix")


if __name__ == "__main__":
    main()
