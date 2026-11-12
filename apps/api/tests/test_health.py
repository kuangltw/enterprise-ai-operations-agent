"""不需真實資料庫即可驗證 Liveness（存活檢查）。"""
from fastapi.testclient import TestClient
from src.main import app

def test_liveness():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
