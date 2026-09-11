"""Exercise startup CORS configuration without reloading the shared API module."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


ALLOWED = "https://fairies-test.pages.dev"
SECOND = "http://localhost:8080"


@pytest.fixture
def make_client(monkeypatch):
    def create(origins=f" {ALLOWED}, , {SECOND} "):
        if origins is None:
            monkeypatch.delenv("FAIRIES_CORS_ORIGINS", raising=False)
        else:
            monkeypatch.setenv("FAIRIES_CORS_ORIGINS", origins)
        spec = importlib.util.spec_from_file_location(
            "cors_test_api", Path(__file__).resolve().parents[1] / "api" / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "start_session", lambda user_id, consent: SimpleNamespace(
            user_id="user_cors", session_id="session_20260911_120000_abcdef",
            greeting="Hello",
        ))
        return TestClient(module.app)
    return create


def preflight(client, origin, method="POST", headers="content-type", path="/sessions"):
    return client.options(path, headers={
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": headers,
    })


@pytest.mark.parametrize("origin", [ALLOWED, SECOND])
@pytest.mark.parametrize("path", ["/sessions", "/chat", "/match", "/match/stream", "/sessions/test/end"])
def test_allowed_preflight(make_client, origin, path):
    response = preflight(make_client(), origin, path=path)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("method", ["GET", "OPTIONS"])
def test_other_allowed_methods(make_client, method):
    assert preflight(make_client(), ALLOWED, method=method).status_code == 200


@pytest.mark.parametrize("origin", [ALLOWED, SECOND])
def test_post_preserves_response_and_adds_cors(make_client, origin):
    response = make_client().post("/sessions", headers={"Origin": origin},
                                  json={"user_id": None, "log_consent": True})
    assert response.status_code == 201
    assert response.json()["user_id"] == "user_cors"
    assert response.headers["access-control-allow-origin"] == origin
    assert "origin" in response.headers["vary"].lower()
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize("origin", ["https://untrusted.example", ALLOWED + ".evil.example", "null"])
def test_unallowed_origin_has_no_allow_origin(make_client, origin):
    client = make_client()
    response = preflight(client, origin)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    response = client.post("/sessions", headers={"Origin": origin},
                           json={"user_id": None, "log_consent": True})
    assert response.status_code == 201  # CORS controls browser access, not authorization.
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origins", [None, "", " , "])
def test_empty_configuration_denies_cross_origin(make_client, origins):
    response = preflight(make_client(origins), ALLOWED)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origins", ["*", ALLOWED + ", *", "https://*.pages.dev"])
def test_wildcards_fail_at_startup(make_client, origins):
    with pytest.raises(ValueError, match="FAIRIES_CORS_ORIGINS"):
        make_client(origins)


@pytest.mark.parametrize("method,headers", [("DELETE", "content-type"), ("POST", "x-unapproved")])
def test_unneeded_methods_and_headers_are_rejected(make_client, method, headers):
    assert preflight(make_client(), ALLOWED, method, headers).status_code == 400


def test_get_and_validation_error_keep_existing_contract(make_client):
    client = make_client()
    response = client.get("/", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["access-control-allow-origin"] == ALLOWED
    response = client.post("/sessions", headers={"Origin": ALLOWED}, json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_non_browser_request_is_unchanged(make_client):
    response = make_client().post("/sessions", json={"user_id": None, "log_consent": True})
    assert response.status_code == 201
    assert "access-control-allow-origin" not in response.headers
