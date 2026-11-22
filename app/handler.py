"""llm-obs-rag Lambda: answers a question using Elasticsearch retrieval + Bedrock Claude."""
import base64
import json
import os

import boto3

from retrieval import retrieve

CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
TOP_K = int(os.environ.get("TOP_K", "5"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "512"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.2"))
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

SYSTEM_PROMPT = (
    "You are an assistant for Elastic operations runbooks. "
    "Answer ONLY from the numbered context passages you are given and cite them like [1]. "
    "If the passages do not contain the answer, say you don't know."
)


def _response(status, payload):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _parse_question(event):
    """Pull the 'query' string out of an API Gateway HTTP API event."""
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    question = (data.get("query") or "").strip()
    return question or None


def build_prompt(question, chunks):
    context = "\n\n".join(
        f"[{i}] (source: {c['source_doc']})\n{c['text']}" for i, c in enumerate(chunks, start=1)
    )
    return f"Context passages:\n\n{context}\n\nQuestion: {question}"


def lambda_handler(event, context):
    question = _parse_question(event)
    if not question:
        return _response(400, {"error": 'Send a JSON body like {"query": "your question"}'})

    chunks = retrieve(question, TOP_K)
    resp = bedrock.converse(
        modelId=CHAT_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": build_prompt(question, chunks)}]}],
        inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
    )
    answer = resp["output"]["message"]["content"][0]["text"]
    return _response(
        200,
        {
            "answer": answer,
            "sources": [
                {"source_doc": c["source_doc"], "chunk_id": c["chunk_id"], "score": c["score"]}
                for c in chunks
            ],
            "usage": resp.get("usage", {}),
        },
    )
