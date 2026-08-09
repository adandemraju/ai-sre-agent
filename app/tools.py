#Mock Tools


#return plausible canned log snippet
#vary it by alert type
def query_logs(service,alert_type) -> str:
    canned = {
        "high_cpu": f"[{service}] worker-pool exhausted, 47 requests queued",
        "disk_full": f"[{service}] write failed: no space left on device",
        "service_down": f"[{service}] connection refused on :8080",
    }

    return canned.get(alert_type,f"[{service}] no matching error patterns in the last 15m")

def query_metrics(service: str, alert_type: str) -> str:
    canned = {
        "high_cpu": f"[{service}] cpu_usage=95% p99_latency_ms=2100 gc_pause_ms=1200",
        "disk_full": f"[{service}] disk_usage=97% inode_usage=61%",
        "service_down": f"[{service}] healthy_replicas=0/3 restarts_last_hour=6",
    }
    return canned.get(alert_type, f"[{service}] cpu_usage=normal mem_usage=normal")

from pathlib import Path
RUNBOOK_DIR = Path("runbooks")

def retrieve_runbook(alert_type: str) -> str:
    path = RUNBOOK_DIR / f"{alert_type}.md"
    if path.exists():
        return path.read_text()
    return "No runbook on file for this alert type. Use general SRE judgment."

import os
def remediate_action(action: str, service: str) -> str:
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    if dry_run:
        return f"[DRY RUN] Would execute '{action}' on service '{service}'. No changes made."
    return f"Executed '{action}' on service '{service}'. Service restored."


def notify_slack(message) -> str:
    print(message)