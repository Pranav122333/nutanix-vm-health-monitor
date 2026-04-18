# Nutanix VM Health Monitor

A Python tool that connects to **Nutanix Prism Element / Prism Central** via the REST API v3, polls VM health metrics (CPU, memory, power state), evaluates thresholds, and generates an **automated HTML health report**. Optionally sends email alerts when VMs exceed warning thresholds.

Built as a practical CloudOps automation project aligned with Nutanix iResident/iConsultant workflows.

---

## Features

- Connects to Nutanix Prism via REST API v3 (authenticated, HTTPS)
- Lists all VMs and retrieves real-time CPU / memory utilisation
- Evaluates health: `HEALTHY` / `WARNING` / `CRITICAL` / `OFF`
- Generates a timestamped HTML report saved to `reports/`
- Optional SMTP email alert for degraded VMs
- `--demo` flag to run offline with mock data (no Nutanix cluster needed)

---

## Demo (no Nutanix required)

```bash
pip install requests
python monitor.py --demo
```

Sample output:
```
============================================================
  Nutanix VM Health Monitor
============================================================
  [mode] DEMO — using mock cluster data

  VM Name                   Power    CPU%     MEM%     Status
  ------------------------------------------------------------
  web-prod-01               ON       72       61       HEALTHY
  ⚠ db-prod-01             ON       88       91       WARNING
  app-staging-01            ON       34       45       HEALTHY
  backup-agent              OFF      0        0        OFF
  monitor-01                ON       12       28       HEALTHY

  Report saved → reports/health_demo-cluster_20260417_120000.html
```

---

## Live Usage (Nutanix CE / Prism)

```bash
python monitor.py --host 192.168.1.100 --user admin --pass YourPassword
```

With email alerts:
```bash
python monitor.py --host 192.168.1.100 --user admin --pass YourPassword \
  --email ops-team@company.com
```

---

## Project Structure

```
nutanix-vm-health-monitor/
├── monitor.py          # Main script
├── requirements.txt    # Dependencies
└── reports/            # Auto-created, stores HTML reports
```

---

## Tech Stack

- Python 3.8+
- Nutanix Prism REST API v3
- `requests` for HTTP/HTTPS API calls
- `smtplib` for email alerts
- Zero external UI dependencies — pure HTML report generation

---

## Concepts Demonstrated

| Concept | How |
|---|---|
| REST API authentication | Basic auth over HTTPS, session reuse |
| JSON response parsing | Nested key extraction from Prism v3 entities |
| Threshold-based alerting | CPU/memory evaluation with configurable limits |
| Report generation | Dynamic HTML with colour-coded status rows |
| Cloud ops mindset | Mimics daily health-check workflow of Nutanix iResidents |

---

## Related Certifications

- Nutanix Certified Associate (NCA)
- Red Hat System Administration I & II (RH124, RH134)