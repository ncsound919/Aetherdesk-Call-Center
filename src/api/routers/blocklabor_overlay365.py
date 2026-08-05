"""Blocklabor integration for Aetherdesk - hire workers from call center UI."""

import logging
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from api.services.auth import verify_access_token, verify_tenant_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/blocklabor", tags=["blocklabor"])

bearer_scheme = HTTPBearer(auto_error=False)

BLOCKLABOR_URL = os.getenv("BLOCKLABOR_URL", "http://localhost:5173")
BLOCKLABOR_API_KEY = os.getenv("BLOCKLABOR_API_KEY", "")


async def get_verified_tenant(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    x_api_key: str = Header(default=""),
) -> str:
    """Verify the Bearer token, extract tenant_id, and confirm the API key
    belongs to that tenant (IDOR protection)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = await verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Token missing tenant_id")
    return await verify_tenant_access(tenant_id, x_api_key)


class PostJobRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    skills_required: list[str] = Field(default_factory=list, max_length=20)
    pay_rate: float = Field(..., gt=0, le=10000)
    duration: Literal["temp", "contract", "full-time"] = Field(default="temp")
    tenant_id: str = Field(..., min_length=1, max_length=100)


@router.post("/post-job")
async def post_job_to_blocklabor(
    request: PostJobRequest,
    tenant_id: str = Depends(get_verified_tenant),
):
    """Post a job to Blocklabor when Aetherdesk needs workers."""
    headers = {"Content-Type": "application/json"}
    if BLOCKLABOR_API_KEY:
        headers["Authorization"] = f"Bearer {BLOCKLABOR_API_KEY}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{BLOCKLABOR_URL}/api/jobs",
                json={
                    "title": request.title,
                    "description": request.description,
                    "skills": request.skills_required,
                    "pay_rate": request.pay_rate,
                    "duration": request.duration,
                    "source": "aetherdesk",
                    "tenant_id": request.tenant_id,
                },
                headers=headers,
            )
            if response.status_code == 200:
                logger.info(f"Job posted to Blocklabor: tenant={request.tenant_id}")
                return {"status": "posted", "job": response.json()}
            return {"status": "error", "detail": response.text}
        except httpx.RequestError as e:
            logger.warning(f"Blocklabor unreachable: {e}")
            raise HTTPException(
                status_code=503, detail="Blocklabor service unreachable"
            ) from e


@router.get("/workers/match")
async def match_workers(
    skills: str,
    pay_rate: float,
    tenant_id: str = Depends(get_verified_tenant),
):
    """Find matching workers in Blocklabor for Aetherdesk needs."""
    headers = {"Content-Type": "application/json"}
    if BLOCKLABOR_API_KEY:
        headers["Authorization"] = f"Bearer {BLOCKLABOR_API_KEY}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BLOCKLABOR_URL}/api/workers/match",
                params={"skills": skills, "min_pay": pay_rate},
                headers=headers,
            )
            if response.status_code == 200:
                return response.json()
            return {"workers": []}
        except httpx.RequestError:
            return {"workers": []}


@router.get("/health")
async def blocklabor_health():
    """Check if Blocklabor is reachable."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{BLOCKLABOR_URL}/health")
            return {"reachable": response.status_code == 200}
        except httpx.RequestError:
            return {"reachable": False}
