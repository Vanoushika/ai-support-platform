# Local tracing and dashboards

Run the installer, then from the project root:

```sh
docker compose config --quiet
docker compose build api worker indexer
docker compose up -d
docker compose ps -a
```

Existing Compose project name and ticket/Temporal volume names are unchanged.
Do not use `down -v`. Ollama stays on the host. The indexer is not instrumented.

## Verify

1. Open http://localhost:8080. Create a NEW synthetic ticket and start its workflow.
2. Review the draft and reject it if unsupported; verify completion after deciding.
3. Wait 30 seconds for metric export and scrapes.
4. Open http://localhost:3001. On a new Grafana volume the initial login is admin /
   admin. Choose a new password when prompted; it is stored in the Grafana volume.
5. Open Dashboards -> AI Support -> AI Support Platform.
6. Open Explore -> Tempo -> TraceQL. Run:
   `{ resource.service.name = "support-worker" }`
   Choose Last 15 minutes. Open a trace and check for both API/client and worker
   spans. Look for review.prepare, ticket.classify, knowledge.search, draft.generate,
   and review.record_decision. Trace context crosses Temporal via its SDK interceptor.
7. Run `docker compose exec api python check_observability.py`.
   Both metrics and worker traces should pass; this smoke check does NOT establish
   that an API and worker share a trace ID. Verify that visually in step 6.

```sh
docker compose logs --tail=60 api worker otel-collector tempo prometheus grafana
```

The dashboard may need a minute and multiple requests before rate/latency panels
have samples. Zero traffic or no operation executions produces empty panels.
The collector scrape health panel alone does not prove telemetry flows end to end.

## What is measured

API counts, response status and latency use route templates, not raw ticket URLs.
Health probes are excluded; browser polling is included. Operation timers cover
classification, retrieval, drafting and review activity execution. Counters measure
attempts (retries may add counts), not unique tickets or completed refunds.
Raised exceptions are recorded by type; a classifier's handled fallback is not
counted as a raised error. These metrics do not measure factual accuracy.

Manual instrumentation does not record ticket text, prompts, replies, request bodies,
query strings, auth headers or exception messages. The Temporal SDK interceptor may
include workflow/activity identifiers and SDK exception events; use synthetic demo
data. Review telemetry before using any real customer information. No log ingestion
is configured: existing logs remain available through docker compose logs.

Traces retain 24 hours; Prometheus retains up to 2 days / 512 MB. The collector's
in-memory export queue is not durable. This is local development telemetry, not
an audit log or production monitoring system. Metrics and traces have separate
named volumes. Grafana is exposed only on localhost:3001; other telemetry services
have no published host ports. Fixed example image versions are not an ongoing
security patch policy; assess/update them before external deployment.

OTEL_ENABLED defaults to false outside Compose, so existing Mac venv commands keep
working without installing new packages. Runtime dependencies are added only to
requirements-runtime.txt. Explicit spans avoid collecting model text automatically.

No workflow implementation or stored workflow arguments changed. Historical
executions do not gain traces retroactively. TracingInterceptor is an SDK-supported
integration; the diagnostic methods used in diagnose_faithfulness.py are unrelated.

If Colima runs out of memory, stop the containers normally, stop Colima, then start
it with `colima start --cpu 2 --memory 6` and bring containers back up. This is an
optional adjustment on the 16 GB Mac; start with the existing 4 GB allocation.
