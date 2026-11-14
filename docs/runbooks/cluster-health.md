# Cluster health triage runbook (sample data)

## Yellow cluster status
Yellow means every primary shard is assigned but at least one replica shard is not.
Run GET _cluster/allocation/explain to see why the replica is unassigned.
The usual causes are a node that left the cluster, a disk above the high watermark, or more replicas configured than there are data nodes.
Fix the cause first; Elasticsearch assigns the replica automatically once it can.

## Red cluster status
Red means at least one primary shard is unassigned, so some data cannot be searched or written.
Run GET _cat/shards?v&h=index,shard,prirep,state,unassigned.reason to find the affected index.
If the node holding the primary is gone for good and no replica exists, restore that index from the latest snapshot.

## Disk watermarks
The low watermark is 85 percent, the high watermark is 90 percent and the flood stage is 95 percent.
At flood stage Elasticsearch blocks writes to indices on that node; after you free disk space the block is removed automatically.
