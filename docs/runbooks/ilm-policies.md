# ILM policies runbook (sample data)

## logs-mainframe-prod
The logs-mainframe-prod data stream uses the ILM policy named mainframe-logs-90d.
Hot phase: roll over at 50 GB primary shard size or 1 day, whichever comes first.
Warm phase: after 7 days, force merge to 1 segment and shrink to 1 primary shard.
Cold phase: after 30 days, move to cold nodes and mark the index read-only.
Delete phase: delete indices 90 days after rollover.
To check the policy, run GET _ilm/policy/mainframe-logs-90d in Kibana Dev Tools.

## logs-app-prod
The logs-app-prod data stream uses the ILM policy app-logs-30d.
Hot phase: roll over at 30 GB primary shard size or 1 day. Delete phase: delete 30 days after rollover.

## Troubleshooting ILM
If an index is stuck in a phase, run GET <index>/_ilm/explain and read the step and step_info fields.
A common cause is a shrink step waiting for every shard to be allocated to a single node.
After fixing the cause, run POST <index>/_ilm/retry to resume the policy.
