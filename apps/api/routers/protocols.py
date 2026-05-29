
import csv
import json
import os
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from apps.api.services.auth import verify_api_key

router = APIRouter(prefix="/protocols", tags=["protocols"])

UPLOAD_DIR = "config/uploads"
PROTO_DIR = "config/protocols"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROTO_DIR, exist_ok=True)

# Allowlist for secure filenames
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

@router.post("/upload_csv", dependencies=[Depends(verify_api_key)])
async def upload_csv(file: UploadFile = File(...), tenant_id: str = Depends(verify_api_key)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")

    # Sanitize filename to prevent path traversal
    base_name = os.path.splitext(file.filename)[0]
    if not SAFE_FILENAME_RE.match(base_name):
        raise HTTPException(400, "Invalid filename. Use only letters, numbers, hyphens, and underscores.")
    pid = f"{tenant_id}_{base_name}"  # Prefix with tenant_id to isolate tenants

    # Ensure paths stay within allowed directories
    upload_path = os.path.join(UPLOAD_DIR, file.filename)
    proto_path = os.path.join(PROTO_DIR, f"{pid}.json")

    if not os.path.abspath(upload_path).startswith(os.path.abspath(UPLOAD_DIR)) or \
       not os.path.abspath(proto_path).startswith(os.path.abspath(PROTO_DIR)):
        raise HTTPException(400, "Invalid file path")

    with open(upload_path, "wb") as out:
        out.write(await file.read())

    nodes = {}
    with open(upload_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            node = row.get("node") or "start"
            entry = {}
            for k in ["prompt","field","validate","next","action","on_ok","on_fail"]:
                if row.get(k):
                    entry[k] = row[k]
            if row.get("options"):
                entry["options"] = [s.strip() for s in row["options"].split(",")]
            nodes[node] = entry
    proto = {"nodes": nodes}
    with open(proto_path, "w") as f:
        json.dump(proto, f, indent=2)

    return {"ok": True, "protocol_id": pid, "path": proto_path, "nodes": len(nodes)}
