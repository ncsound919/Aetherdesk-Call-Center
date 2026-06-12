import asyncio
import os
from typing import Any

from langchain_community.document_loaders import CSVLoader, JSONLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

KB_DIR = os.getenv("KB_DIR", "data/kb")
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


class RAGService:
    def __init__(
        self,
        kb_dir: str = KB_DIR,
        chroma_dir: str = CHROMA_DIR,
        embedding_model: str = EMBEDDING_MODEL
    ):
        self.kb_dir = kb_dir
        self.chroma_dir = chroma_dir
        self.embedding_model = embedding_model
        self._vectorstore: Chroma | None = None
        self._embeddings = None
        self._lock = asyncio.Lock()
        self._query_cache: dict[str, list[dict[str, Any]]] = {} # Optimization: Cache recent results

    def _get_embeddings(self):
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(model_name=self.embedding_model)
        return self._embeddings

    async def initialize(self):
        if self._vectorstore is None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_or_create_index)

    def _load_or_create_index(self):
        if os.path.exists(self.chroma_dir) and os.listdir(self.chroma_dir):
            self._vectorstore = Chroma(
                persist_directory=self.chroma_dir,
                embedding_function=self._get_embeddings()
            )
        else:
            self._rebuild_index()

    def _rebuild_index(self):
        os.makedirs(self.chroma_dir, exist_ok=True)

        documents = []
        if os.path.exists(self.kb_dir):
            for filename in os.listdir(self.kb_dir):
                filepath = os.path.join(self.kb_dir, filename)
                if filename.endswith('.txt'):
                    loader = TextLoader(filepath, encoding='utf-8')
                    documents.extend(loader.load())
                elif filename.endswith('.csv'):
                    loader = CSVLoader(filepath)
                    documents.extend(loader.load())
                elif filename.endswith('.json'):
                    loader = JSONLoader(filepath)
                    documents.extend(loader.load())

        if not documents:
            documents = [
                Document(
                    page_content="Billing FAQ: Invoice questions can be answered by providing your invoice ID. Refunds typically process within 5-7 business days.",
                    metadata={"source": "default", "category": "billing"}
                ),
                Document(
                    page_content="Pharmacy FAQ: Prescription refills require your prescription number. Doctor callbacks are available for medication questions.",
                    metadata={"source": "default", "category": "pharmacy"}
                ),
                Document(
                    page_content="Order Status: To check order status, provide your order ID and the shipping ZIP code.",
                    metadata={"source": "default", "category": "orders"}
                ),
            ]

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )
        chunks = splitter.split_documents(documents)

        self._vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding_function=self._get_embeddings(),
            persist_directory=self.chroma_dir
        )

    async def query(self, query_text: str, k: int = 4) -> list[dict[str, Any]]:
        # Optimization: Check cache first
        cache_key = f"{query_text}:{k}"
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        if self._vectorstore is None:
            await self.initialize()

        loop = asyncio.get_running_loop()
        docs = await loop.run_in_executor(
            None,
            lambda: self._vectorstore.similarity_search(query_text, k=k)
        )

        results = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in docs
        ]

        # Simple cache eviction (max 100 entries)
        if len(self._query_cache) > 100:
            self._query_cache.pop(next(iter(self._query_cache)))
        self._query_cache[cache_key] = results

        return results

    async def query_with_score(self, query_text: str, k: int = 4) -> list[dict[str, Any]]:
        if self._vectorstore is None:
            await self.initialize()

        loop = asyncio.get_running_loop()
        docs_and_scores = await loop.run_in_executor(
            None,
            lambda: self._vectorstore.similarity_search_with_score(query_text, k=k)
        )

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score
            }
            for doc, score in docs_and_scores
        ]

    def rebuild_index(self):
        self._vectorstore = None
        self._query_cache = {} # Optimization: Clear cache on rebuild
        self._load_or_create_index()


rag_service = RAGService()
