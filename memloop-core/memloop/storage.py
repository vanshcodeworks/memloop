"""
storage.py – High-performance local vector store with dedup, scoring & batch ops.
"""

import hashlib
import logging
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("memloop.storage")


class LocalMemory:
    """ChromaDB-backed vector store with deduplication and relevance scoring."""

    def __init__(
        self,
        path: str = "./memloop_data",
        collection_name: str = "agent_memory",
        model_name: str = "all-MiniLM-L6-v2",
        distance_fn: str = "cosine",
    ):
        self.client = chromadb.PersistentClient(path=path)

        # Embedding model (~80 MB, downloaded once)
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.ef,
            metadata={"hnsw:space": distance_fn},
        )

    # ── deterministic ID ──────────────────────────────────
    @staticmethod
    def _make_id(text: str, metadata: Optional[dict] = None) -> str:
        """Deterministic content-hash so the same chunk is never stored twice."""
        key = text.strip().lower()
        if metadata:
            key += str(metadata.get("source", ""))
            key += str(metadata.get("chunk_index", ""))
            key += str(metadata.get("page", ""))
        return hashlib.sha256(key.encode()).hexdigest()

    # ── write ─────────────────────────────────────────────
    def save(self, text: str, metadata: Optional[dict] = None) -> str:
        """Upsert a single document. Returns its ID."""
        doc_id = self._make_id(text, metadata)
        meta = metadata or {}
        # Upsert avoids "duplicate ID" errors and keeps data fresh
        self.collection.upsert(
            documents=[text],
            metadatas=[meta],
            ids=[doc_id],
        )
        return doc_id

    def save_batch(
        self,
        texts: list[str],
        metadatas: Optional[list[dict]] = None,
        batch_size: int = 256,
    ) -> int:
        """Upsert documents in efficient batches. Returns total saved count."""
        if not texts:
            return 0

        metadatas = metadatas or [{}] * len(texts)
        ids = [self._make_id(t, m) for t, m in zip(texts, metadatas)]
        total = 0

        for start in range(0, len(texts), batch_size):
            end = start + batch_size
            self.collection.upsert(
                documents=texts[start:end],
                metadatas=metadatas[start:end],
                ids=ids[start:end],
            )
            total += end - start

        return min(total, len(texts))

    # ── read ──────────────────────────────────────────────
    def search(self, query: str, n_results: int = 5) -> list[str]:
        """Simple text-only search (legacy compat)."""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        return results["documents"][0] if results["documents"] else []

    def search_with_meta(
        self,
        query: str,
        n_results: int = 5,
        max_distance: Optional[float] = None,
    ) -> tuple[list[str], list[dict], list[float]]:
        """
        Return (documents, metadatas, distances).

        *max_distance*: discard results farther than this threshold
        (cosine distance, lower = more relevant).
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        dists = results["distances"][0] if results["distances"] else []

        # Filter by distance threshold when provided
        if max_distance is not None:
            filtered = [
                (d, m, dist)
                for d, m, dist in zip(docs, metas, dists)
                if dist <= max_distance
            ]
            if filtered:
                docs, metas, dists = zip(*filtered)
                docs, metas, dists = list(docs), list(metas), list(dists)
            else:
                docs, metas, dists = [], [], []

        return docs, metas, dists

    def find_similar(self, text: str, threshold: float = 0.15) -> Optional[str]:
        """Return the closest stored doc if within *threshold*, else None."""
        docs, _, dists = self.search_with_meta(text, n_results=1)
        if docs and dists[0] <= threshold:
            return docs[0]
        return None

    # ── management ────────────────────────────────────────
    def count(self) -> int:
        return self.collection.count()

    def delete_by_source(self, source: str) -> None:
        """Remove every chunk that came from *source*."""
        # ChromaDB where filter
        self.collection.delete(where={"source": source})

    def reset(self) -> None:
        """Wipe the entire collection."""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name="agent_memory",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )