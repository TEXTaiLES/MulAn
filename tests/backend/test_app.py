from __future__ import annotations


def test_health_and_development_root(client):
    health = client.get("/api/health")
    assert health.status_code == 200 and health.get_json() == {"status": "ok"}
    root = client.get("/")
    assert root.status_code == 200
    assert root.get_json()["name"] == "MulAn"


def test_unknown_api_route_is_json_error(client):
    response = client.get("/api/v1/not-a-route")
    assert response.status_code == 404
    assert response.is_json
    assert set(response.get_json()["error"]) == {"code", "message", "details"}


def test_spa_handler_does_not_serve_files_outside_static_root(client):
    response = client.get("/%2e%2e/%2e%2e/%2e%2e/SPEC.md")
    assert response.status_code == 200
    assert b"# MulAn" not in response.data
    assert client.get("/assets/missing.js").status_code == 404
