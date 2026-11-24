from fastapi.testclient import TestClient

from logtracer.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "version", "log_root_found", "db_found"}


def test_openapi_available():
    assert client.get("/openapi.json").status_code == 200
