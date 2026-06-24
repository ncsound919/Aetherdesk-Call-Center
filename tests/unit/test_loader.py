import json
import os
import tempfile
import pytest


class TestFileLoader:
    def test_load_existing_file(self):
        from apps.api.services.loader import FileLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            data = {"nodes": {"start": {"prompt": "Hello"}}}
            proto_path = os.path.join(tmpdir, "test_proto.json")
            with open(proto_path, "w") as f:
                json.dump(data, f)

            loader = FileLoader(base_path=tmpdir)
            result = loader.load("test_proto")
            assert result == data

    def test_load_nonexistent_file_returns_none(self):
        from apps.api.services.loader import FileLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            loader = FileLoader(base_path=tmpdir)
            result = loader.load("nonexistent")
            assert result is None

    def test_default_base_path(self):
        from apps.api.services.loader import FileLoader
        loader = FileLoader()
        assert loader.base_path is not None
        assert "config" in loader.base_path
        assert "protocols" in loader.base_path

