"""M1 API 骨架：僅提供健康檢查，未開放受保護的業務端點。"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID, uuid4

from .db import engine
from .auth import AuthError, router as auth_router
from .tenants import router as tenant_router

app = FastAPI(title="Enterprise AI Operations Agent API", version="0.1.0")
app.include_router(auth_router)
app.include_router(tenant_router)


@app.exception_handler(AuthError)
def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", "")
    try:
        trace_id = str(UUID(request_id))
    except ValueError:
        trace_id = str(uuid4())
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message,
                           "details": {}, "trace_id": trace_id}},
    )

@app.get("/health/live", tags=["健康檢查"])
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "agent-api"}

@app.get("/health/ready", tags=["健康檢查"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="資料庫尚未就緒") from exc
    return {"status": "ready", "service": "agent-api"}
