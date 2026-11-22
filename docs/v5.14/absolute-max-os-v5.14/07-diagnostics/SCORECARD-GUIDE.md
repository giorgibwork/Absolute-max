# Scorecard & Evidence Guide — v5.2.0

## Minimum evidence for any “improved” claim

1. **Positive probe** — intended case succeeds (command + exit 0 + short output proof)
2. **Negative probe** — bad case fails closed (non-zero exit or quarantine)
3. **Hold-out** — at least one related case not used to design the change
4. **Receipt** — timestamp, version 5.2.0, and hashes when available

## Preferred scorecard shape (JSON)

```json
{
  "primitive": "name",
  "positive_command": "...",
  "negative_command": "...",
  "trials": 3,
  "positive_pass": true,
  "negative_failure_caught": true,
  "median_latency_ms": 0,
  "notes": "optional"
}
```

## Multi-step agent tasks (add these)

Single RPC latency is not enough. Include at least:

- Store memory → recall → confirm guard still blocks poison
- Short tool chain (search or scrape → summarize with origin tags → SPR)
- One deliberate failure path that must not be reported as success

## Anti-patterns

- All latencies identical (~30 ms) with no workload variety
- Only positive tests
- Claims without commands that another agent can re-run
