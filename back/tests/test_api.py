from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TOKEN_REFRESH_HEADER, create_access_token, verify_password
from app.db.session import SessionLocal
from app.services.user import get_user_by_username


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_hello(client):
    response = client.get("/api/hello")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["message"] == "Hello from FastAPI backend"


def test_register_and_login(client):
    payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "secret123",
    }

    register_resp = client.post("/api/auth/register", json=payload)
    assert register_resp.status_code == 200
    register_body = register_resp.json()
    assert register_body["code"] == 0
    assert register_body["data"]["token"]["access_token"]
    assert register_body["data"]["user"]["username"] == "testuser"

    login_resp = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "secret123"},
    )
    assert login_resp.status_code == 200
    login_body = login_resp.json()
    token = login_body["data"]["token"]["access_token"]

    me_resp = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "test@example.com"
    assert me_resp.headers.get(TOKEN_REFRESH_HEADER)


def test_password_is_hashed_in_database(client):
    payload = {
        "username": "hashuser",
        "email": "hash@example.com",
        "password": "secret123",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200

    db: Session = SessionLocal()
    try:
        user = get_user_by_username(db, "hashuser")
        assert user is not None
        assert user.hashed_password != payload["password"]
        assert user.hashed_password.startswith("$2b$")
        assert verify_password(payload["password"], user.hashed_password)
    finally:
        db.close()


def test_token_expires_after_idle_period(client):
    expired_token = create_access_token(1, token_version=0, expires_delta=timedelta(seconds=-1))
    response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "未登录或登录已过期"


def test_token_lifetime_is_one_hour(client):
    register_resp = client.post(
        "/api/auth/register",
        json={
            "username": "tokenuser",
            "email": "token@example.com",
            "password": "secret123",
        },
    )
    token = register_resp.json()["data"]["token"]["access_token"]
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    now = datetime.now(UTC)
    remaining = exp - now
    assert timedelta(minutes=59) <= remaining <= timedelta(minutes=61)


def test_token_invalid_after_password_change(client):
    register_resp = client.post(
        "/api/auth/register",
        json={
            "username": "pwduser",
            "email": "pwd@example.com",
            "password": "secret123",
        },
    )
    old_token = register_resp.json()["data"]["token"]["access_token"]

    change_resp = client.post(
        "/api/users/change-password",
        headers={"Authorization": f"Bearer {old_token}"},
        json={"old_password": "secret123", "new_password": "newsecret456"},
    )
    assert change_resp.status_code == 200
    new_token = change_resp.json()["data"]["token"]["access_token"]
    assert new_token != old_token

    stale_resp = client.get("/api/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert stale_resp.status_code == 401
    assert stale_resp.json()["message"] == "密码已修改，请重新登录"

    fresh_resp = client.get("/api/users/me", headers={"Authorization": f"Bearer {new_token}"})
    assert fresh_resp.status_code == 200
