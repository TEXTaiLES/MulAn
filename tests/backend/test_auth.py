from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fake_hestia import TOKEN


def test_session_reports_anonymous_user_without_cookie(anonymous_client):
    response = anonymous_client.get("/api/v1/session")
    assert response.status_code == 200
    body = response.get_json()
    assert body["authenticated"] is False and body["user"] is None
    assert not any(body["capabilities"].values())
    assert body["login_url"] == "/auth/login"
    assert response.headers["Cache-Control"] == "no-store"


def test_session_reports_hestia_user_and_capabilities(client, hestia):
    hestia.capabilities[TOKEN]["annotations_update"] = False
    body = client.get("/api/v1/session").get_json()
    assert body["authenticated"] is True
    assert body["user"]["display_name"] == "Ada Lovelace"
    assert body["capabilities"]["images_read"] is True and body["capabilities"]["annotations_update"] is False


def test_session_endpoint_always_asks_hestia(client, hestia):
    client.get("/api/v1/session"); client.get("/api/v1/session")
    assert hestia.calls.count("session") == 2


def test_login_redirects_to_portal_and_back_to_front_page(anonymous_client):
    response = anonymous_client.get("/auth/login", headers={"Host": "mulan.example.org"})
    assert response.status_code == 302
    target = urlsplit(response.headers["Location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == "http://portal.test/archive/user/login"
    assert parse_qs(target.query)["redirect_url"] == ["http://mulan.example.org/"]


def test_login_prefers_configured_public_url(app, anonymous_client):
    app.config["MULAN_PUBLIC_URL"] = "https://mulan.textailes.example/"
    target = urlsplit(anonymous_client.get("/auth/login").headers["Location"])
    assert parse_qs(target.query)["redirect_url"] == ["https://mulan.textailes.example/"]


def test_logout_redirects_to_portal_logout(client):
    response = client.get("/auth/logout")
    assert response.status_code == 302
    target = urlsplit(response.headers["Location"])
    assert target.path == "/archive/user/logout"
    assert parse_qs(target.query)["redirect_url"] == ["http://localhost/"]


def test_every_api_route_requires_a_hestia_login(anonymous_client):
    for method, path in (("post", "/api/v1/convert/bmp-to-tiff"), ("post", "/api/v1/annotations"), ("post", "/api/internal/v1/cleanup")):
        response = getattr(anonymous_client, method)(path)
        assert response.status_code == 401 and response.get_json()["error"]["code"] == "unauthenticated"


def test_expired_hestia_cookie_is_treated_as_signed_out(app):
    stale = app.test_client()
    stale.set_cookie(app.config["HESTIA_COOKIE_NAME"], "expired-token")
    assert stale.get("/api/v1/session").get_json()["authenticated"] is False
    assert stale.post("/api/v1/annotations").status_code == 401


def test_health_stays_public(anonymous_client):
    assert anonymous_client.get("/api/health").status_code == 200
