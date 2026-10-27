# Local container demo on an Apple Silicon Mac

Prerequisites: Colima (default user-mode networking), Docker Compose/Buildx,
and the existing host Ollama service with qwen3.5:4b and nomic-embed-text.
Ollama stays on the Mac for native acceleration; it is not containerized.
The host.lima.internal mapping uses Lima's default host-loopback address.
Other runtimes/network modes need a different OLLAMA_BASE_URL/mapping.

## Run

From the repository root:

```sh
docker compose config --quiet
docker compose build
docker compose run --rm --no-deps api python -c "import json, urllib.request; from settings import OLLAMA_BASE_URL; d=json.load(urllib.request.urlopen(OLLAMA_BASE_URL+'/api/tags', timeout=10)); print([m['name'] for m in d['models']])"
docker compose up -d
docker compose ps -a
```

Open http://localhost:8080 for the app, http://localhost:8001/docs for the API,
and http://localhost:8234 for the container Temporal UI.
Create a NEW ticket, start its workflow, wait for awaiting_review, then approve
or reject and refresh to confirm the stored decision. Approval still sends no
customer message, issues no refund, and does not resolve a ticket automatically.

The container demo uses separate named volumes for tickets and Temporal.
Existing Mac tickets, embeddings, reviews and workflows are not migrated.
The first run indexes the three existing knowledge articles into the new database.
The indexer should show Exited (0); it is intentionally a one-shot task.
The worker should log 'Support worker ready'.

```sh
docker compose logs --tail=80 indexer api worker temporal
docker compose down
docker compose up -d
```

After down/up, confirm the NEW ticket and review still exist. Normal down preserves
volumes. `docker compose down -v` deletes this demo's stored data; do not use it
unless deliberately resetting the demo. Stop containers with down when finished;
`colima stop` also releases the VM's memory.

## Updates

Source is baked into images. After code or knowledge article edits:

```sh
docker compose down
docker compose build
docker compose up -d
```

The indexer reruns against the existing volume, reusing unchanged embeddings.
Evaluation scripts stay in the Mac venv with their existing requirements.txt;
the lean runtime image does not install RAGAS and its evaluation dependencies.
Existing local commands still work because settings default to their original
addresses and SQLite path when no environment overrides are supplied.

## Scope and limits

This is a local development setup, with a Temporal development server and shared
SQLite storage for one API and one worker. It is not production-hardened and does
not add authentication, distributed database scaling, telemetry or secret storage.
Those remain separate milestones. Image minor tags and transitive dependencies
are not a fully reproducible lock; pin image digests and a tested Linux dependency
lock after the first successful build.

The API health check verifies HTTP startup, not model quality or every dependency.
Existing model evaluation limitations and human review requirements still apply.
