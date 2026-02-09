"""
brain.py – Core orchestration: ingest → chunk → embed → cache → retrieve → rerank.

Upgrades over v0.1:
  • Semantic cache with fuzzy matching (similarity threshold, not exact hash).
  • LRU-style cache eviction with configurable max size.
  • Sentence-aware chunking with overlap (delegates to file_loader.chunk_text).
  • Distance-aware retrieval — low-relevance results are dropped automatically.
  • Context deduplication and reranking by relevance score.
  • Batch upsert for faster ingestion.
  • Configurable parameters exposed via __init__.
"""

import hashlib
import logging
from collections import OrderedDict
from typing import Optional

from .storage import LocalMemory
from .web_reader import crawl_and_extract
from .file_loader import (
    ingest_folder,
    load_text_file,
    load_pdf_pages,
    load_json_file,
    chunk_text,
)

logger = logging.getLogger("memloop.brain")


class MemLoop:
    """Plug-and-play memory engine for AI agents."""

    def __init__(
        self,
        db_path: str = "./memloop_data",
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        cache_max_size: int = 512,
        cache_similarity_threshold: float = 0.15,
        retrieval_max_distance: float = 1.2,
        short_term_limit: int = 10,
    ):
        self.memory = LocalMemory(path=db_path)

        # Chunking config
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Semantic cache — OrderedDict gives us LRU for free
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._cache_max = cache_max_size
        self._cache_sim_threshold = cache_similarity_threshold

        # Retrieval
        self._max_distance = retrieval_max_distance

        # Short-term conversational buffer
        self.short_term: list[str] = []
        self._st_limit = short_term_limit

    # ── helpers ───────────────────────────────────────────

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.strip().lower().encode()).hexdigest()

    def _chunk(self, text: str) -> list[str]:
        """Sentence-aware chunking with overlap."""
        return chunk_text(
            text,
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
            respect_sentences=True,
        )

    # ── cache helpers ─────────────────────────────────────

    def _cache_put(self, key: str, value: str) -> None:
        """Store in LRU cache, evicting oldest if full."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    def _cache_get(self, query: str) -> Optional[str]:
        """
        Two-tier cache lookup:
          1. Exact hash match  (O(1)).
          2. Fuzzy vector similarity against cached keys (O(n) but n is small).
        """
        key = self._hash(query)

        # Tier 1 — exact
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        # Tier 2 — fuzzy (ask the vector DB if a near-duplicate exists)
        existing = self.memory.find_similar(query, threshold=self._cache_sim_threshold)
        if existing:
            existing_key = self._hash(existing)
            if existing_key in self._cache:
                self._cache.move_to_end(existing_key)
                return self._cache[existing_key]

        return None

    # ── ingestion ─────────────────────────────────────────

    def learn_url(self, url: str, follow_links: bool = False, max_pages: int = 10) -> int:
        """
        Scrape *url*, chunk the text, and store every chunk with source metadata.
        Returns the number of chunks stored.
        """
        self._cache.clear()
        # Get raw page text in large chunks so we can re-chunk with sentence awareness
        raw_chunks = crawl_and_extract(
            url,
            chunk_size=4000,   # large raw chunks to preserve context
            overlap=200,
            follow_links=follow_links,
            max_pages=max_pages,
        )

        # Merge all raw text, then re-chunk with sentence awareness
        full_text = "\n\n".join(raw_chunks)
        smart_chunks = self._chunk(full_text)

        texts: list[str] = []
        metas: list[dict] = []
        for idx, c in enumerate(smart_chunks):
            if c.strip():
                texts.append(c)
                metas.append({"source": url, "type": "web", "chunk_index": idx})

        count = self.memory.save_batch(texts, metas)
        logger.info("Learned %d chunks from %s", count, url)
        return count

    def learn_local(self, folder_path: str) -> int:
        """Ingest every supported file under *folder_path*."""
        self._cache.clear()
        docs = ingest_folder(folder_path)

        texts: list[str] = []
        metas: list[dict] = []

        for text, meta in docs:
            for idx, c in enumerate(self._chunk(text)):
                if c.strip():
                    texts.append(c)
                    metas.append({**meta, "chunk_index": idx})

        count = self.memory.save_batch(texts, metas)
        logger.info("Learned %d chunks from folder %s", count, folder_path)
        return count

    def learn_doc(self, file_path: str, page_number: Optional[int] = None) -> int:
        """Ingest a single document (PDF, TXT, MD, JSON)."""
        self._cache.clear()
        texts: list[str] = []
        metas: list[dict] = []

        ext = file_path.lower()
        if ext.endswith(".pdf"):
            pages = load_pdf_pages(file_path)
            for text, meta in pages:
                if page_number is not None and meta.get("page") != page_number:
                    continue
                for idx, c in enumerate(self._chunk(text)):
                    if c.strip():
                        texts.append(c)
                        metas.append({**meta, "chunk_index": idx})

        elif ext.endswith(".json"):
            items = load_json_file(file_path)
            for text, meta in items:
                for idx, c in enumerate(self._chunk(text)):
                    if c.strip():
                        texts.append(c)
                        metas.append({**meta, "chunk_index": idx})
        else:
            content = load_text_file(file_path)
            for idx, c in enumerate(self._chunk(content)):
                if c.strip():
                    texts.append(c)
                    metas.append({
                        "source": file_path,
                        "type": "text",
                        "page": 1,
                        "chunk_index": idx,
                    })

        count = self.memory.save_batch(texts, metas)
        logger.info("Learned %d chunks from %s", count, file_path)
        return count

    def add_memory(self, text: str) -> None:
        """Store *text* in long-term vector DB and short-term buffer."""
        self._cache.clear()
        self.memory.save(text, metadata={"type": "user_input"})

        self.short_term.append(text)
        if len(self.short_term) > self._st_limit:
            self.short_term.pop(0)

    # ── retrieval ─────────────────────────────────────────

    def recall(
        self,
        query: str,
        n_results: int = 5,
        include_short_term: bool = True,
    ) -> str:
        """
        Retrieve the best context for *query*.

        Pipeline:
          1. Check semantic cache (exact + fuzzy).
          2. Vector search with distance filtering.
          3. Deduplicate & rerank results by relevance.
          4. Prepend short-term buffer for conversational context.
          5. Store result in cache for future hits.
        """
        # 1. Cache lookup
        cached = self._cache_get(query)
        if cached:
            logger.debug("Cache hit for query: %s", query[:60])
            return f"[CACHE HIT]\n{cached}"

        # 2. Vector search
        documents, metadatas, distances = self.memory.search_with_meta(
            query,
            n_results=n_results * 2,  # over-fetch so we can filter + dedup
            max_distance=self._max_distance,
        )

        # 3. Deduplicate (by content similarity) and skip trivial self-matches
        seen_hashes: set[str] = set()
        pairs: list[tuple[str, dict, float]] = []

        for doc, meta, dist in zip(documents, metadatas, distances):
            if doc.strip().lower() == query.strip().lower():
                continue
            h = self._hash(doc)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            pairs.append((doc, meta, dist))

        # Sort by distance (ascending = most relevant first) and take top n
        pairs.sort(key=lambda x: x[2])
        pairs = pairs[:n_results]

        if not pairs:
            return "No relevant memories found for this query."

        # 4. Build response with citations
        lines: list[str] = []

        # Optionally prepend short-term context
        if include_short_term and self.short_term:
            recent = " | ".join(self.short_term[-3:])
            lines.append(f"[Recent Context] {recent}\n")

        lines.append("Found References:")
        for i, (doc, meta, dist) in enumerate(pairs, start=1):
            source = meta.get("source", "unknown")
            page = meta.get("page", "—")
            relevance = max(0.0, round(1.0 - dist, 3))
            # Show more text for highly relevant results
            preview_len = 300 if relevance > 0.7 else 200
            preview = doc[:preview_len].rstrip()
            if len(doc) > preview_len:
                preview += "…"
            lines.append(
                f"  [{i}] (relevance: {relevance}) {preview}\n"
                f"       ↳ Source: {source}, Page: {page}"
            )

        response = "\n".join(lines)

        # 5. Cache the result
        self._cache_put(self._hash(query), response)

        return response

    # ── management ────────────────────────────────────────

    def forget_cache(self) -> None:
        """Clear the semantic cache."""
        self._cache.clear()

    def forget_source(self, source: str) -> None:
        """Delete all chunks from a specific source (URL or file path)."""
        self.memory.delete_by_source(source)
        self._cache.clear()

    def status(self) -> dict:
        """Snapshot of the memory state."""
        return {
            "long_term_count": self.memory.count(),
            "short_term_count": len(self.short_term),
            "cache_size": len(self._cache),
            "cache_max": self._cache_max,
        }

    def __repr__(self) -> str:
        s = self.status()
        return (
            f"MemLoop(long_term={s['long_term_count']}, "
            f"short_term={s['short_term_count']}, "
            f"cache={s['cache_size']}/{s['cache_max']})"
        )
