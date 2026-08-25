"""HTTP Basic Auth-middleware. Los van de app-fixture in test_app_smoke.py
omdat we hier bewust met en zonder auth-env-vars willen testen."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import configure_auth


def _make_app(username: str | None, password: str | None) -> FastAPI:
    app = FastAPI()
    configure_auth(app, username=username, password=password)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def _basic_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_credentials_configured_leaves_app_open():
    app = _make_app(None, None)
    client = TestClient(app)

    resp = client.get("/ping")
    assert resp.status_code == 200


def test_missing_header_is_rejected_when_configured():
    app = _make_app("admin", "geheim")
    client = TestClient(app)

    resp = client.get("/ping")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Basic")


def test_correct_credentials_are_accepted():
    app = _make_app("admin", "geheim")
    client = TestClient(app)

    resp = client.get("/ping", headers=_basic_header("admin", "geheim"))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_wrong_password_is_rejected():
    app = _make_app("admin", "geheim")
    client = TestClient(app)

    resp = client.get("/ping", headers=_basic_header("admin", "fout-wachtwoord"))
    assert resp.status_code == 401


def test_wrong_username_is_rejected():
    app = _make_app("admin", "geheim")
    client = TestClient(app)

    resp = client.get("/ping", headers=_basic_header("iemand-anders", "geheim"))
    assert resp.status_code == 401


def test_malformed_header_is_rejected():
    app = _make_app("admin", "geheim")
    client = TestClient(app)

    resp = client.get("/ping", headers={"Authorization": "Basic niet-base64!!"})
    assert resp.status_code == 401


def test_non_basic_scheme_is_rejected():
    app = _make_app("admin", "geheim")
    client = TestClient(app)

    resp = client.get("/ping", headers={"Authorization": "Bearer sometoken"})
    assert resp.status_code == 401


def test_only_username_set_leaves_app_open():
    # Beide moeten gezet zijn; anders bewust open (met waarschuwing bij het
    # opstarten) i.p.v. een half-geconfigureerde, verwarrende auth-eis.
    app = _make_app("admin", None)
    client = TestClient(app)

    resp = client.get("/ping")
    assert resp.status_code == 200


@pytest.mark.parametrize("username,password", [("admin", "geheim")])
def test_configure_auth_returns_true_when_enabled(username, password):
    app = FastAPI()
    assert configure_auth(app, username, password) is True


def test_configure_auth_returns_false_when_disabled():
    app = FastAPI()
    assert configure_auth(app, None, None) is False
