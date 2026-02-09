import hashlib
import chromadb
from chromadb.utils import embedding_functions


class LocalMemory:
    """Thin wrapper around ChromaDB with local SentenceTransformer embeddings."""

    def __init__(self, path="./memloop_data"):
        self.client = chromadb.PersistentClient(path=path)
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self.collection = self.client.get_or_create_collection(
            name="agent_memory",
            embedding_function=self.ef,
        )

    def save(self, text, metadata=None):
        """Upsert a document (safe for duplicates)."""
        meta = metadata or {}
        unique_str = (
            text
            + str(meta.get("source", ""))
            + str(meta.get("page", ""))
            + str(meta.get("chunk_index", ""))
        )
        doc_id = hashlib.md5(unique_str.encode()).hexdigest()
        self.collection.upsert(
            documents=[text],
            metadatas=[meta],
            ids=[doc_id],
        )

    def search_with_meta(self, query, n_results=3):
        """Return (documents, metadatas) for top-n results."""
        if self.collection.count() == 0:
            return [], []
        actual_n = min(n_results, self.collection.count())
        results = self.collection.query(query_texts=[query], n_results=actual_n)
        return results["documents"][0], results["metadatas"][0]

    def count(self):
        """Number of documents stored."""
        return self.collection.count()
