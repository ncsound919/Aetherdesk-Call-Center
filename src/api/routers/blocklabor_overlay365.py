"""Blocklabor integration for Aetherdesk - hire workers from call center UI."""
import os
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field, Literal

from api.services.auth import verify_access_token, verify_tenant_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/blocklabor", tags=["blocklabor"])

BLOCKLABOR_URL = os.getenv("BLOCKLABOR_URL", "http://localhost:5173")
BLOCKLABOR_API_KEY = os.getenv("BLOCKLABOR_API_KEY", "")


class PostJobRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    skills_required: List[str] = Field(default_factory=list, max_length=20)
    pay_rate: float = Field(..., gt=0, le=10000)
    duration: Literal["temp", "contract", "full-time"] = Field(default="temp")
    tenant_id: str = Field(..., min_length=1, max_length=100)


@router.post("/post-job")
async def post_job_to_blocklabor(
    request: PostJobRequest,
    token: str = Depends(verify_access_token),
):
    """Post a job to Blocklabor when Aetherdesk needs workers."""
    verify_tenant_access(token, request.tenant_id)
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
            raise HTTPException(status_code=503, detail="Blocklabor service unreachable")


@router.get("/workers/match")
async def match_workers(
    skills: str,
    pay_rate: float,
    token: str = Depends(verify_access_token),
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