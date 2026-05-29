import os
from dataclasses import dataclass


@dataclass
class Config:
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

    kb_dir: str = os.getenv("KB_DIR", "data/kb")
    chroma_dir: str = os.getenv("CHROMA_DIR", "chroma_db")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    use_llm_routing: bool = os.getenv("USE_LLM_ROUTING", "false").lower() == "true"

    asr_model_size: str = os.getenv("ASR_MODEL_SIZE", "base")
    asr_device: str = os.getenv("ASR_DEVICE", "auto")

    tts_engine: str = os.getenv("TTS_ENGINE", "edge")
    tts_voice: str = os.getenv("TTS_VOICE", "en-US-AriaNeural")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    max_voice_connections: int = int(os.getenv("MAX_VOICE_CONNECTIONS", "100"))
    rate_limit_window: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    protocol_base_path: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "config", "protocols")
    routes_path: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "config", "routes.json")


config = Config()

config.protocol_base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "protocols")
config.routes_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "routes.json")
