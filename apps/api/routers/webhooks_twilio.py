
from fastapi import APIRouter

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])

@router.get("/ping")
def ping():
    return {"ok": True}
