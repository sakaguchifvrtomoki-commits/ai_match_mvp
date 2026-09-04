from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_root_returns_app_metadata():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "app": "Fairies",
        "version": "0.2.2",
        "status": "ok",
    }
