"""Run the Lambda handler on your laptop with a fake API Gateway event.

Usage (from the repo root, with .venv active):
    python app/local_test.py
    python app/local_test.py "How do I fix a yellow cluster?"
"""
import json
import logging
import os
import sys

# Point the handler at the embeddings file in the repo root (in Lambda it sits next to handler.py).
os.environ.setdefault("CORPUS_PATH", "corpus.jsonl")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import handler  # noqa: E402 - must be imported after CORPUS_PATH is set

question = sys.argv[1] if len(sys.argv) > 1 else "What is the ILM policy for logs-mainframe-prod?"
event = {
    "version": "2.0",
    "routeKey": "POST /chat",
    "rawPath": "/chat",
    "headers": {"content-type": "application/json"},
    "body": json.dumps({"query": question}),
    "isBase64Encoded": False,
}
result = handler.lambda_handler(event, None)
print("statusCode:", result["statusCode"])
print(json.dumps(json.loads(result["body"]), indent=2))
