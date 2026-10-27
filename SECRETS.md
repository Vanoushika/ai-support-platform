# OpenBao secret delivery (local demonstration)

The API, worker and indexer log in to OpenBao using AppRole, obtain a two-minute
batch token, and read the PostgreSQL password from `support/data/vector-db`.
Tokens and passwords are not printed or cached on disk by the client. Tokens
expire without a renewal task. A fresh login/read happens per database connection.
The service fails if OpenBao is sealed/unavailable; it does not silently fall back
to a local password file. Native code defaults to the existing file provider.

The app policy grants read access to only that secret and permission to inspect
its own capabilities. It cannot write/delete that secret or administer mounts.
The live checker tests those effective permissions and a real PostgreSQL connection.
This is a static database password in KV v2, not dynamic credentials or automated
password rotation. The PostgreSQL account still has the demo's bootstrap privileges;
OpenBao read-only policy does not make the SQL account read-only.

## First installation
From the project root after installing the update:

```bash
python setup_openbao.py prepare
docker compose config --quiet
docker compose up -d openbao
python setup_openbao.py bootstrap
docker compose build api worker indexer
docker compose run --rm --no-deps api python -m unittest test_secret_access -v
docker compose up -d
docker compose exec api python check_secrets.py
docker compose exec api python check_vector.py
```

It is expected for OpenBao to be unhealthy until initialized and unsealed.
If bootstrap reports unavailable immediately after starting, wait a few seconds
and rerun it. Bootstrap preserves the existing database password and app credentials;
it refuses mismatching stored secrets rather than silently rotating them.

## Restart after stopping all containers or rebooting Colima
OpenBao starts sealed. Start it and explicitly unseal before starting dependent apps:

```bash
docker compose up -d openbao
python setup_openbao.py unseal
docker compose up -d
docker compose exec api python check_secrets.py
```

A simple API/worker recreation does not require unsealing if OpenBao stayed running.
Never delete the volumes or use `down -v` to fix a sealed service. Keep the matching
OpenBao volume and host bootstrap file. A missing key prevents recovery; this package
does not bypass OpenBao's seal or reinitialize a server to erase data.

## Private files
All live credentials remain in `.local-secrets/`, already excluded by .gitignore and
.dockerignore. Do not upload that folder or paste its contents into chat.

- `bao-bootstrap.json`: initial root token and one unseal share (0600). Host-only;
  never mounted in app containers. Used by the local setup/unseal command.
- `bao-app.json`: RoleID and SecretID (0644 inside host directory 0700). Read-only
  Compose mount for non-root app processes. These authenticate to the scoped role.
- `vector_password`: original database bootstrap password. Still mounted in the
  database service; no longer mounted in API/worker/indexer. Keep it for existing
  database initialization/recovery. Replacing it does not rotate PostgreSQL.

AppRole SecretIDs are intentionally reusable and non-expiring for this local demo;
short-lived login tokens do not make the SecretID itself short-lived. Production
needs a managed credential delivery/rotation mechanism. Administrator/unseal
credentials stored together on the same laptop are a demonstration convenience,
not separation of duties. The bootstrap root token is retained for local management.

OpenBao uses encrypted persistent file storage in an isolated named volume, one
unseal share, plain HTTP on the private Compose network, localhost-only host port
8201, and disabled mlock. This is not a production secrets deployment. Production
needs TLS, managed unseal/key custody, secure administrator workflows, audit logging,
transactional/HA storage, least-privilege database roles, and tested backups.

Ollama has no API key in this setup. The real managed secret here is the PostgreSQL
password. Describe this as OpenBao integration, not HashiCorp Vault deployment.

References:
- https://openbao.org/docs/api/auth/approle/
- https://openbao.org/docs/api/secret/kv/kv-v2/
- https://openbao.org/docs/api/system/init/
- https://openbao.org/docs/api/system/capabilities-self/
