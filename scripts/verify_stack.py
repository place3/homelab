"""Wait for scrape targets, Grafana provisioning and data in every dashboard panel."""

import argparse
import base64
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def read_env(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def get_json(url, authorization=None):
    headers = {"Authorization": authorization} if authorization else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def verify(prometheus, grafana, authorization):
    health = get_json(grafana + "/api/health")
    if health.get("database") != "ok":
        raise RuntimeError("Grafana database is not ready")
    source = get_json(grafana + "/api/datasources/uid/prometheus/health", authorization)
    if source.get("status") != "OK":
        raise RuntimeError("Grafana cannot query the provisioned Prometheus datasource")
    data = get_json(prometheus + "/api/v1/targets")
    targets = data["data"]["activeTargets"]
    expected = {"prometheus", "node_exporter", "cadvisor"}
    if {target["labels"].get("job") for target in targets} != expected:
        raise RuntimeError("Expected exactly the prometheus, node_exporter and cadvisor jobs")
    if len(targets) != 3 or any(target.get("health") != "up" for target in targets):
        raise RuntimeError("Some scrape targets are not UP")
    dashboard = get_json(grafana + "/api/dashboards/uid/homelab-overview", authorization)["dashboard"]
    panels = dashboard.get("panels", [])
    if len(panels) != 8:
        raise RuntimeError("Expected the provisioned dashboard with eight panels")
    for panel in panels:
        for target in panel.get("targets", []):
            query = urllib.parse.urlencode({"query": target["expr"]})
            result = get_json(prometheus + "/api/v1/query?" + query)
            if result.get("status") != "success" or not result.get("data", {}).get("result"):
                raise RuntimeError(f"No data yet for panel: {panel['title']}")
    return {"targets_up": len(targets), "grafana_database": "ok", "datasource": "healthy", "panels_with_data": len(panels)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        env = read_env(args.env_file)
    except OSError:
        parser.exit(1, "Cannot read the environment file; run python3 scripts/init_env.py first.\n")
    if not env.get("GRAFANA_ADMIN_PASSWORD"):
        parser.exit(1, "GRAFANA_ADMIN_PASSWORD is empty; configure the local environment first.\n")
    credentials = env.get("GRAFANA_ADMIN_USER", "admin") + ":" + env["GRAFANA_ADMIN_PASSWORD"]
    authorization = "Basic " + base64.b64encode(credentials.encode()).decode()
    prometheus = "http://127.0.0.1:" + env.get("PROMETHEUS_PORT", "29090")
    grafana = "http://127.0.0.1:" + env.get("GRAFANA_PORT", "23030")
    deadline = time.monotonic() + args.timeout
    last_error = "Stack has not started"
    while time.monotonic() < deadline:
        try:
            summary = verify(prometheus, grafana, authorization)
        except (OSError, urllib.error.URLError, ValueError, KeyError, RuntimeError) as error:
            last_error = str(error)
            time.sleep(3)
        else:
            print(json.dumps(summary, indent=2))
            return
    parser.exit(1, f"Stack verification failed: {last_error}\n")


if __name__ == "__main__":
    main()
