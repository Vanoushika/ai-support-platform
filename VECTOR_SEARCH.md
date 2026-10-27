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

Follow CONTAINERS.md for the current first-time setup or daily startup. It includes
OpenBao initialization/unsealing before running indexer and application services.
With the stack running and OpenBao unsealed:

```bash
docker compose exec api python check_vector.py
docker compose run --rm indexer
```

The first index creates new embeddings. An unchanged subsequent run should report
three reused embeddings and zero new embeddings. Test a NEW ticket workflow at
http://localhost:8080 and inspect its retrieved sources. For restart testing, follow
the OpenBao-aware startup sequence in CONTAINERS.md, then repeat the checker.
A successful checker after startup verifies retrieval recovery; because indexing
can rerun, it is not proof of an off-machine backup/restore procedure.

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

## Credentials and scope (current OpenBao integration)
`setup_vector.py` creates the initial random PostgreSQL password. The database
service retains that bootstrap file mount. API, worker and indexer now authenticate
to OpenBao with AppRole and read the same password from KV v2; they do not mount
the direct password file. See SECRETS.md. The native file-provider path remains
available when explicitly configured. No automatic database password rotation or
dynamic credentials are implemented.

This isolated local demo uses a database-owner account (the image's bootstrap user)
for extension/table initialization and retrieval. Production requires separate
bootstrap, index-writer and read-only application roles, backups, TLS and access
controls. The database is not published on a host port.

Sources: https://github.com/pgvector/pgvector and
https://www.psycopg.org/psycopg3/docs/basic/params.html
