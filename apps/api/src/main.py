"""M1 API 骨架：僅提供健康檢查，未開放受保護的業務端點。"""
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from .settings import settings

app = FastAPI(title="Enterprise AI Operations Agent API", version="0.1.0")
engine = create_engine(settings.database_url, pool_pre_ping=True)

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
