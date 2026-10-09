# Runbook: Workload is over-provisioned (wasting CPU, money and energy)
## Symptoms
- CPU requested is much higher than CPU used (for example used < 10% of requested for 30+ minutes)
- Many replicas of an idle service
## Root cause
Requests and replicas were set high "just in case", usually out of fear of failures.
## Fix
1. Only rightsize workloads that the self-healing agent can recover (MTTR proven low).
2. Set CPU request to about 2x the observed peak usage, never below the floor of 50m.
3. Reduce replicas to the minimum that meets the SLO (never below 1).
4. Action: rightsize. Risk: medium. Always keep a rollback.
## Verify
SLO still met (error rate and latency) for 30 minutes after the change.
