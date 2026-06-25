import os
import pytest
from api.services.config import Config


class TestConfig:
    def test_default_values(self):
        cfg = Config()
        assert cfg.redis_host == "localhost"
        assert cfg.redis_port == 6379
        assert cfg.ollama_host == "http://localhost:11434"
        assert cfg.ollama_model == "llama3.2:1b"

    def test_uses_env_vars(self):
        os.environ["TEST_REDIS_HOST"] = "myredis"
        os.environ["TEST_REDIS_PORT"] = "9999"
        cfg = Config(
            redis_host=os.getenv("TEST_REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("TEST_REDIS_PORT", "6379")),
        )
        assert cfg.redis_host == "myredis"
        assert cfg.redis_port == 9999
        del os.environ["TEST_REDIS_HOST"]
        del os.environ["TEST_REDIS_PORT"]

    def test_log_level_default(self):
        cfg = Config()
        assert cfg.log_level == "INFO"

    def test_tts_defaults(self):
        cfg = Config()
        assert cfg.tts_engine == "edge"
        assert cfg.tts_voice == "en-US-AriaNeural"

    def test_rate_limit_window_default(self):
        cfg = Config()
        assert cfg.rate_limit_window == 60
