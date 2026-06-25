import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMemoryServiceInit:
    def test_default_initialization(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        assert svc.memory_dir == "memory_db"
        assert svc.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert svc._vectorstore is None
        assert svc._embeddings is None

    def test_custom_initialization(self):
        from api.services.memory import MemoryService

        svc = MemoryService(memory_dir="/tmp/test_mem", embedding_model="custom-model")
        assert svc.memory_dir == "/tmp/test_mem"
        assert svc.embedding_model == "custom-model"

    def test_singleton_instance(self):
        from api.services.memory import memory_service

        assert memory_service is not None
        assert isinstance(memory_service, object)


class TestMemoryServiceGetEmbeddings:
    def test_lazy_initialization(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        assert svc._embeddings is None

        with patch("api.services.memory.HuggingFaceEmbeddings") as mock_emb:
            mock_instance = MagicMock()
            mock_emb.return_value = mock_instance
            result = svc._get_embeddings()
            assert result == mock_instance
            assert svc._embeddings == mock_instance
            mock_emb.assert_called_once_with(model_name=svc.embedding_model)

    def test_returns_cached_embeddings(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._embeddings = "cached"
        with patch("api.services.memory.HuggingFaceEmbeddings") as mock_emb:
            result = svc._get_embeddings()
            assert result == "cached"
            mock_emb.assert_not_called()


class TestMemoryServiceInitialize:
    @pytest.mark.asyncio
    async def test_initializes_vectorstore(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        with patch.object(svc, "_load_or_create_index") as mock_load:
            await svc.initialize()
            mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_if_already_initialized(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()
        with patch.object(svc, "_load_or_create_index") as mock_load:
            await svc.initialize()
            mock_load.assert_not_called()


class TestMemoryServiceLoadOrCreateIndex:
    def test_loads_existing_index(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        mock_chroma = MagicMock()

        with patch("api.services.memory.os.path.exists", return_value=True), \
             patch("api.services.memory.os.listdir", return_value=["some_file"]), \
             patch("api.services.memory.Chroma", return_value=mock_chroma) as mock_chroma_cls, \
             patch.object(svc, "_get_embeddings", return_value="fake_emb"):
            svc._load_or_create_index()
            mock_chroma_cls.assert_called_once_with(persist_directory=svc.memory_dir, embedding_function="fake_emb")
            assert svc._vectorstore == mock_chroma

    def test_creates_new_index_when_dir_empty(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        mock_chroma = MagicMock()

        with patch("api.services.memory.os.path.exists", return_value=True), \
             patch("api.services.memory.os.listdir", return_value=[]), \
             patch("api.services.memory.os.makedirs") as mock_mkdir, \
             patch("api.services.memory.Chroma", return_value=mock_chroma) as mock_chroma_cls, \
             patch.object(svc, "_get_embeddings", return_value="fake_emb"):
            svc._rebuild_index = MagicMock()
            svc._load_or_create_index()
            svc._rebuild_index.assert_called_once()

    def test_creates_new_index_when_dir_missing(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        with patch("api.services.memory.os.path.exists", return_value=False), \
             patch.object(svc, "_rebuild_index") as mock_rebuild:
            svc._load_or_create_index()
            mock_rebuild.assert_called_once()


class TestMemoryServiceRebuildIndex:
    def test_creates_directory_and_index(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        mock_chroma = MagicMock()

        with patch("api.services.memory.os.makedirs") as mock_mkdir, \
             patch("api.services.memory.Chroma", return_value=mock_chroma) as mock_chroma_cls, \
             patch.object(svc, "_get_embeddings", return_value="fake_emb"):
            svc._rebuild_index()
            mock_mkdir.assert_called_once_with(svc.memory_dir, exist_ok=True)
            mock_chroma_cls.assert_called_once_with(embedding_function="fake_emb", persist_directory=svc.memory_dir)
            assert svc._vectorstore == mock_chroma


class TestMemoryServiceCreateMemoryId:
    def test_creates_hex_id(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        mem_id = svc._create_memory_id("hello world", "session-1")
        assert isinstance(mem_id, str)
        assert len(mem_id) == 16
        all(c in "0123456789abcdef" for c in mem_id)

    def test_creates_different_ids_for_different_content(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        id1 = svc._create_memory_id("content a", "session-1")
        id2 = svc._create_memory_id("content b", "session-1")
        assert id1 != id2

    def test_creates_different_ids_for_different_sessions(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        id1 = svc._create_memory_id("same text", "session-a")
        id2 = svc._create_memory_id("same text", "session-b")
        assert id1 != id2


class TestMemoryServiceAddMemory:
    @pytest.mark.asyncio
    async def test_adds_memory_successfully(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()

        with patch.object(svc, "_create_memory_id", return_value="mem-123"), \
             patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            mem_id = await svc.add_memory("test content", "session-1", user_id="user-1", metadata={"key": "val"})
            assert mem_id == "mem-123"

    @pytest.mark.asyncio
    async def test_initializes_if_not_ready(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = None

        with patch.object(svc, "initialize", new_callable=AsyncMock) as mock_init, \
             patch.object(svc, "_create_memory_id", return_value="mem-456"), \
             patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            svc._vectorstore = MagicMock()

            await svc.add_memory("test", "session-1")
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_memory_creates_document(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()

        with patch.object(svc, "_create_memory_id", return_value="mem-789"), \
             patch("asyncio.get_running_loop") as mock_loop, \
             patch("api.services.memory.Document") as mock_doc_cls:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            mock_doc = MagicMock()
            mock_doc_cls.return_value = mock_doc

            await svc.add_memory("important fact", "session-2", metadata={"source": "call"})
            mock_doc_cls.assert_called_once()
            args, kwargs = mock_doc_cls.call_args
            assert kwargs["page_content"] == "important fact"
            assert kwargs["metadata"]["session_id"] == "session-2"
            assert kwargs["metadata"]["source"] == "call"


class TestMemoryServiceSearchMemories:
    @pytest.mark.asyncio
    async def test_search_without_filter(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "result content"
        mock_doc.metadata = {"memory_id": "mem-1", "session_id": "s1", "user_id": "u1", "timestamp": 100.0}

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[(mock_doc, 0.95)])

            results = await svc.search_memories("test query", k=5)
            assert len(results) == 1
            assert results[0]["content"] == "result content"
            assert results[0]["score"] == 0.95
            assert results[0]["id"] == "mem-1"

    @pytest.mark.asyncio
    async def test_search_with_session_filter(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()
        mock_doc1 = MagicMock()
        mock_doc1.page_content = "from session 1"
        mock_doc1.metadata = {"memory_id": "mem-1", "session_id": "session-1", "user_id": "u1"}
        mock_doc2 = MagicMock()
        mock_doc2.page_content = "from session 2"
        mock_doc2.metadata = {"memory_id": "mem-2", "session_id": "session-2", "user_id": "u1"}

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[(mock_doc1, 0.9), (mock_doc2, 0.8)])

            results = await svc.search_memories("query", session_id="session-1", k=5)
            assert len(results) == 1
            assert results[0]["content"] == "from session 1"

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=[])
            results = await svc.search_memories("nothing", k=5)
            assert results == []

    @pytest.mark.asyncio
    async def test_search_respects_k_limit(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()

        docs = []
        for i in range(10):
            d = MagicMock()
            d.page_content = f"result {i}"
            d.metadata = {"memory_id": f"mem-{i}", "session_id": "s1", "user_id": "u1", "timestamp": float(i)}
            docs.append((d, 1.0 - i * 0.1))

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=docs)
            results = await svc.search_memories("query", k=3)
            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_initializes_if_not_ready(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = None
        svc._embeddings = MagicMock()

        with patch.object(svc, "initialize", new_callable=AsyncMock) as mock_init:
            svc._vectorstore = MagicMock()
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=[])
                await svc.search_memories("query", k=5)
                mock_init.assert_called_once()


class TestMemoryServiceGetSessionMemories:
    @pytest.mark.asyncio
    async def test_returns_session_memories(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        svc._vectorstore = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "session memory"
        mock_doc.metadata = {"memory_id": "mem-1", "session_id": "session-1", "user_id": "u1"}

        with patch("asyncio.get_running_loop") as mock_loop, \
             patch.object(svc, "search_memories") as mock_search:
            mock_search.return_value = [{"id": "mem-1", "content": "session memory", "score": 0.9}]
            results = await svc.get_session_memories("session-1", k=10)
            assert len(results) == 1
            assert results[0]["content"] == "session memory"
            mock_search.assert_called_once_with(query="", session_id="session-1", k=10)


class TestMemoryServiceClearSessionMemories:
    @pytest.mark.asyncio
    async def test_is_noop(self):
        from api.services.memory import MemoryService

        svc = MemoryService()
        result = await svc.clear_session_memories("session-1")
        assert result is None
