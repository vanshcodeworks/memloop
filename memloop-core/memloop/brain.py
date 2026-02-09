"""Core orchestration layer that ties storage, caching, and retrieval."""

import hashlib
from .storage import LocalMemory
from .web_reader import crawl_and_extract
from .file_loader import ingest_folder, load_text_file, load_pdf_pages

class MemLoop:
    """Plug-and-play memory engine for AI agents."""

    def __init__(self, db_path="./memloop_data"):
        self.memory = LocalMemory(path=db_path)
        self.short_term: list[str] = []
        self.cache: dict[str, str] = {}

    # ── helpers ───────────────────────────────────────────
    def _hash(self, text: str) -> str:
        """Create a unique hash for semantic caching."""
        return hashlib.md5(text.encode()).hexdigest()

    def _chunk_text(self, text: str, chunk_size: int = 500):
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    # ── ingestion ─────────────────────────────────────────
    def learn_url(self, url: str) -> int:
        """Scrape *url*, chunk it, and save every chunk. Returns chunk count."""
        self.cache.clear()
        chunks = crawl_and_extract(url)
        count = 0
        for chunk in chunks:
            if chunk and chunk.strip():
                self.memory.save(chunk, metadata={"source": url, "type": "web"})
                count += 1
        return count

    def learn_local(self, folder_path: str) -> int:
        """Ingest all supported files from a local folder."""
        self.cache.clear()
        docs = ingest_folder(folder_path)
        count = 0

        for text, meta in docs:
            for idx, chunk in enumerate(self._chunk_text(text)):
                if chunk.strip():
                    meta_with_chunk = {**meta, "chunk_index": idx}
                    self.memory.save(chunk, metadata=meta_with_chunk)
                    count += 1
        return count

    def learn_doc(self, file_path: str, page_number: int | None = None) -> int:
        """Ingest a specific document (or a specific page for PDFs)."""
        self.cache.clear()
        count = 0

        if file_path.lower().endswith(".pdf"):
            pages = load_pdf_pages(file_path)
            for text, meta in pages:
                if page_number and meta.get("page") != page_number:
                    continue
                for idx, chunk in enumerate(self._chunk_text(text)):
                    if chunk.strip():
                        meta_with_chunk = {**meta, "chunk_index": idx}
                        self.memory.save(chunk, metadata=meta_with_chunk)
                        count += 1
            return count

        content = load_text_file(file_path)
        for idx, chunk in enumerate(self._chunk_text(content)):
            if chunk.strip():
                meta = {"source": file_path, "type": "text", "page": 1, "chunk_index": idx}
                self.memory.save(chunk, metadata=meta)
                count += 1
        return count

    def add_memory(self, text: str) -> None:
        """Store *text* in both long-term vector DB and short-term buffer."""
        # 1. Invalidate cache so we don't return old/stale answers
        self.cache.clear()

        # 2. Save to Vector Store (Long Term)
        self.memory.save(text, metadata={"type": "user_input"})
        
        # 3. Update Working Memory (Short Term)
        self.short_term.append(text)
        if len(self.short_term) > 5:
            self.short_term.pop(0)

    # ── retrieval ─────────────────────────────────────────
    def recall(self, query: str, n_results: int = 3) -> str:
        """Retrieve context for *query*. Uses cache when possible."""
        key = self._hash(query)
        
        # 1. Check Cache (Speed Optimization)
        if key in self.cache:
            return f"[CACHE HIT] {self.cache[key]}"

        documents, metadatas = self.memory.search_with_meta(query, n_results=n_results)
        pairs = [
            (doc, meta)
            for doc, meta in zip(documents, metadatas)
            if doc.strip().lower() != query.strip().lower()
        ]

        response = "Found References:\n"
        for i, (doc, meta) in enumerate(pairs, start=1):
            source = meta.get("source", "unknown")
            page = meta.get("page", "?")
            response += f"[{i}] {doc[:150]}... (Ref: {source}, Page {page})\n"

        self.cache[key] = response
        return response

    # ── management ────────────────────────────────────────
    def forget_cache(self) -> None:
        """Clear the semantic cache."""
        self.cache.clear()

    def status(self) -> dict:
        """Return a snapshot of the memory state."""
        try:
            # Depending on ChromaDB version, .count() is usually available on the collection
            lt_count = self.memory.collection.count()
        except AttributeError:
            lt_count = "Unknown"

        return {
            "long_term_count": lt_count,
            "short_term_count": len(self.short_term),
            "cache_size": len(self.cache),
        }

    def __repr__(self) -> str:
        s = self.status()
        return (
            f"MemLoop(long_term={s['long_term_count']}, "
            f"short_term={s['short_term_count']}, "
            f"cache={s['cache_size']})"
        )
