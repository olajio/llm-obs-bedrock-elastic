"""Retrieval quality check for rag-corpus.

For each test question, checks whether a chunk from the expected source document
appears in the top K results. Edit TEST_CASES to match your own runbooks.

Usage (from the app/ folder, with ES_URL, ES_API_KEY and ES_CA_CERT set):
    python eval_retrieval.py
"""
import sys

from retrieval import retrieve

K = 5
PASS_MARK = 0.8  # at least 8 of 10 questions should find the right document

# (question, a word that appears in the expected source_doc file name)
TEST_CASES = [
    ("What is the ILM policy for logs-mainframe-prod?", "ilm"),
    ("Which ILM policy does logs-app-prod use?", "ilm"),
    ("What do I do if an index is stuck in an ILM phase?", "ilm"),
    ("Why is my cluster yellow?", "cluster"),
    ("How do I restart Logstash safely?", "logstash"),
    ("What does pipeline backpressure look like?", "logstash"),
    ("What happens to events that fail with mapping errors?", "logstash"),
    ("What does a red cluster mean?", "cluster"),
    ("What is flood stage disk watermark?", "cluster"),
    ("How long are logs-mainframe-prod indices kept before deletion?", "ilm"),
]


def main():
    hits = 0
    for question, expected in TEST_CASES:
        results = retrieve(question, K)
        sources = [r["source_doc"] for r in results]
        found = any(expected.lower() in s.lower() for s in sources)
        hits += found
        top = f"{sources[0]} ({results[0]['score']:.3f})" if results else "no results"
        print(f"{'PASS' if found else 'MISS'}  {question}")
        print(f"      expected '{expected}', top hit: {top}")
    rate = hits / len(TEST_CASES)
    print(f"\nHit rate @{K}: {hits}/{len(TEST_CASES)} = {rate:.0%} (target {PASS_MARK:.0%})")
    sys.exit(0 if rate >= PASS_MARK else 1)


if __name__ == "__main__":
    main()
