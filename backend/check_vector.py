"""Read-only integration smoke check against the running indexed database."""
import asyncio
import json
from settings import VECTOR_BACKEND
from retrieval import search_knowledge
from vector_store import connect

async def main():
    if VECTOR_BACKEND != "pgvector":
        raise SystemExit("Expected VECTOR_BACKEND=pgvector; refusing to test SQLite.")
    with connect() as conn:
        version = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        rows = conn.execute("SELECT source, vector_dims(embedding) AS dimensions FROM knowledge_vectors ORDER BY source").fetchall()
    if not version or not rows or any(r["dimensions"] != 768 for r in rows):
        raise SystemExit("FAIL: vector extension, indexed documents, or dimensions missing.")
    print(json.dumps({"pgvector_version": version["extversion"], "documents": rows}, indent=2))
    cases = [
        ("I forgot my password and the recovery email never arrived.", "password_reset.md"),
        ("I paid for premium but the features are still locked.", "premium_access.md"),
        ("I was charged twice. Please refund the duplicate payment.", "refund_requests.md"),
    ]
    for question, expected in cases:
        hits = await search_knowledge(question, top_k=1)
        if not hits or hits[0]["source"] != expected:
            raise SystemExit(f"FAIL: expected {expected}; got {hits}")
        print(f"PASS: {expected} (similarity {hits[0]['score']:.3f})")
    print("PASS: all three retrieval smoke cases. This is not an accuracy benchmark.")

if __name__ == "__main__":
    asyncio.run(main())
