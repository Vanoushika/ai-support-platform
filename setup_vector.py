"""Generate a local database password without printing it or overwriting it."""
import os
import secrets
from pathlib import Path

folder = Path(__file__).resolve().parent / ".local-secrets"
folder.mkdir(mode=0o700, exist_ok=True)
folder.chmod(0o700)
path = folder / "vector_password"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
except FileExistsError:
    if not path.read_text().strip():
        raise SystemExit("Existing password file is empty; no changes made.")
    print("Existing vector database password preserved.")
else:
    with os.fdopen(fd, "w") as handle:
        handle.write(secrets.token_urlsafe(48) + "\n")
    # Compose file secrets retain source permissions. The app runs as uid 10001.
    # Parent directory is private on the host; only explicitly mounted services see the file.
    path.chmod(0o644)
    print("Local vector database password created. It was not printed.")
