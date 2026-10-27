# Project status and evidence

Snapshot: 27 October 2026. This is a working local portfolio demo with documented
limitations. It has not been verified for production use or independent deployment
by a new user. The final combined verification checklist is in DEMO.md.

## Evidence observed during development

| Area | Observed result | Scope |
| --- | --- | --- |
| Ticket API/UI | Creation, listing, status updates and persistence exercised | Local synthetic tickets |
| Workflow review | Approvals/rejections saved; completed outcomes returned after refresh | One workflow per ticket; no messages/refunds sent |
| Containers | App and support services ran on Colima; ticket/review survived recreation | Local Compose setup |
| Nginx | Health returned 200 after API recreation without frontend restart | Recovery smoke test; no outage/SLA guarantee |
| Vector retrieval | Three articles stored as 768-dimensional vectors; three expected top-one matches | Three smoke cases, not a retrieval benchmark |
| Embedding reuse | Second index reported 0 new embeddings and 3 reused | Unchanged three-article collection |
| Retrieval after restart | All three smoke cases passed again | Indexer can rerun at startup; this alone is not a backup/restore test |
| Metrics/traces | Checker passed and Grafana displayed metrics plus API/worker preparation spans | Some status-query trace durations are anomalous |
| OpenBao | Scoped read permissions, denied unrelated/admin paths, actual PostgreSQL connection, absent direct password mount | Local static KV secret; not production key custody |
| Recovery | Retrieval worked after OpenBao restart and explicit unseal | Not an automated disaster-recovery procedure |
| Draft tests | 18 deterministic regressions passed | Mocked retrieval/model responses |
| Secret tests | 10 deterministic tests passed during update preparation | Mocked OpenBao responses |
| Live quality behavior | Second-reset draft no longer requested a third email; premium test used a flagged fallback | Limited examples; internal-note wording still observed |

## Evaluation evidence

Historical six-case development runs produced 6/6 category and top-one retrieval
matches. These are small, familiar development cases. Reported mean document-only
faithfulness varied (including about 0.638 and 0.674); neither is a general accuracy
claim. These reports predate the final pgvector/OpenBao/quality-check combination.

A diagnostic second-attempt response scored 0.0 using only article evidence and
0.8 when customer-reported facts were explicitly added. These have different evidence
scopes and cannot be combined or presented as a measured model-quality improvement.
Judge reasoning can be overly restrictive or wrong. The generator and judge share
the same local model. New draft placeholders are tracked separately in evaluation
metadata, but successful_drafts still counts nonempty text; inspect fallback counts.

## Known gaps and next improvements

1. Customer-facing tone: a generated draft can sound like instructions to an agent.
2. Placeholder approval: the UI/backend still allow recording approval of a fallback;
   reviewers must reject it. Future work should enforce a non-approvable state and
   allow an edited human reply with revision history.
3. Draft correctness: regex checks are deliberately limited and can produce false
   positives/negatives. Broader held-out tests, evidence-aware checks and model
   comparisons are needed before claiming dependable answer quality.
4. Observability: investigate Temporal status-query span timestamps before drawing
   latency conclusions from total trace durations. The exporter/collector is not an
   audit log, and handled classifier fallbacks are not raised-error metrics.
5. Security: no user authentication, role enforcement, tenant isolation, TLS between
   local containers, production unseal/key custody, or least-privilege SQL roles.
6. Workflow/product scope: no real reply sending, refund processing, draft editing,
   per-ticket workflow revisions or authorization of the human reviewer.
7. Scale/operations: only three whole articles, exact vector search, a local shared
   SQLite database, Temporal development server, no load test, CI pipeline, fully
   reproducible dependency/image lock or tested off-machine backup restoration.

## Accurate project description

Built a local AI-assisted customer-support demo with FastAPI, React, LangGraph,
Temporal and Ollama. Implemented pgvector retrieval, human review workflows,
RAGAS development evaluations, OpenTelemetry/Grafana monitoring, OpenBao AppRole
secret access and Docker Compose deployment.

Do not describe this implementation as MongoDB Atlas Vector Search, HashiCorp Vault,
production deployment, autonomous ticket resolution, or a measured general-purpose
accuracy improvement. Those claims would require additional implementation/evidence.
