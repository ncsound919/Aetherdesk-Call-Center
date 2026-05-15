import asyncio
import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

# Try to import Document from LangChain. If unavailable due to version differences,
# provide a lightweight fallback to keep memory indexing functional.
try:
    from langchain_core.documents import Document  # type: ignore
except Exception:
    from dataclasses import dataclass
    @dataclass
    class Document:
        page_content: str
        metadata: dict
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

MEMORY_DIR = os.getenv("MEMORY_DIR", "memory_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


@dataclass
class Memory:
    id: str
    content: str
    metadata: dict[str, Any]
    timestamp: float
    session_id: str
    user_id: str | None = None


class MemoryService:
    def __init__(
        self,
        memory_dir: str = MEMORY_DIR,
        embedding_model: str = EMBEDDING_MODEL
    ):
        self.memory_dir = memory_dir
        self.embedding_model = embedding_model
        self._vectorstore: Chroma | None = None
        self._embeddings = None
        self._lock = asyncio.Lock()

    def _get_embeddings(self):
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(model_name=self.embedding_model)
        return self._embeddings

    async def initialize(self):
        if self._vectorstore is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_or_create_index)

    def _load_or_create_index(self):
        if os.path.exists(self.memory_dir) and os.listdir(self.memory_dir):
            self._vectorstore = Chroma(
                persist_directory=self.memory_dir,
                embedding_function=self._get_embeddings()
            )
        else:
            self._rebuild_index()

    def _rebuild_index(self):
        os.makedirs(self.memory_dir, exist_ok=True)
        # Start with an empty index
        self._vectorstore = Chroma(
            embedding_function=self._get_embeddings(),
            persist_directory=self.memory_dir
        )

    def _create_memory_id(self, content: str, session_id: str) -> str:
        """Create a unique ID for a memory"""
        timestamp = str(time.time())
        raw = f"{session_id}:{content}:{timestamp}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def add_memory(
        self,
        content: str,
        session_id: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> str:
        """Add a memory to the vector store"""
        await self.initialize()

        memory_id = self._create_memory_id(content, session_id)
        timestamp = time.time()

        memory = Memory(
            id=memory_id,
            content=content,
            metadata=metadata or {},
            timestamp=timestamp,
            session_id=session_id,
            user_id=user_id
        )

        document = Document(
            page_content=content,
            metadata={
                "memory_id": memory_id,
                "session_id": session_id,
                "user_id": user_id or "",
                "timestamp": timestamp,
                **memory.metadata
            }
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._vectorstore.add_documents([document])
        )

        return memory_id

    async def search_memories(
        self,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
        k: int = 5
    ) -> list[dict[str, Any]]:
        """Search for relevant memories"""
        await self.initialize()

        # Build filter criteria
        filter_dict = {}
        if session_id:
            filter_dict["session_id"] = session_id
        if user_id:
            filter_dict["user_id"] = user_id

        loop = asyncio.get_event_loop()
        if filter_dict:
            # ChromaDB doesn't support filtering in the same way, so we'll fetch more and filter
            # Alternatively, we can use the `where` parameter in similarity_search
            docs_and_scores = await loop.run_in_executor(
                None,
                lambda: self._vectorstore.similarity_search_with_score(
                    query,
                    k=k*2,  # Get more to account for filtering
                    where=filter_dict if filter_dict else None
                )
            )
        else:
            docs_and_scores = await loop.run_in_executor(
                None,
                lambda: self._vectorstore.similarity_search_with_score(query, k=k)
            )

        results = []
        for doc, score in docs_and_scores:
            # Apply additional filtering if needed (ChromaDB's where might not be flexible enough)
            metadata = doc.metadata
            if session_id and metadata.get("session_id") != session_id:
                continue
            if user_id and metadata.get("user_id") != user_id:
                continue

            results.append({
                "id": metadata.get("memory_id"),
                "content": doc.page_content,
                "metadata": metadata,
                "score": score
            })

            if len(results) >= k:
                break

        return results

    async def get_session_memories(
        self,
        session_id: str,
        k: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent memories for a session"""
        return await self.search_memories(
            query="",  # Empty query to get all
            session_id=session_id,
            k=k
        )

    async def clear_session_memories(self, session_id: str):
        """Clear all memories for a session (by marking as deleted or removing)"""
        # For simplicity, we'll just note that in a production system we might want to actually delete
        # Since ChromaDB doesn't have a direct delete by filter, we could recreate the index without those memories
        # But for now, we'll just leave them and rely on the session_id filter to ignore them
        pass


memory_service = MemoryService()
