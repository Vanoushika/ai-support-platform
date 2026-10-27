# AI Support Platform

A local customer-support demo that creates tickets, retrieves support articles,
drafts suggested replies, assigns support queues, and saves human review decisions.
It runs on an Apple Silicon Mac with local Ollama models and Docker Compose.

**A draft approval records a review decision. It does not send a message, approve
or issue a refund, or mark the ticket resolved.** This is a portfolio demonstration,
not a production support system or an autonomous resolution agent.

## Implemented features

- React/TypeScript ticket UI and FastAPI endpoints with input validation.
- Persistent SQLite tickets, routing decisions and saved review snapshots.
- LangGraph ticket classification and queue selection.
- RAG using three Markdown support articles, local embeddings, and PostgreSQL
  pgvector exact cosine similarity search. Unchanged document embeddings are reused.
- Local model response generation with one correction attempt for detected issues
  and a clearly flagged human-review fallback when checks still fail.
- Temporal workflows that prepare drafts, wait for review, and persist decisions.
- RAGAS document-faithfulness evaluation and separate claim-level diagnostics.
- OpenTelemetry API/worker traces and metrics, Grafana dashboards, Tempo and Prometheus.
- OpenBao KV v2 password storage with AppRole login and restricted secret access.
- Docker Compose services with persistent volumes and a host-native Ollama service.

## Components

| Component | Responsibility |
| --- | --- |
| React + Nginx | Ticket creation, status updates, sources and review controls |
| FastAPI | Ticket APIs and Temporal workflow start/status/review endpoints |
| LangGraph | Classification and support-queue selection |
| Temporal server + Python worker | Durable preparation and human-review coordination |
| Ollama | `qwen3.5:4b` generation and `nomic-embed-text` embeddings |
| PostgreSQL + pgvector | Knowledge document/vector storage and SQL similarity search |
| SQLite | Tickets, routing and review records shared by the API and worker |
| OpenBao | AppRole authentication and read-only access to the stored database password |
| OpenTelemetry, Tempo, Prometheus, Grafana | Traces, metrics and dashboards |

The API starts a workflow and returns before model work finishes. The worker
classifies the ticket, retrieves an article and prepares a draft. A human reviews
the saved text against its sources and approves or rejects it. Ticket status is
managed separately. One review workflow is supported per ticket; use a new ticket
when testing changed prompts or knowledge articles.

## Run locally

See [CONTAINERS.md](CONTAINERS.md) for first-time installation, daily startup,
updates and recovery. The tested setup uses a MacBook Air M3 with 16 GB RAM,
Colima with 2 CPUs/4 GB RAM, Docker Compose and host-native Ollama.

For an **already initialized** installation, from the repository root:

```bash
colima start --cpu 2 --memory 4
docker compose up -d openbao
```

Once OpenBao is responding:

```bash
python3 setup_openbao.py unseal
docker compose up -d
```

Ollama must also be running on the Mac. Stop on errors and follow the troubleshooting
section in CONTAINERS.md. Fresh clones must follow the first-time setup instead.

| Local interface | URL |
| --- | --- |
| App | http://localhost:8080 |
| API docs | http://localhost:8001/docs |
| Temporal UI | http://localhost:8234 |
| Grafana | http://localhost:3001 |
| OpenBao | http://localhost:8201 |

These ports are bound to localhost. PostgreSQL and telemetry backends have no
published host ports. The API has no user authentication; do not expose it publicly.

## Checks and demo

See [DEMO.md](DEMO.md) for a short walkthrough and the final verification checklist.
See [PROJECT_STATUS.md](PROJECT_STATUS.md) for what has been verified and what is
still limited. Unit tests use mocks; live smoke checks test local integrations.
Neither is a general model-accuracy benchmark.

```bash
docker compose exec api python -m unittest test_draft_quality test_secret_access -v
docker compose exec api python check_secrets.py
docker compose exec api python check_vector.py
```

After creating a new workflow, wait about 30 seconds, then:

```bash
docker compose exec api python check_observability.py
```

## Detailed documentation

- [Containers and startup](CONTAINERS.md)
- [Vector retrieval](VECTOR_SEARCH.md)
- [Draft checks and fallback behavior](DRAFT_QUALITY.md)
- [Observability](OBSERVABILITY.md)
- [Secret management](SECRETS.md)
- [Demo and final verification](DEMO.md)
- [Evidence and limitations](PROJECT_STATUS.md)

## Evaluation scope

The evaluation dataset contains six development cases, not a held-out benchmark.
Historical reports under `backend/evaluation_reports/` were generated at earlier
project stages. Generator and judge use the same local model. Judge scores can be
wrong, and document-only faithfulness may penalize customer-reported facts that
are absent from articles. Ticket-plus-document diagnostics are a separate metric
scope and must not be merged with the original document-only scores.

Native evaluation defaults to SQLite retrieval. It does not evaluate the Docker
pgvector backend unless explicitly configured to do so. New reports record fallback
and revised-draft counts. A nonempty fallback is not successful task completion,
even if it receives a high faithfulness score.

## Important limitations

- Only three support articles; whole-article retrieval with no chunking or reranker.
- Heuristic checks can miss unsupported statements or reject acceptable phrasing.
  Citations and retrieval similarity do not establish correctness.
- Drafts can still read like internal notes; review them before approval. The UI
  does not yet prevent approving a fallback placeholder or support editing drafts.
- No customer messaging integration, authentication/RBAC, tenant isolation, automated
  refund execution, deployment hardening, load test or disaster-recovery validation.
- Temporal runs in development mode; the SQLite design targets one local API/worker.
- OpenBao uses a documented local-demo key/credential arrangement, not production
  key custody. Database-role least privilege and rotation remain future work.
- Some workflow-status traces show timestamp/duration anomalies; do not use their
  total duration as request latency. See OBSERVABILITY.md.

This implementation uses **pgvector instead of MongoDB Atlas Vector Search**, and
**OpenBao instead of HashiCorp Vault**. Describe the implemented stack accurately
when discussing the project or listing it on a resume.
