import os
import time
import threading
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3

app = FastAPI()

MCP_TOKEN = os.getenv("MCP_TOKEN", "").strip()

# In-memory job store (skeleton only; next step we move to Firestore/Redis)
jobs: Dict[str, Dict[str, Any]] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_auth(request: Request) -> None:
    if not MCP_TOKEN:
        raise HTTPException(status_code=500, detail="SERVER_MISCONFIG: MCP_TOKEN is not set")

    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {MCP_TOKEN}":
        raise HTTPException(status_code=401, detail="UNAUTHORIZED: Missing/invalid bearer token")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = "INTERNAL_ERROR"
    msg = str(exc.detail)

    if msg.startswith("UNAUTHORIZED"):
        code = "UNAUTHORIZED"
    elif msg.startswith("SERVER_MISCONFIG"):
        code = "SERVER_MISCONFIG"

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": msg}},
    )


@app.get("/")
async def root():
    return {"ok": True,}

@app.get("/healthz/")
async def healthz():
    return {"ok": True}

@app.post("/v1/jobs")
async def create_job(request: Request):
    require_auth(request)
    body = await request.json()

    template = body.get("template")
    client_job_id = body.get("clientJobId")

    if not template:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_FAILED", "message": "template is required"}},
        )

    # Idempotency by clientJobId (optional but helpful)
    if client_job_id:
        for j in jobs.values():
            if j.get("clientJobId") == client_job_id:
                return JSONResponse(status_code=202, content=j)

    job_id = "job_" + secrets.token_hex(10)
    created_at = utc_now_iso()

    job = {
        "jobId": job_id,
        "clientJobId": client_job_id,
        "status": "queued",
        "createdAt": created_at,
        "links": {"self": f"/v1/jobs/{job_id}"},
    }
    jobs[job_id] = job

    # Skeleton: simulate async work, then mark succeeded
    def worker():
        jobs[job_id]["status"] = "running"
        jobs[job_id]["startedAt"] = utc_now_iso()
        time.sleep(2)
        jobs[job_id]["status"] = "succeeded"
        jobs[job_id]["finishedAt"] = utc_now_iso()
        jobs[job_id]["result"] = {
            "outputUrl": "https://example.com/dummy.mp4",
            "durationSec": (body.get("params") or {}).get("durationSec"),
        }

    threading.Thread(target=worker, daemon=True).start()

    return JSONResponse(status_code=202, content=job)


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    require_auth(request)
    job = jobs.get(job_id)
    if not job:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "JOB_NOT_FOUND", "message": "jobId not found"}},
        )
    return job



class SignRequest(BaseModel):
    videoKey: str | None = None
    audioKey: str | None = None
    outputKey: str | None = None
    expiresSec: int = 3600

class SignResponse(BaseModel):
    videoGetUrl: str | None = None
    audioGetUrl: str | None = None
    outputPutUrl: str | None = None

def r2_client():
    account_id = os.environ["CF_R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
@app.post("/v1/sign", response_model=SignResponse)
def sign(req: SignRequest):
    s3 = r2_client()
    bucket = os.environ["CF_R2_BUCKET"]

    res = {}

    if req.videoKey:
        res["videoGetUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": req.videoKey},
            ExpiresIn=req.expiresSec,
        )

    if req.audioKey:
        res["audioGetUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": req.audioKey},
            ExpiresIn=req.expiresSec,
        )

    if req.outputKey:
        res["outputPutUrl"] = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": req.outputKey},
            ExpiresIn=req.expiresSec,
        )

    return res