# Demo and final verification

Use synthetic tickets only. Start the stack using CONTAINERS.md. A model-generated
answer may vary between runs, so compare it with the sources rather than expecting
a memorized response. This checklist does not assert that every item has been run
on the final combined stack; record actual results when you execute it.

## 1. Verify the running stack

From the repository root:

```bash
docker compose ps -a
curl -i http://localhost:8080/api/health
docker compose exec api python -m unittest test_draft_quality test_secret_access -v
docker compose exec api python check_secrets.py
docker compose exec api python check_vector.py
```

Expected: indexer exited 0; long-running services up; HTTP 200; 28 mocked regression
tests pass; secret-access checks pass; three retrieval cases pass. These establish
specific behavior, not general accuracy, availability or security certification.

## 2. Show a ticket and its evidence

Open http://localhost:8080 and create a NEW ticket:

**Title:** Premium access unavailable after signing in again

**Description:** My billing page shows the upgrade as completed. I signed out and
signed back in with the same account, but premium features are still locked.

Start the workflow under that exact ticket title. Expected queue: billing.
Expected retrieved article: KB-002 / premium_access.md. The next applicable step
is human billing review. A draft should not repeat completed sign-in steps, claim
features were activated, or invent an activation time.

Inspect the warning area. FALLBACK means the model failed the bounded checks and
the displayed text is only a human-review placeholder. Reject it. A citation alone
does not make a response correct. Reject internal agent notes that are unsuitable
as customer replies. There is no draft-editing interface yet.

Approve only a response you have checked and found acceptable. Either decision
should become completed and persist on refresh. Approval sends no message or refund
and does not change the independent ticket status. Change status separately with
the dropdown if demonstrating that feature.

## 3. Demonstrate the known password-reset regression

Create another NEW ticket:

**Title:** Second password reset email still missing

**Description:** I checked spam and requested a second password reset email.
Another ten minutes have passed without receiving it.

Expected queue: account_access. Expected source: KB-001. The source calls for
human account-access escalation at this stage, not a third reset email. Acceptable
behavior is a supported, customer-facing draft with [KB-001], or a flagged fallback
requiring human drafting. The observed live run fixed the third-email/citation issue
but still sounded like an internal note; that tone issue remains a limitation.

## 4. Show traces and metrics

After a new workflow, wait about 30 seconds:

```bash
docker compose exec api python check_observability.py
```

Open Grafana http://localhost:3001 -> Dashboards -> AI Support -> AI Support Platform.
Use Last 1 hour. Show API request rate, API latency, operation durations and collector
health. Operation totals/averages are since worker start; polling counts as API
traffic. The 5xx chart does not include Nginx-generated errors that never reach API.

Explore -> Tempo -> TraceQL:

```text
{ resource.service.name = "support-worker" && name = "review.prepare" }
```

Open a result and show API and worker services, ticket.classify, knowledge.search
and draft.generate. Retrieval is nested within drafting: do not add their durations
as independent sequential steps. Workflow-status query traces have shown a timestamp
anomaly; use the API span for request time, not the whole query trace's duration.

## 5. Explain secrets without displaying them

Run `docker compose exec api python check_secrets.py` and show only its PASS lines.
The app uses AppRole, reads one KV v2 secret, and connects to PostgreSQL. It cannot
write the secret or administer secret mounts. This is not automated SQL credential
rotation, and the SQL account itself remains privileged for the local demonstration.

## 6. Optional recovery demonstration

This interrupts secret reads briefly. Do it between workflows, not during a live demo:

```bash
docker compose restart openbao
```

Wait a few seconds, then:

```bash
python3 setup_openbao.py unseal
docker compose exec api python check_secrets.py
docker compose exec api python check_vector.py
```

For a full stop/start, use CONTAINERS.md. Never use `down -v` for recovery.

## Final handoff checklist

- [ ] Combined 28-test run passes in the current image.
- [ ] Health, secret-access and vector smoke checks pass.
- [ ] A new workflow's sources, draft and review decision have been inspected.
- [ ] Metrics and a preparation trace are visible.
- [ ] Recovery sequence is understood and private credentials are retained locally.
- [ ] `git status --short` is clean after committing documentation.
- [ ] No databases, credentials or real customer data were committed.
- [ ] Demo claims match the implemented stack and known limitations.
