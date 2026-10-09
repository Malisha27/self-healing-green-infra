# Runbook: Pod cannot pull its image (ImagePullBackOff / ErrImagePull)
## Symptoms
- Pod status ImagePullBackOff or ErrImagePull
- Events mention "manifest unknown", "not found", "unauthorized" or "i/o timeout"
## Root cause
Wrong image name/tag, missing registry credentials, or no network/DNS from the node.
## Fix
1. "i/o timeout" / "lookup ... no such host" = network or DNS problem on the node, not the app. Escalate to platform team.
2. "not found" / "manifest unknown" = wrong tag. Roll back to the previous working version. Action: rollback. Risk: medium.
3. "unauthorized" = registry credentials. Escalate (never handle secrets automatically).
## Verify
Pod starts, image pulled.
