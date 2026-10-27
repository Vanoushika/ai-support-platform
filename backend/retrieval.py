import argparse
import asyncio
import hashlib
import json

from observability import observed
import math
from pathlib import Path

import httpx

from database import get_connection

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
EMBEDDING_MODEL = "nomic-embed-text"
from settings import OLLAMA_BASE_URL

EMBEDDING_URL = f"{OLLAMA_BASE_URL}/api/embed"


def initialize_index():
    connection = get_connection()

    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    source TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    embedding TEXT NOT NULL
                )
                """
            )
    finally:
        connection.close()


def read_index() -> list[dict]:
    initialize_index()
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT source, content, fingerprint, embedding
            FROM knowledge_documents
            ORDER BY source
            """
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "source": row["source"],
            "content": row["content"],
            "fingerprint": row["fingerprint"],
            "embedding": json.loads(row["embedding"]),
        }
        for row in rows
    ]


def save_index(documents: list[dict]):
    connection = get_connection()

    try:
        # Replace the index atomically after all embeddings are ready.
        with connection:
            connection.execute("DELETE FROM knowledge_documents")

            connection.executemany(
                """
                INSERT INTO knowledge_documents (
                    source, content, fingerprint, embedding
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        document["source"],
                        document["content"],
                        document["fingerprint"],
                        json.dumps(document["embedding"]),
                    )
                    for document in documents
                ],
            )
    finally:
        connection.close()


def fingerprint(content: str) -> str:
    value = f"{EMBEDDING_MODEL}\nsearch_document: {content}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def embed_texts(
    client: httpx.AsyncClient,
    texts: list[str],
) -> list[list[float]]:
    response = await client.post(
        EMBEDDING_URL,
        json={
            "model": EMBEDDING_MODEL,
            "input": texts,
            "truncate": False,
        },
    )
    response.raise_for_status()

    vectors = response.json().get("embeddings")

    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError("Ollama returned invalid embeddings.")

    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise ValueError("Ollama returned an empty embedding.")

        if not all(
            isinstance(value, (int, float))
            and math.isfinite(value)
            for value in vector
        ):
            raise ValueError("Ollama returned invalid embedding values.")

    return vectors


async def index_documents() -> dict:
    existing = await asyncio.to_thread(read_index)
    existing_by_source = {
        document["source"]: document
        for document in existing
    }

    documents = []
    changed_documents = []
    reused = 0

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()

        if not content:
            continue

        document = {
            "source": path.name,
            "content": content,
            "fingerprint": fingerprint(content),
        }

        previous = existing_by_source.get(path.name)

        if (
            previous is not None
            and previous["fingerprint"] == document["fingerprint"]
        ):
            document["embedding"] = previous["embedding"]
            reused += 1
        else:
            changed_documents.append(document)

        documents.append(document)

    if not documents:
        raise ValueError(
            f"No non-empty Markdown files found in {KNOWLEDGE_DIR}. "
            "The existing index has not been changed."
        )

    if changed_documents:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=10.0)
        ) as client:
            vectors = await embed_texts(
                client,
                [
                    f"search_document: {document['content']}"
                    for document in changed_documents
                ],
            )

        for document, vector in zip(changed_documents, vectors):
            document["embedding"] = vector

    current_sources = {document["source"] for document in documents}
    removed = len(set(existing_by_source) - current_sources)

    await asyncio.to_thread(save_index, documents)

    return {
        "indexed_documents": len(documents),
        "new_or_updated_embeddings": len(changed_documents),
        "reused_embeddings": reused,
        "removed_documents": removed,
    }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(
            "Embedding dimensions do not match. Rebuild the index."
        )

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(y * y for y in b))

    if magnitude_a == 0 or magnitude_b == 0:
        raise ValueError("Received a zero-length embedding vector.")

    return dot_product / (magnitude_a * magnitude_b)


@observed("knowledge.search")
async def search_knowledge(query: str, top_k: int = 2) -> list[dict]:
    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    documents = await asyncio.to_thread(read_index)

    if not documents:
        raise ValueError(
            "Knowledge index is empty. Run: python retrieval.py --index"
        )

    # Detect configuration changes or inconsistent stored content.
    for document in documents:
        if document["fingerprint"] != fingerprint(document["content"]):
            raise ValueError(
                "Knowledge index needs rebuilding. "
                "Run: python retrieval.py --index"
            )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(180.0, connect=10.0)
    ) as client:
        vectors = await embed_texts(
            client,
            [f"search_query: {query}"],
        )

    query_vector = vectors[0]

    results = [
        {
            "source": document["source"],
            "content": document["content"],
            "score": cosine_similarity(
                query_vector,
                document["embedding"],
            ),
        }
        for document in documents
    ]

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]


async def main():
    parser = argparse.ArgumentParser(
        description="Build or search the local knowledge index."
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Index new or changed Markdown articles.",
    )
    parser.add_argument(
        "--query",
        default="I forgot my password and the recovery email never arrived.",
        help="Question to search for.",
    )
    args = parser.parse_args()

    if args.index:
        result = await index_documents()
        print(json.dumps(result, indent=2))
        return

    results = await search_knowledge(args.query)

    print(f"\nQuestion: {args.query}\n")

    for result in results:
        print(f"Source: {result['source']}")
        print(f"Similarity: {result['score']:.3f}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
