"""ContextInjector - RAG system for company context in AgentFarm.

Provides intelligent context injection for Early Access users:
- ChromaDB for semantic search of company documents
- Sentence-transformers for embeddings
- Integration with SecureVault for secure storage
- Automatic context extraction for agent prompts

Based on patterns from GraphRAG-projekt/hybrid_memory.py
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextResult:
    """A search result with relevance score."""

    text: str
    source: str
    score: float
    metadata: dict[str, Any]


@dataclass
class InjectionResult:
    """Result of context injection for an agent."""

    context: str
    sources: list[str]
    token_estimate: int


class ContextInjector:
    """RAG-based context injection for company documents.

    Stores and retrieves company-specific context using semantic search,
    enabling agents to work with company-specific knowledge.

    Usage:
        injector = ContextInjector(storage_path=".agentfarm/context")

        # Index company documents
        await injector.add_document("api_guide.md", api_content, {"type": "api"})
        await injector.add_document("code_style.md", style_content, {"type": "style"})

        # Get context for a query
        result = await injector.get_context_for_query(
            "How should I format API responses?",
            max_tokens=2000
        )
        print(result.context)

    Note: Requires optional dependencies:
        pip install chromadb sentence-transformers
    """

    DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    DEFAULT_COLLECTION = "company_context"
    CHARS_PER_TOKEN = 4  # Rough estimate

    def __init__(
        self,
        storage_path: Path | str = ".agentfarm/context",
        embedding_model: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize ContextInjector.

        Args:
            storage_path: Directory for ChromaDB persistence
            embedding_model: Sentence-transformer model name
            collection_name: ChromaDB collection name
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.embedding_model_name = embedding_model or self.DEFAULT_EMBEDDING_MODEL
        self.collection_name = collection_name or self.DEFAULT_COLLECTION

        # Lazy-loaded components
        self._chroma_client = None
        self._collection = None
        self._embedding_model = None
        self._available: bool | None = None

    @property
    def is_available(self) -> bool:
        """Check if dependencies are available."""
        if self._available is None:
            try:
                import chromadb  # noqa: F401
                from sentence_transformers import SentenceTransformer  # noqa: F401

                self._available = True
            except ImportError:
                logger.warning(
                    "RAG dependencies not installed. "
                    "pip install chromadb sentence-transformers"
                )
                self._available = False
        return self._available

    @property
    def embedding_model(self) -> Any:
        """Lazy-load sentence-transformer model."""
        if self._embedding_model is None:
            if not self.is_available:
                raise RuntimeError("sentence-transformers not installed")

            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer(self.embedding_model_name)
            logger.info("Loaded embedding model: %s", self.embedding_model_name)
        return self._embedding_model

    @property
    def chroma_client(self) -> Any:
        """Lazy-load ChromaDB client."""
        if self._chroma_client is None:
            if not self.is_available:
                raise RuntimeError("chromadb not installed")

            import chromadb

            self._chroma_client = chromadb.PersistentClient(
                path=str(self.storage_path / "chroma_db")
            )
            logger.info("Initialized ChromaDB at %s", self.storage_path)
        return self._chroma_client

    @property
    def collection(self) -> Any:
        """Get or create the ChromaDB collection."""
        if self._collection is None:
            self._collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Company context for AgentFarm"}
            )
        return self._collection

    def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text."""
        embedding = self.embedding_model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def _generate_doc_id(self, filename: str, content: str) -> str:
        """Generate unique document ID."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"doc_{filename.replace('/', '_')}_{content_hash}"

    async def add_document(
        self,
        filename: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> int:
        """Add a document to the context store.

        Args:
            filename: Document filename/path
            content: Document content
            metadata: Optional metadata (type, author, etc.)
            chunk_size: Characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            Number of chunks added
        """
        if not self.is_available:
            raise RuntimeError("RAG dependencies not installed")

        # Split into chunks
        chunks = self._split_into_chunks(content, chunk_size, chunk_overlap)

        # Prepare for batch insert
        ids = []
        embeddings = []
        documents = []
        metadatas = []

        base_metadata = {
            "filename": filename,
            "indexed_at": datetime.now().isoformat(),
            **(metadata or {}),
        }

        for i, chunk in enumerate(chunks):
            chunk_id = f"{self._generate_doc_id(filename, content)}_{i}"
            embedding = self._generate_embedding(chunk)

            ids.append(chunk_id)
            embeddings.append(embedding)
            documents.append(chunk)
            metadatas.append({
                **base_metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info("Added %d chunks from %s", len(chunks), filename)
        return len(chunks)

    async def add_text(
        self,
        text: str,
        source: str = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a text snippet directly (no chunking).

        Args:
            text: Text to add
            source: Source identifier
            metadata: Optional metadata

        Returns:
            Document ID
        """
        if not self.is_available:
            raise RuntimeError("RAG dependencies not installed")

        doc_id = self._generate_doc_id(source, text)
        embedding = self._generate_embedding(text)

        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "source": source,
                "indexed_at": datetime.now().isoformat(),
                **(metadata or {}),
            }],
        )

        logger.info("Added text snippet: %s", doc_id)
        return doc_id

    async def search(
        self,
        query: str,
        n_results: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[ContextResult]:
        """Search for relevant context.

        Args:
            query: Search query
            n_results: Max results to return
            metadata_filter: Filter by metadata

        Returns:
            List of ContextResult ordered by relevance
        """
        if not self.is_available:
            raise RuntimeError("RAG dependencies not installed")

        query_embedding = self._generate_embedding(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=metadata_filter,
        )

        context_results = []
        for i, doc in enumerate(results["documents"][0]):
            context_results.append(ContextResult(
                text=doc,
                source=results["metadatas"][0][i].get("filename", "unknown"),
                score=1.0 - results["distances"][0][i],  # Convert distance to similarity
                metadata=results["metadatas"][0][i],
            ))

        return context_results

    async def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 2000,
        n_results: int = 5,
    ) -> InjectionResult:
        """Get formatted context for injection into agent prompts.

        Args:
            query: The query/task to find context for
            max_tokens: Maximum tokens for context
            n_results: Number of results to consider

        Returns:
            InjectionResult with formatted context
        """
        results = await self.search(query, n_results=n_results)

        if not results:
            return InjectionResult(
                context="",
                sources=[],
                token_estimate=0,
            )

        # Build context within token limit
        max_chars = max_tokens * self.CHARS_PER_TOKEN
        context_parts = ["# Company Context\n"]
        sources = set()
        current_chars = len(context_parts[0])

        for result in results:
            chunk_text = f"\n## From {result.source} (relevance: {result.score:.2f})\n{result.text}\n"
            chunk_chars = len(chunk_text)

            if current_chars + chunk_chars > max_chars:
                # Truncate if needed
                remaining = max_chars - current_chars - 50  # Buffer
                if remaining > 100:
                    truncated = chunk_text[:remaining] + "\n[...truncated]"
                    context_parts.append(truncated)
                    sources.add(result.source)
                break

            context_parts.append(chunk_text)
            sources.add(result.source)
            current_chars += chunk_chars

        full_context = "".join(context_parts)

        return InjectionResult(
            context=full_context,
            sources=list(sources),
            token_estimate=len(full_context) // self.CHARS_PER_TOKEN,
        )

    async def delete_document(self, filename: str) -> int:
        """Delete all chunks from a document.

        Args:
            filename: Document filename to delete

        Returns:
            Number of chunks deleted
        """
        if not self.is_available:
            raise RuntimeError("RAG dependencies not installed")

        # Find all chunks with this filename
        results = self.collection.get(where={"filename": filename})

        if not results["ids"]:
            return 0

        self.collection.delete(ids=results["ids"])
        logger.info("Deleted %d chunks from %s", len(results["ids"]), filename)
        return len(results["ids"])

    async def clear(self) -> None:
        """Clear all documents from the collection."""
        if not self.is_available:
            return

        try:
            self.chroma_client.delete_collection(self.collection_name)
            self._collection = None
            logger.info("Cleared context collection")
        except Exception as e:
            logger.warning("Failed to clear collection: %s", e)

    def _split_into_chunks(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
    ) -> list[str]:
        """Split text into overlapping chunks.

        Tries to split on paragraph boundaries when possible.
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        paragraphs = text.split("\n\n")

        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # Handle very long paragraphs
                if len(para) > chunk_size:
                    # Split on sentences or words
                    words = para.split()
                    current_chunk = ""
                    for word in words:
                        if len(current_chunk) + len(word) + 1 <= chunk_size:
                            current_chunk += word + " "
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = word + " "
                else:
                    current_chunk = para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Add overlap between chunks
        if overlap > 0 and len(chunks) > 1:
            overlapped_chunks = [chunks[0]]
            for i in range(1, len(chunks)):
                prev_end = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
                overlapped_chunks.append(prev_end + " " + chunks[i])
            chunks = overlapped_chunks

        return chunks

    def get_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        if not self.is_available:
            return {"available": False}

        try:
            count = self.collection.count()
            return {
                "available": True,
                "document_count": count,
                "embedding_model": self.embedding_model_name,
                "storage_path": str(self.storage_path),
            }
        except Exception as e:
            return {"available": True, "error": str(e)}
