import yaml
from pathlib import Path


COMPOSE_FILE = Path(__file__).parent.parent.parent / "docker-compose.yml"


def load_compose():
    if not COMPOSE_FILE.exists():
        pytest.skip("docker-compose.yml not found")
    return yaml.safe_load(COMPOSE_FILE.read_text())


def test_ollama_service_exists():
    data = load_compose()
    services = data.get("services", {})
    assert "ollama" in services, "ollama service missing from docker-compose.yml"


def test_open_webui_service_exists():
    data = load_compose()
    services = data.get("services", {})
    assert "open-webui" in services, "open-webui service missing from docker-compose.yml"


def test_open_webui_depends_on_ollama():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    depends_on = open_webui.get("depends_on", [])
    
    assert "ollama" in depends_on, "open-webui must depend on ollama"


def test_open_webui_port_mapping():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    ports = open_webui.get("ports", [])
    
    # Should map host port 3000 to container port 8080
    port_mapping = "3000:8080"
    assert port_mapping in ports, f"open-webui port mapping {port_mapping} not found"


def test_open_webui_ollama_base_url():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    environment = open_webui.get("environment", {})
    
    # Environment may be a list or dict
    if isinstance(environment, list):
        env_text = " ".join(str(e) for e in environment)
    else:
        env_text = str(environment)
    
    assert "ollama:11434" in env_text, "OLLAMA_BASE_URL must point to ollama:11434"


def test_open_webui_redis_url():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    environment = open_webui.get("environment", {})
    
    if isinstance(environment, list):
        env_text = " ".join(str(e) for e in environment)
    else:
        env_text = str(environment)
    
    assert "redis:" in env_text, "REDIS_URL must reference redis service"


def test_open_webui_volumes_exist():
    data = load_compose()
    services = data.get("services", {})
    volumes = data.get("volumes", {})
    
    open_webui = services["open-webui"]
    service_volumes = open_webui.get("volumes", [])
    
    # Check for persistent volume
    assert any("open-webui-data" in str(v) for v in service_volumes), "open-webui must mount open-webui-data volume"
    assert "open-webui-data" in volumes, "open-webui-data volume must be defined"


def test_ollama_volume_exists():
    data = load_compose()
    volumes = data.get("volumes", {})
    
    assert "ollama-data" in volumes, "ollama-data volume must be defined for model persistence"


def test_api_gateway_depends_on_ollama():
    data = load_compose()
    services = data.get("services", {})
    
    api = services.get("api-gateway", {})
    depends_on = api.get("depends_on", [])
    
    assert "ollama" in depends_on, "api-gateway must depend on ollama for LLM access"


def test_api_gateway_ollama_env():
    data = load_compose()
    services = data.get("services", {})
    
    api = services.get("api-gateway", {})
    environment = api.get("environment", {})
    
    if isinstance(environment, list):
        env_text = " ".join(str(e) for e in environment)
    else:
        env_text = str(environment)
    
    assert "OLLAMA_HOST" in env_text, "api-gateway must have OLLAMA_HOST configured"
    assert "ollama:11434" in env_text, "OLLAMA_HOST must point to ollama:11434"


def test_celery_enabled_in_api_gateway():
    data = load_compose()
    services = data.get("services", {})
    
    api = services.get("api-gateway", {})
    environment = api.get("environment", {})
    
    if isinstance(environment, list):
        env_text = " ".join(str(e) for e in environment)
    else:
        env_text = str(environment)
    
    assert "CELERY_ENABLED" in env_text, "api-gateway must have CELERY_ENABLED configured"
    assert "true" in env_text.lower(), "CELERY_ENABLED should be true"


def test_network_exists():
    data = load_compose()
    networks = data.get("networks", {})
    
    assert "aetherdesk-net" in networks, "aetherdesk-net network must exist"
    assert networks["aetherdesk-net"].get("driver") == "bridge"


def test_ollama_resources_configured():
    data = load_compose()
    services = data.get("services", {})
    
    ollama = services["ollama"]
    deploy = ollama.get("deploy", {})
    resources = deploy.get("resources", {})
    limits = resources.get("limits", {})
    
    assert "memory" in limits, "ollama should have memory limits configured"
    assert "cpus" in limits, "ollama should have CPU limits configured"


def test_open_webui_resources_configured():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    deploy = open_webui.get("deploy", {})
    resources = deploy.get("resources", {})
    limits = resources.get("limits", {})
    
    assert "memory" in limits, "open-webui should have memory limits configured"
    assert "cpus" in limits, "open-webui should have CPU limits configured"


def test_open_webui_health_config():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    # Open WebUI typically uses healthcheck via /health endpoint
    # We just verify it's configured properly
    assert "restart" in open_webui, "open-webui should have restart policy"


def test_open_webui_signup_disabled():
    data = load_compose()
    services = data.get("services", {})
    
    open_webui = services["open-webui"]
    environment = open_webui.get("environment", {})
    
    if isinstance(environment, list):
        env_text = " ".join(str(e) for e in environment)
    else:
        env_text = str(environment)
    
    assert "ENABLE_SIGNUP" in env_text and "false" in env_text.lower(), "ENABLE_SIGNUP should be false for production"
