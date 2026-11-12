"""不需真實資料庫即可驗證 Liveness（存活檢查）。"""
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from unittest.mock import patch
from src.main import app

def test_liveness():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_when_database_is_available():
    with patch("src.main.engine") as engine:
        response = TestClient(app).get("/health/ready")
        engine.connect.return_value.__enter__.return_value.execute.assert_called_once()

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_when_database_is_unavailable():
    with patch("src.main.engine") as engine:
        engine.connect.side_effect = SQLAlchemyError("offline")
        response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "資料庫尚未就緒"
