import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BACKEND_DIR / "tickets.db")))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")

# Native development retains SQLite. Docker explicitly selects pgvector.
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "sqlite")
if VECTOR_BACKEND not in {"sqlite", "pgvector"}:
    raise ValueError("VECTOR_BACKEND must be sqlite or pgvector")
