"""Run the Lambda handler locally with a fake API Gateway event.

Usage: python local_invoke.py "your question here"
"""
import json
import sys

from handler import lambda_handler

question = " ".join(sys.argv[1:]) or "What is the ILM policy for logs-mainframe-prod?"
event = {
    "body": json.dumps({"query": question}),
    "isBase64Encoded": False,
    "headers": {"content-type": "application/json", "x-user-id": "local-test"},
}
result = lambda_handler(event, None)
print(f"HTTP {result['statusCode']}")
print(json.dumps(json.loads(result["body"]), indent=2))
