"""
Nutanix VM Health Monitor
Connects to Nutanix Prism Element/Central via REST API v3,
polls VM metrics, and generates an automated health report.

Usage:
    python monitor.py --host <prism-ip> --user <admin> --pass <password>
    python monitor.py --demo          # runs with mock data (no Nutanix needed)
"""

import argparse
import json
import sys
import os
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ── Thresholds ───────────────────────────────────────────────────────────────
CPU_WARN_PCT    = 80
MEMORY_WARN_PCT = 85
REPORT_DIR      = "reports"

# ── Mock data (demo mode) ────────────────────────────────────────────────────
MOCK_VMS = [
    {"name": "web-prod-01",   "power_state": "ON",  "cpu_pct": 72,  "mem_pct": 61,  "ip": "10.0.1.10"},
    {"name": "db-prod-01",    "power_state": "ON",  "cpu_pct": 88,  "mem_pct": 91,  "ip": "10.0.1.11"},  # CPU + MEM alert
    {"name": "app-staging-01","power_state": "ON",  "cpu_pct": 34,  "mem_pct": 45,  "ip": "10.0.1.12"},
    {"name": "backup-agent",  "power_state": "OFF", "cpu_pct": 0,   "mem_pct": 0,   "ip": "N/A"},
    {"name": "monitor-01",    "power_state": "ON",  "cpu_pct": 12,  "mem_pct": 28,  "ip": "10.0.1.14"},
]


