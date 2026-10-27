# Local containers on an Apple Silicon Mac

Run commands from the repository root. Run one block at a time and stop if a command
fails. This guide is for the current OpenBao + pgvector stack; older startup
instructions that omit unsealing are no longer sufficient after a full restart.

## Prerequisites

- Python 3.12 on the host for setup scripts (these use the standard library).
- Colima, Docker CLI, Docker Compose plugin and Docker Buildx plugin installed.
- Ollama installed and running natively on the Mac. It stays outside Docker for
  native acceleration. Do not start a second Ollama server if one is already running.
- Git and this repository cloned locally.

The working Colima configuration is 2 CPUs and 4 GB RAM on a 16 GB M3 Mac.
The Compose mapping `host.lima.internal:192.168.5.2` is specific to the default
Lima/Colima host-loopback networking used here. Other runtimes need their own host
mapping and OLLAMA_BASE_URL. PostgreSQL uses a separate named volume; tickets and
Temporal data retain their existing named volumes.

## First-time setup on a fresh clone

Start Colima and download the models if they are not already present:

```bash
colima start --cpu 2 --memory 4
ollama pull qwen3.5:4b
ollama pull nomic-embed-text
ollama list
```

From the repository root, create private files and check the Compose configuration:

```bash
python3 setup_vector.py
python3 setup_openbao.py prepare
git check-ignore .local-secrets/vector_password .local-secrets/bao-app.json
docker compose config --quiet
```

Start OpenBao and PostgreSQL. The OpenBao health check initially fails because it
has not been initialized/unsealed yet; this is expected.

```bash
docker compose up -d openbao vector-db
```

Wait a few seconds, then bootstrap. This saves the recovery credentials privately,
unseals OpenBao, stores the existing database password and configures AppRole:

```bash
python3 setup_openbao.py bootstrap
```

If it reports that OpenBao is unavailable, wait a few seconds and retry the same
command. It is designed to preserve existing credentials on repeated execution.
Do not delete private files or volumes to bypass initialization errors.

Build the app and run isolated tests before starting it:

```bash
docker compose build
docker compose run --rm --no-deps api python -m unittest test_draft_quality test_secret_access -v
```

Index articles, start the rest of the stack, and verify:

```bash
docker compose run --rm indexer
docker compose up -d
docker compose ps -a
docker compose exec api python check_secrets.py
docker compose exec api python check_vector.py
```

The indexer is a one-shot job; `Exited (0)` is success. An app/worker failure is not
normal. Open the app at http://localhost:8080. Create a new synthetic ticket and run
its workflow. Grafana initial login on a new volume is admin/admin; change that
password when prompted. OpenBao administrator credentials do not belong in app
containers, source files, shell arguments or chat messages.

## Daily startup after stopping containers or rebooting

Ensure Ollama is running. Start Colima if needed:

```bash
colima start --cpu 2 --memory 4
docker compose up -d openbao
```

Wait a few seconds for OpenBao, then:

```bash
python3 setup_openbao.py unseal
docker compose up -d
curl -i http://localhost:8080/api/health
```

Expect HTTP 200. This health endpoint checks API startup, not all dependencies.
For dependency checks run check_secrets.py and check_vector.py as shown above.
OpenBao remains unsealed when only API/worker containers are recreated. It starts
sealed again whenever its own process restarts.

## Stop without deleting data

```bash
docker compose down
colima stop
```

Normal `down` preserves named volumes. **Do not add `-v`**: it deletes ticket,
workflow, vector, telemetry and OpenBao data. Preserve `.local-secrets/` with the
matching OpenBao/database volumes. A Git clone does not contain those private
files or databases and cannot restore their contents.

## Apply source or article changes

Source and articles are copied into images; they are not live bind mounts.
With OpenBao already unsealed:

```bash
docker compose build api worker indexer
docker compose up -d
```

For frontend changes:

```bash
docker compose build frontend
docker compose run --rm --no-deps frontend nginx -t
docker compose up -d --no-deps frontend
```

The indexer must rerun after article changes; `docker compose run --rm indexer`
can be used explicitly once the new backend image is built. Unchanged embeddings
are reused. Existing workflow drafts remain saved snapshots. Test changes with a
new ticket, not an existing reviewed workflow. Do not stop the whole stack for a
routine app update; doing so requires the unseal startup sequence again.

## Troubleshooting

| Symptom | Next check |
| --- | --- |
| OpenBao unhealthy or sealed | `python3 setup_openbao.py unseal`; then `docker compose up -d` |
| Missing bootstrap file | Restore the matching private recovery file; do not reinitialize/delete the volume |
| Workflow stays preparing | `docker compose logs --tail=60 worker`; check Ollama and OpenBao |
| Model/embedding connection error | Confirm Ollama is running and `ollama list` includes both models |
| Frontend 502 after API recreation | Wait for API health and DNS refresh; inspect `docker compose logs --tail=40 frontend api` |
| No dashboard data | Create a new workflow, wait 30 seconds, select a recent time range |
| Native port 8000/7233 already occupied | Container stack uses 8001/7234 on the host; avoid starting duplicate native services |
| Password mismatch during bootstrap | Stop and investigate matching files/volumes; changing a file does not rotate PostgreSQL |

Do not share `.local-secrets/` contents. Logs should be reviewed before sharing
because third-party SDK error events can contain workflow identifiers or details.

## Native development and evaluation

The lean Docker runtime does not install RAGAS. For the existing native evaluation
mode, use a Python 3.12 virtual environment and host Ollama:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python retrieval.py --index
python evaluate_project.py --limit 1
```

If `.venv` already exists, just activate it; do not recreate or clear it. Native
settings default to local SQLite and native Temporal/Ollama addresses. These
reports do not measure the Docker pgvector backend. See README.md for limitations.

The container app entry point is `server:app`, which includes workflow routes and
telemetry. Running `main:app` alone omits those additions. This setup has no
production authentication or fully locked cross-platform dependency/image digests.
