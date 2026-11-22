from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.security import issuer, password_hasher
from app.db.session import session_factory
from app.models.user import User
from conftest import BROWSER_HEADERS, PASSWORD

ROOT = "/api/v1"
PROFILE = f"{ROOT}/profiles/me"
USER = f"{ROOT}/users/me"

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}

def test_production_rejects_a_local_secret():
    local_secret = "local-" + uuid4().hex * 2
    with pytest.raises(ValidationError, match="Production requires a separate JWT secret") as error:
        Settings(_env_file=None, app_env="production", db_password="unused",
                 jwt_secret=local_secret, cors_origins=["https://app.example.com"])
    assert local_secret not in str(error.value)


def test_deployment_settings_accept_unset_optional_values(monkeypatch):
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_THINKING"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LLM_PRICES", "null")
    monkeypatch.setenv("DB_POOL_SIZE", "4")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    monkeypatch.setenv("DB_POOL_RECYCLE_SECONDS", "600")
    settings = Settings(_env_file=None, app_env="production", db_password="fixture",
                        jwt_secret=uuid4().hex * 2, cors_origins=["https://career.example.com"])
    assert settings.llm_base_url == "" and settings.llm_thinking is None
    assert settings.llm_prices == {}
    assert (settings.db_pool_size, settings.db_max_overflow, settings.db_pool_recycle_seconds) == (4, 0, 600)

def test_register_hash_and_duplicate(client, register_account):
    email, account = register_account()
    assert account["email"] == email and "password_hash" not in account
    with session_factory()() as db:
        stored = db.get(User, account["id"]).password_hash
        assert stored.startswith("$argon2id$")
        assert password_hasher.verify(PASSWORD, stored)
    duplicate = client.post(f"{ROOT}/auth/register", json={
        "email": email.upper(), "username": "second", "password": PASSWORD,
    })
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "EMAIL_EXISTS"

@pytest.mark.parametrize("email,password,field", [
    ("invalid-email", PASSWORD, "email"),
    ("someone@example.com", "weak", "password"),
    ("someone@example.com", "alllettersnotstrong", "password"),
])
def test_invalid_registration(client, email, password, field):
    response = client.post(f"{ROOT}/auth/register", json={"email": email, "username": "test", "password": password})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field
    assert password not in response.text

def test_login_and_current_user(client, register_account, bearer_headers):
    email, account = register_account()
    headers = bearer_headers(email)
    assert client.get(USER, headers=headers).json() == account
    invalid = client.post(f"{ROOT}/auth/login", data={"username": email, "password": "wrong password"})
    assert invalid.status_code == 401 and invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
def test_unauthenticated_access(client, headers):
    for url in (USER, PROFILE):
        response = client.get(url, headers=headers)
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
    assert client.put(PROFILE, headers=headers, json={}).status_code == 401

def test_expired_token(client, register_account):
    _, account = register_account()
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(account["id"]), "iss": issuer, "aud": "api", "iat": now - timedelta(minutes=5),
         "exp": now - timedelta(minutes=1)},
        get_settings().jwt_secret.get_secret_value(), algorithm="HS256",
    )
    assert client.get(USER, headers={"Authorization": f"Bearer {token}"}).status_code == 401

def test_profile_lifecycle_and_isolation(client, bearer_headers):
    first = bearer_headers()
    second = bearer_headers()
    missing = client.get(PROFILE, headers=first)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PROFILE_NOT_FOUND"
    body = {
        "real_name": "样例", "undergraduate_school": "示例大学", "undergraduate_major": "国际贸易",
        "undergraduate_degree": "本科", "graduate_school": "示例研究生院", "graduate_major": "低空经济",
        "graduation_year": 2028, "target_position": "AI 产品经理", "interested_industries": ["低空经济"],
        "skills": ["Python", "SQL"], "internship_experience": [{"title": "例行实习", "description": "演示"}],
        "project_experience": [{"title": "项目甲"}],
    }
    created = client.put(PROFILE, headers=first, json=body)
    assert created.status_code == 200, created.text
    assert created.json()["skills"] == ["Python", "SQL"]
    assert created.json()["project_experience"] == [{"title": "项目甲", "description": ""}]
    assert client.get(PROFILE, headers=first).json() == created.json()
    assert client.get(PROFILE, headers=second).status_code == 404
    second_saved = client.put(PROFILE, headers=second, json={"target_position": "数据产品经理"})
    assert second_saved.status_code == 200 and second_saved.json()["id"] != created.json()["id"]
    assert client.put(PROFILE, headers=second, json={"user_id": 1}).status_code == 422
    updated = client.put(PROFILE, headers=first, json={"target_position": "AI Agent 产品经理"})
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["skills"] == []
    assert client.get(PROFILE, headers=second).json() == second_saved.json()

def test_concurrent_first_profile_save(client, bearer_headers):
    headers = bearer_headers()
    def save(target):
        return client.put(PROFILE, headers=headers, json={"target_position": target})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["AI 产品经理", "智能应用产品经理"]))
    assert [result.status_code for result in results] == [200, 200]
    assert len({result.json()["id"] for result in results}) == 1

def test_cookie_session_csrf_cors_and_logout(client, register_account):
    email, user = register_account()
    login = f"{ROOT}/auth/session"
    data = {"username": email, "password": PASSWORD}
    assert client.post(login, data=data).status_code == 403
    result = client.post(login, data=data, headers=BROWSER_HEADERS)
    assert result.status_code == 200 and result.json() == user
    cookies = result.headers["Set-Cookie"]
    assert "HttpOnly" in cookies and "SameSite=lax" in cookies
    assert client.get(USER).json() == user
    assert client.put(PROFILE, json={}).status_code == 403
    untrusted = {**BROWSER_HEADERS, "Origin": "https://untrusted.example"}
    assert client.put(PROFILE, json={}, headers=untrusted).status_code == 403
    allowed = client.options(PROFILE, headers={
        **BROWSER_HEADERS, "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "X-CSRF-Protection, Content-Type",
    })
    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == BROWSER_HEADERS["Origin"]
    assert "Access-Control-Allow-Origin" not in client.get(USER, headers=untrusted).headers
    assert client.put(PROFILE, json={}, headers=BROWSER_HEADERS).status_code == 200
    assert client.delete(login, headers=BROWSER_HEADERS).status_code == 204
    assert client.get(USER).status_code == 401

@pytest.mark.parametrize("endpoint,attempts", [("register", 5), ("login", 15)])
def test_rate_limit(client, endpoint, attempts):
    for _ in range(attempts):
        email = f"test-{uuid4().hex}@example.com"
        if endpoint == "register":
            assert client.post(f"{ROOT}/auth/{endpoint}", json={
                "email": email, "username": "rate-test", "password": PASSWORD,
            }).status_code == 201
        else:
            assert client.post(f"{ROOT}/auth/{endpoint}", data={"username": email, "password": "wrong"}).status_code == 401
    result = client.post(f"{ROOT}/auth/{endpoint}", json={
        "email": email, "username": "rate-test", "password": PASSWORD,
    }) if endpoint == "register" else client.post(f"{ROOT}/auth/{endpoint}", data={"username": email, "password": "wrong"})
    assert result.status_code == 429 and int(result.headers["Retry-After"]) > 0
