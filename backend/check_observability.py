"""Run inside the API container after generating traffic; no ticket mutation."""
import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen


def get_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def main():
    failures = []
    for name, url, field in [
        ("API metrics", "http://prometheus:9090/api/v1/query?" + urlencode({"query": 'support_http_requests_total{service_name="support-api"}'}), "metrics"),
        ("Worker traces", "http://tempo:3200/api/search?" + urlencode({"q": '{ resource.service.name = "support-worker" }', "limit": 5}), "traces"),
    ]:
        try:
            data = get_json(url)
            items = data.get("data", {}).get("result", []) if field == "metrics" else data.get("traces", [])
            if not items:
                raise ValueError("No data yet. Create a new ticket workflow and wait 30 seconds.")
            print(f"PASS: {name} ({len(items)} results)")
        except Exception as exc:
            failures.append(name)
            print(f"NOT VERIFIED: {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
