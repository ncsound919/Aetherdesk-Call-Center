import sys
import importlib
import os
import pytest
from unittest.mock import patch


class TestDbConfig:
    def test_raises_when_postgres_required_and_no_url(self):
        for key in list(sys.modules.keys()):
            if "db_config" in key:
                del sys.modules[key]

        with patch.dict(os.environ, {"USE_POSTGRES": "true"}, clear=True):
            with pytest.raises(RuntimeError, match="DATABASE_URL"):
                importlib.import_module("api.services.db_config")

