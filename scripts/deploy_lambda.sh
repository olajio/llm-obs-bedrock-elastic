#!/usr/bin/env bash
# Rebuilds build/function.zip and uploads it to the existing llm-obs-rag function.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FUNCTION_NAME="${FUNCTION_NAME:-llm-obs-rag}"
"$ROOT/scripts/build_lambda.sh"
aws lambda update-function-code --function-name "$FUNCTION_NAME" --zip-file "fileb://$ROOT/build/function.zip" --query 'LastModified' --output text
aws lambda wait function-updated-v2 --function-name "$FUNCTION_NAME"
echo "Deployed $FUNCTION_NAME"
