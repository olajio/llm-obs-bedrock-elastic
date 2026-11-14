# Logstash pipeline runbook (sample data)

## Restarting Logstash safely
Restart one node at a time with sudo systemctl restart logstash.
Wait until the Logstash log reports the pipeline as running before moving to the next node.
Check pipeline stats with curl -s localhost:9600/_node/stats/pipelines.

## Pipeline backpressure
If events per second drop while the persistent queue keeps growing, the output (usually Elasticsearch) is slower than the input.
Look for HTTP 429 responses in the Logstash log: Elasticsearch rejected bulk requests because its write thread pool queue is full.
Reduce pipeline.batch.size or add ingest capacity on the Elasticsearch side.

## Dead letter queue
Events that fail with mapping errors go to the dead letter queue when dead_letter_queue.enable is true.
Read them with the dead_letter_queue input plugin and fix the mapping before replaying them.
