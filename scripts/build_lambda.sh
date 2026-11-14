#!/usr/bin/env bash
# Builds build/function.zip for the llm-obs-rag Lambda. Works for every phase:
# it packs every app/*.py (except local_*.py test helpers), any app/*.crt CA file,
# corpus.jsonl when it exists, and the packages listed in app/requirements.txt,
# all at the ROOT of the zip (Lambda requires that).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="$ROOT/build/package"
ZIP="$ROOT/build/function.zip"

rm -rf "$PKG" "$ZIP"
mkdir -p "$PKG"

# Install runtime dependencies only if requirements.txt lists any (Phase 1 has none).
# The --platform flags fetch Linux x86_64 wheels even when you build on a Mac.
if grep -Ev '^[[:space:]]*(#|$)' "$ROOT/app/requirements.txt" | grep -q .; then
  python3 -m pip install --quiet --requirement "$ROOT/app/requirements.txt" --target "$PKG" --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all:
fi

for f in "$ROOT"/app/*.py "$ROOT"/app/*.crt; do
  [ -e "$f" ] || continue
  case "$(basename "$f")" in local_*.py) continue ;; esac
  cp "$f" "$PKG/"
done

if [ -f "$ROOT/corpus.jsonl" ]; then
  cp "$ROOT/corpus.jsonl" "$PKG/"
else
  echo "NOTE: corpus.jsonl not found - fine from Phase 2 on; in Phase 1 run app/ingest/embed.py first" >&2
fi

(cd "$PKG" && zip -qr "$ZIP" .)

echo "Built $ZIP ($(du -h "$ZIP" | cut -f1))"
unzip -l "$ZIP" | tail -n 8