# ── Nutanix API client ────────────────────────────────────────────────────────
class NutanixClient:
    def __init__(self, host, username, password, port=9440):
        self.base_url = f"https://{host}:{port}/api/nutanix/v3"
        self.auth = (username, password)
        self.session = requests.Session()
        self.session.verify = False  # self-signed cert in lab

    def _post(self, endpoint, payload):
        url = f"{self.base_url}/{endpoint}"
        resp = self.session.post(url, auth=self.auth, json=payload,
                                 headers={"Content-Type": "application/json"}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def list_vms(self):
        """Fetch all VMs via Prism API v3 (paginated)."""
        payload = {"kind": "vm", "length": 100, "offset": 0}
        data = self._post("vms/list", payload)
        return data.get("entities", [])

    def get_vm_stats(self, vm_uuid):
        """Get runtime stats for a single VM."""
        url = f"{self.base_url}/vms/{vm_uuid}"
        resp = self.session.get(url, auth=self.auth, timeout=15)
        resp.raise_for_status()
        return resp.json()


# ── Health check logic ────────────────────────────────────────────────────────
def parse_live_vms(entities):
    """Normalise Prism v3 VM entities into our flat dict format."""
    vms = []
    for e in entities:
        spec    = e.get("spec", {})
        status  = e.get("status", {})
        res     = status.get("resources", {})
        stats   = res.get("stats", {})

        cpu_pct = round(float(stats.get("hypervisor_cpu_usage_ppm", 0)) / 10000, 1)
        mem_b   = float(stats.get("memory_usage_bytes", 0))
        mem_tot = float(res.get("memory_size_mib", 1)) * 1024 * 1024
        mem_pct = round((mem_b / mem_tot) * 100, 1) if mem_tot else 0

        nics    = res.get("nic_list", [])
        ip      = "N/A"
        if nics and nics[0].get("ip_endpoint_list"):
            ip = nics[0]["ip_endpoint_list"][0].get("ip", "N/A")

        vms.append({
            "name":        spec.get("name", "unknown"),
            "power_state": res.get("power_state", "UNKNOWN").upper(),
            "cpu_pct":     cpu_pct,
            "mem_pct":     mem_pct,
            "ip":          ip,
        })
    return vms


def evaluate_health(vms):
    """Tag each VM as HEALTHY / WARNING / CRITICAL / OFF."""
    results = []
    for vm in vms:
        if vm["power_state"] != "ON":
            status = "OFF"
        elif vm["cpu_pct"] >= CPU_WARN_PCT or vm["mem_pct"] >= MEMORY_WARN_PCT:
            status = "WARNING" if max(vm["cpu_pct"], vm["mem_pct"]) < 95 else "CRITICAL"
        else:
            status = "HEALTHY"
        results.append({**vm, "status": status})
    return results


# ── Report generator ──────────────────────────────────────────────────────────
def generate_html_report(results, cluster="nutanix-lab"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    healthy = sum(1 for r in results if r["status"] == "HEALTHY")
    warnings = sum(1 for r in results if r["status"] in ("WARNING", "CRITICAL"))
    off = sum(1 for r in results if r["status"] == "OFF")

    rows = ""
    for r in sorted(results, key=lambda x: x["status"]):
        colour = {"HEALTHY": "#d4edda", "WARNING": "#fff3cd",
                  "CRITICAL": "#f8d7da", "OFF": "#e2e3e5"}.get(r["status"], "#fff")
        rows += f"""
        <tr style="background:{colour}">
          <td>{r['name']}</td>
          <td>{r['power_state']}</td>
          <td>{r['cpu_pct']}%</td>
          <td>{r['mem_pct']}%</td>
          <td>{r['ip']}</td>
          <td><b>{r['status']}</b></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Nutanix VM Health Report</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 32px; }}
  h1 {{ color: #1e2c5e; }} h3 {{ color: #555; }}
  .summary {{ display:flex; gap:24px; margin:16px 0 24px; }}
  .card {{ padding:12px 24px; border-radius:8px; font-size:18px; font-weight:bold; }}
  .green {{ background:#d4edda; color:#155724; }}
  .yellow {{ background:#fff3cd; color:#856404; }}
  .gray  {{ background:#e2e3e5; color:#383d41; }}
  table {{ border-collapse:collapse; width:100%; }}
  th {{ background:#1e2c5e; color:#fff; padding:10px 14px; text-align:left; }}
  td {{ padding:9px 14px; border-bottom:1px solid #dee2e6; }}
</style></head>
<body>
  <h1>Nutanix VM Health Report</h1>
  <h3>Cluster: {cluster} &nbsp;|&nbsp; Generated: {ts}</h3>
  <div class="summary">
    <div class="card green">✔ {healthy} Healthy</div>
    <div class="card yellow">⚠ {warnings} Warning / Critical</div>
    <div class="card gray">○ {off} Off</div>
  </div>
  <table>
    <tr><th>VM Name</th><th>Power</th><th>CPU %</th><th>Memory %</th><th>IP</th><th>Status</th></tr>
    {rows}
  </table>
  <p style="color:#888;font-size:13px;margin-top:24px">
    CPU threshold: {CPU_WARN_PCT}% &nbsp;|&nbsp; Memory threshold: {MEMORY_WARN_PCT}%
  </p>
</body></html>"""
    return html


def save_report(html, cluster):
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(REPORT_DIR, f"health_{cluster}_{ts}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def send_email_alert(results, smtp_host, smtp_port, sender, recipient, password):
    """Send email alert if any VM is in WARNING/CRITICAL state."""
    bad = [r for r in results if r["status"] in ("WARNING", "CRITICAL")]
    if not bad:
        print("  [email] No alerts to send.")
        return

    body = "The following VMs exceeded health thresholds:\n\n"
    for r in bad:
        body += f"  • {r['name']}: CPU={r['cpu_pct']}%  MEM={r['mem_pct']}%  [{r['status']}]\n"

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = f"[Nutanix Alert] {len(bad)} VM(s) need attention"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"  [email] Alert sent to {recipient}")
    except Exception as e:
        print(f"  [email] Failed: {e}")


# ── CLI entry point ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Nutanix VM Health Monitor")
    parser.add_argument("--host",  help="Prism IP/hostname")
    parser.add_argument("--user",  help="Prism username", default="admin")
    parser.add_argument("--pass",  dest="password", help="Prism password")
    parser.add_argument("--demo",  action="store_true", help="Run with mock data")
    parser.add_argument("--email", help="Alert recipient email (optional)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Nutanix VM Health Monitor")
    print("=" * 60)

    if args.demo:
        print("  [mode] DEMO — using mock cluster data\n")
        vms    = MOCK_VMS
        cluster = "demo-cluster"
    else:
        if not REQUESTS_AVAILABLE:
            print("ERROR: `requests` not installed. Run: pip install requests")
            sys.exit(1)
        if not args.host or not args.password:
            print("ERROR: --host and --pass required (or use --demo)")
            sys.exit(1)
        print(f"  [mode] LIVE — connecting to {args.host}\n")
        client   = NutanixClient(args.host, args.user, args.password)
        entities = client.list_vms()
        vms      = parse_live_vms(entities)
        cluster  = args.host

    results = evaluate_health(vms)

    # Print summary table
    print(f"  {'VM Name':<25} {'Power':<8} {'CPU%':<8} {'MEM%':<8} {'Status'}")
    print("  " + "-" * 60)
    for r in results:
        flag = "⚠ " if r["status"] in ("WARNING", "CRITICAL") else "  "
        print(f"  {flag}{r['name']:<23} {r['power_state']:<8} {r['cpu_pct']:<8} {r['mem_pct']:<8} {r['status']}")

    # Save HTML report
    html = generate_html_report(results, cluster)
    path = save_report(html, cluster)
    print(f"\n  Report saved → {path}")
    print("=" * 60)


if __name__ == "__main__":
    main()