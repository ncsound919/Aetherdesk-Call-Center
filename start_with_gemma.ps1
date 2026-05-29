$env:OLLAMA_MODEL = "gemma3:4b"
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
