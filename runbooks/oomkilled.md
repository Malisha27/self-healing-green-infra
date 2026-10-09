# Runbook: Pod killed for using too much memory (OOMKilled)
## Symptoms
- Container last state: terminated, reason OOMKilled, exit code 137
- Pod restarts under load
## Root cause
The memory limit is lower than what the app actually needs.
## Fix
1. Compare actual memory usage with the memory limit.
2. Increase the memory limit by 50% (max 2x). Action: increase_memory_limit. Risk: medium (needs approval in auto mode).
3. If memory keeps growing without bound (memory leak), escalate instead.
## Verify
No new OOMKilled events for 5 minutes, pod Ready.
