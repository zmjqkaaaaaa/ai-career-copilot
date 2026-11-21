import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

PASSWORD = "CareerTestPassword-42"
ORIGIN = "http://127.0.0.1:5173"
BROWSER_HEADERS = {"Origin": ORIGIN, "X-CSRF-Protection": "1"}

@pytest.fixture
def client():
    db_name = os.environ.get("DB_NAME", "")
    if not db_name.endswith("_test") or get_settings().app_env != "test":
        pytest.fail("Run API tests with APP_ENV=test and a migrated DB_NAME ending in _test")
    with TestClient(create_app()) as test_client:
        yield test_client

@pytest.fixture
def register_account(client):
    def register(username="测试用户"):
        email = f"test-{uuid4().hex}@example.com"
        response = client.post("/api/v1/auth/register", json={
            "email": email, "username": username, "password": PASSWORD,
        })
        assert response.status_code == 201, response.text
        return email, response.json()
    return register

@pytest.fixture
def bearer_headers(client, register_account):
    def login(email=None):
        if email is None:
            email, _ = register_account()
        response = client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        assert response.json()["token_type"] == "bearer"
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return login
