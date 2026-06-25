import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from api.models.dto import (
    KnowledgeSnippetCreate,
    SuggestionRequest,
    ValidateOutputRequest,
)
from api.services.agent_assist import agent_assist_service
from api.services.auth import verify_tenant_access
from api.services.output_validator import validator

router = APIRouter(prefix="/ai-assist", tags=["ai-assist"])
logger = structlog.get_logger()


@router.post("/validate")
async def validate_output(
    data: ValidateOutputRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    schema = validator.get_validation_schema(data.schema_name)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Schema '{data.schema_name}' not found")
    result = validator.validate_json_output(data.output, schema)
    return result


@router.post("/validate/intent")
async def validate_intent(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    allowed = [
        "pharmacy_refill", "pharmacy_refill_doc", "billing_invoice",
        "billing_refund", "order_status", "tech_support_password",
        "generalInquiry", "agent_handoff",
    ]
    result = data.get("result", {})
    allowed_intents = data.get("allowed_intents", allowed)
    return validator.validate_intent_result(result, allowed_intents)


@router.post("/validate/fix")
async def fix_output(
    data: dict,
    tenant_id: str = Depends(verify_tenant_access),
):
    output = data.get("output", "")
    error = data.get("error", "")
    if not output:
        raise HTTPException(status_code=400, detail="'output' field is required")
    fixed = validator.repair_with_llm_fallback(output, error)
    return {"original": output, "fixed": fixed}


@router.get("/schemas")
async def list_schemas(
    tenant_id: str = Depends(verify_tenant_access),
):
    return {"schemas": validator.list_schemas()}


@router.get("/schemas/{name}")
async def get_schema(
    name: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    schema = validator.get_validation_schema(name)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Schema '{name}' not found")
    return {"name": name, "schema": schema}


@router.post("/suggestions")
async def get_suggestions(
    data: SuggestionRequest,
    tenant_id: str = Depends(verify_tenant_access),
):
    context = data.context or {}
    context["tenant_id"] = tenant_id
    results = await agent_assist_service.get_suggestions(
        data.call_id, data.transcript_segment, context,
    )
    return {"suggestions": results}


@router.get("/knowledge")
async def search_knowledge(
    tenant_id: str = Depends(verify_tenant_access),
    query: str = Query("", min_length=1),
    limit: int = Query(5, ge=1, le=50),
):
    results = await agent_assist_service.get_knowledge_snippets(tenant_id, query, limit)
    return {"results": results}


@router.post("/knowledge")
async def create_knowledge(
    data: KnowledgeSnippetCreate,
    tenant_id: str = Depends(verify_tenant_access),
):
    result = await agent_assist_service.create_knowledge_snippet(
        tenant_id, data.title, data.content, data.tags, data.category,
    )
    return result


@router.delete("/knowledge/{snippet_id}")
async def delete_knowledge(
    snippet_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    deleted = await agent_assist_service.delete_knowledge_snippet(tenant_id, snippet_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge snippet not found")
    return {"success": True}


@router.get("/nba")
async def get_next_best_action(
    tenant_id: str = Depends(verify_tenant_access),
    call_id: str = Query(""),
    call_duration_seconds: int = Query(0),
    current_intent: str | None = Query(None),
    sentiment: str = Query("neutral"),
    agent_id: str | None = Query(None),
):
    context = {
        "call_id": call_id,
        "call_duration_seconds": call_duration_seconds,
        "current_intent": current_intent,
        "sentiment": sentiment,
    }
    nba = await agent_assist_service.get_next_best_action(context, None)
    return nba


@router.get("/realtime/{call_id}")
async def get_realtime_stats(
    call_id: str,
    tenant_id: str = Depends(verify_tenant_access),
):
    stats = await agent_assist_service.get_realtime_stats(call_id)
    return stats
