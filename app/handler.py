"""AWS Lambda handler for the llm-obs RAG chatbot (Phase 1 version).

What happens on each request:
  1. Read the question from the API Gateway HTTP API event body: {"query": "..."}.
  2. Embed the question with Amazon Titan Text Embeddings V2.
  3. Retrieve the TOP_K most similar runbook chunks. Phase 1 does an in-memory cosine
     search over corpus.jsonl packed in the zip; Phase 2 replaces retrieve()
     with an Elasticsearch semantic query.
  4. Ask Claude Haiku 4.5 (Bedrock Converse API) to answer using only those chunks.
  5. Return the answer, its sources, token usage and timings as JSON.
"""
import base64
import json
import logging
import math
import os
import time

import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---- Configuration: Lambda environment variables, with defaults that match this guide ----
REGION = os.environ.get("AWS_REGION", "us-east-1")  # Lambda sets AWS_REGION automatically
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
TOP_K = int(os.environ.get("TOP_K", "4"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "512"))
MAX_QUESTION_CHARS = 2000
CORPUS_PATH = os.environ.get(
    "CORPUS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus.jsonl"),
)

SYSTEM_PROMPT = (
    "You are an assistant for Elastic Stack operations runbooks. "
    "Answer the question using ONLY the context passages provided. "
    "If the passages do not contain the answer, say you don't know - do not guess. "
    "Keep answers short and practical, and end with the source document names you used in square brackets."
)

# ---- Created once per cold start, then reused by every request this container serves ----
bedrock = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    config=Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=25, connect_timeout=5),
)


def _load_corpus(path):
    """Load the chunk records and pre-compute each vector's length for cosine similarity."""
    corpus = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            record["_norm"] = math.sqrt(sum(x * x for x in record["embedding"])) or 1.0
            corpus.append(record)
    logger.info("Loaded %d chunks from %s", len(corpus), path)
    return corpus


CORPUS = _load_corpus(CORPUS_PATH)


def embed(text):
    """Return Titan's 1024-number embedding for one piece of text."""
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text, "dimensions": 1024, "normalize": True}),
    )
    return json.loads(resp["body"].read())["embedding"]


def cosine(a, b, b_norm):
    """Cosine similarity between vectors a and b (b's length already computed)."""
    dot = sum(x * y for x, y in zip(a, b))
    a_norm = math.sqrt(sum(x * x for x in a)) or 1.0
    return dot / (a_norm * b_norm)


def retrieve(question, k=TOP_K):
    """Return the k chunks most similar to the question. Phase 2 replaces this function's body."""
    q_vec = embed(question)
    scored = [(cosine(q_vec, rec["embedding"], rec["_norm"]), rec) for rec in CORPUS]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "chunk_id": rec["chunk_id"],
            "source_doc": rec["source_doc"],
            "section": rec.get("section", ""),
            "text": rec["text"],
            "score": round(score, 4),
        }
        for score, rec in scored[:k]
    ]


def build_prompt(question, chunks):
    """Put the retrieved chunks in front of the question, each tagged with its source."""
    passages = []
    for i, chunk in enumerate(chunks, start=1):
        passages.append(f'<passage index="{i}" source="{chunk["source_doc"]}">' + chunk["text"] + "</passage>")
    return "Context passages:\n" + "\n".join(passages) + f"\n\nQuestion: {question}"


def ask_llm(prompt):
    """Call Claude through the Converse API; return (answer, usage, stop_reason, latency_ms)."""
    resp = bedrock.converse(
        modelId=CHAT_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.2},
    )
    answer = "".join(block.get("text", "") for block in resp["output"]["message"]["content"])
    return answer, resp["usage"], resp.get("stopReason"), resp.get("metrics", {}).get("latencyMs")


def _response(status_code, body):
    """Shape a return value the way API Gateway expects it."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _parse_question(event):
    """Pull the query string out of an API Gateway HTTP API (payload v2.0) event."""
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    data = json.loads(body) if isinstance(body, str) else body
    if not isinstance(data, dict):
        raise ValueError("body is not a JSON object")
    return str(data.get("query", "")).strip()


def lambda_handler(event, context):
    """Entry point: Lambda calls this once per request (Handler = handler.lambda_handler)."""
    started = time.perf_counter()
    try:
        question = _parse_question(event)
    except ValueError:
        return _response(400, {"error": 'Request body must be JSON like {"query": "your question"}'})
    if not question:
        return _response(400, {"error": 'Missing "query" field in the request body'})
    if len(question) > MAX_QUESTION_CHARS:
        return _response(400, {"error": f"Question longer than {MAX_QUESTION_CHARS} characters"})

    try:
        t0 = time.perf_counter()
        chunks = retrieve(question)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)
        answer, usage, stop_reason, model_latency_ms = ask_llm(build_prompt(question, chunks))
    except Exception as exc:  # log the full traceback, return a clean JSON 500
        logger.exception("RAG request failed")
        return _response(500, {"error": type(exc).__name__, "message": str(exc)})

    total_ms = int((time.perf_counter() - started) * 1000)
    # One structured log line per request. It deliberately omits the question text,
    # which may contain sensitive data (Phase 4 adds a redacting pipeline for that).
    logger.info(json.dumps({
        "event": "rag_request",
        "question_chars": len(question),
        "chunk_ids": [c["chunk_id"] for c in chunks],
        "model_id": CHAT_MODEL_ID,
        "input_tokens": usage.get("inputTokens"),
        "output_tokens": usage.get("outputTokens"),
        "stop_reason": stop_reason,
        "retrieval_ms": retrieval_ms,
        "model_latency_ms": model_latency_ms,
        "total_ms": total_ms,
    }))
    return _response(200, {
        "answer": answer,
        "sources": [
            {"chunk_id": c["chunk_id"], "source_doc": c["source_doc"], "section": c["section"], "score": c["score"]}
            for c in chunks
        ],
        "model_id": CHAT_MODEL_ID,
        "usage": usage,
        "stop_reason": stop_reason,
        "latency_ms": {"retrieval": retrieval_ms, "model": model_latency_ms, "total": total_ms},
    })
