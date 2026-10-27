# PostgreSQL vector search

Docker now stores knowledge documents and 768-dimensional nomic-embed-text vectors
in PostgreSQL/pgvector. SQL cosine distance (`<=>`) ranks results; similarity is
1 minus distance. Similarity is not answer accuracy. Exact nearest-neighbor search
is appropriate for this three-document development dataset. No HNSW index or
scalability benchmark is claimed. Whole articles are still the retrieval units.

Tickets, routing, review snapshots and decisions remain in the existing SQLite
volume. Temporal and Grafana volumes are unchanged. Existing SQLite embeddings
remain available to native development, but Docker re-embeds articles into its
new vector-data volume. Saved historical drafts are not regenerated.

## Install and verify
From the project root, after applying the installer:

```bash
python setup_vector.py
git check-ignore .local-secrets/vector_password
docker compose config --quiet
docker compose build api worker indexer
docker compose up -d vector-db
docker compose run --rm indexer
docker compose up -d
docker compose exec api python check_vector.py
```

The first index creates new embeddings. Run `docker compose run --rm indexer`
again to verify reuse. Test a new workflow in http://localhost:8080 and inspect
its retrieved sources. Then test persistence with `docker compose down` followed
by `docker compose up -d` and repeat the checker. Do not add `-v`: that deletes
project volumes, including existing tickets and Temporal data.

## Index behavior
Indexing computes all changed embeddings before replacing documents in one
transaction. Empty input and malformed/zero/wrong-dimension vectors are rejected.
Failed inserts roll back the transaction. Search executes in PostgreSQL and returns
only the requested results, rather than downloading all vectors to Python.
Model changes require reindexing; dimension changes require a deliberate schema
migration. Run only one index job at a time. File changes require rerunning the
indexer (and rebuilding the backend image because articles are copied into it).
A database failure is reported, not silently replaced with SQLite search.

Native `python retrieval.py` still defaults to SQLite; reports created natively
therefore do not evaluate pgvector. Use the container checker for this backend.
Install updated requirements if opting into native PostgreSQL access; no database
port is published by Compose. This update is pgvector, not MongoDB Atlas Vector Search.

## Credentials and scope
`setup_vector.py` generates one random password and preserves it on repeated runs.
The containing host directory is private (0700). Compose mounts its file read-only
in the database and app containers. The file is readable by the non-root app uid;
it is excluded from Git and Docker build contexts. Keep it with the database volume:
changing the file alone does not rotate an initialized PostgreSQL user's password.
This is local file-based secret delivery, not Vault/OpenBao integration.

This isolated local demo uses a database-owner account (the image's bootstrap user)
for extension/table initialization and retrieval. Production requires separate
bootstrap, index-writer and read-only application roles, backups, TLS and access
controls. The database is not published on a host port.

Sources: https://github.com/pgvector/pgvector and
https://www.psycopg.org/psycopg3/docs/basic/params.html
