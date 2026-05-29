
import pytest

from apps.api.services.mcp_client import MCPClientManager


@pytest.mark.asyncio
async def test_mcp_initialization_and_tool_discovery():
    manager = MCPClientManager()

    # 1. Initialize tenant with mocked MCP servers
    tenant_id = "TENANT-MCP-01"
    mcp_config = '{"internal_wiki": "mcp://wiki.local", "billing_sys": "mcp://billing.local"}'

    await manager.initialize_tenant_servers(tenant_id, mcp_config)
    assert tenant_id in manager.active_connections

    # 2. Verify tool discovery
    tools = manager.get_available_tools(tenant_id)
    assert len(tools) == 2
    tool_names = [t["name"] for t in tools]
    assert "mcp_query_wiki" in tool_names
    assert "mcp_process_refund" in tool_names

@pytest.mark.asyncio
async def test_mcp_tool_execution():
    manager = MCPClientManager()
    tenant_id = "TENANT-MCP-02"
    mcp_config = '{"billing_sys": "mcp://billing.local"}'

    await manager.initialize_tenant_servers(tenant_id, mcp_config)

    # Execute valid tool
    result = await manager.execute_tool(tenant_id, "mcp_process_refund", "INV-12345")
    assert "Refund processed" in result

    # Execute invalid tool
    result2 = await manager.execute_tool(tenant_id, "mcp_unknown", "test")
    assert "failed" in result2.lower()
