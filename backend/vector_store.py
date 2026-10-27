"""PostgreSQL vector storage. Synchronous calls run in retrieval's worker threads."""
import json
import math
import os
from pathlib import Path

DIMENSIONS = 768  # nomic-embed-text default output


def vector_literal(vector):
    if not isinstance(vector, list) or len(vector) != DIMENSIONS:
        raise ValueError(f"Expected {DIMENSIONS} embedding dimensions.")
    if any(isinstance(x, bool) or not isinstance(x, (int, float))
           or not math.isfinite(x) for x in vector):
        raise ValueError("Embedding values must be finite numbers.")
    if not any(x != 0 for x in vector):
        raise ValueError("Zero vectors cannot be used for cosine search.")
    return json.dumps(vector, allow_nan=False)


def connect():
    import psycopg
    from psycopg.rows import dict_row
    from secret_access import read_vector_password
    password = read_vector_password()
    return psycopg.connect(
        host=os.getenv("VECTOR_HOST", "vector-db"),
        port=int(os.getenv("VECTOR_PORT", "5432")),
        dbname=os.getenv("VECTOR_DATABASE", "support_knowledge"),
        user=os.getenv("VECTOR_USER", "support"),
        password=password, connect_timeout=10, row_factory=dict_row,
        options="-c statement_timeout=30000 -c lock_timeout=10000",
    )


def initialize():
    with connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_vectors (
                source TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                model TEXT NOT NULL,
                embedding vector(768) NOT NULL
            )
        """)


def read_index():
    initialize()
    with connect() as conn:
        rows = conn.execute("""
            SELECT source, content, fingerprint, embedding::text AS embedding
            FROM knowledge_vectors ORDER BY source
        """).fetchall()
    for row in rows:
        row["embedding"] = json.loads(row["embedding"])
    return rows


def save_index(documents, model):
    # Validate everything before touching the currently searchable index.
    if not documents:
        raise ValueError("Refusing to replace the index with an empty collection.")
    values = [(d["source"], d["content"], d["fingerprint"], model,
               vector_literal(d["embedding"])) for d in documents]
    with connect() as conn:
        conn.execute("LOCK TABLE knowledge_vectors IN EXCLUSIVE MODE")
        conn.execute("DELETE FROM knowledge_vectors")
        with conn.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO knowledge_vectors
                    (source, content, fingerprint, model, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
            """, values)
    # Context-manager commit is atomic; exceptions roll back the entire change.


def search(vector, top_k, model):
    literal = vector_literal(vector)
    with connect() as conn:
        metadata = conn.execute("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE model <> %s) AS incompatible
            FROM knowledge_vectors
        """, (model,)).fetchone()
        if not metadata["total"]:
            raise ValueError("Knowledge index is empty. Run retrieval.py --index.")
        if metadata["incompatible"]:
            raise ValueError("Embedding model changed. Run retrieval.py --index.")
        return conn.execute("""
            SELECT source, content, fingerprint,
                   1 - (embedding <=> %s::vector) AS score
            FROM knowledge_vectors
            ORDER BY embedding <=> %s::vector, source
            LIMIT %s
        """, (literal, literal, top_k)).fetchall()
