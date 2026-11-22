import os
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError

from app.db.session import session_factory
from app.models.application import JobApplication, ResumeVersion
from app.models.interview import InterviewSession
from app.models.operations import PendingFileDeletion, WorkerHeartbeat
from app.models.resume import Resume, ResumeJob
from app.models.user import User
from app.services.account_deletion import clean_file_once
from app.services.resume_storage import storage_path
from app.services.resumes import utc_now
from app.services.worker_health import FULL_WORKER, STRATEGY_WORKER, heartbeat
from conftest import BROWSER_HEADERS, PASSWORD
from resume_fixtures import cases, write_case
from test_applications import seed_resume
from test_product_acceptance import write
from test_resumes import workspace


def test_readiness_distinguishes_worker_and_database(client):
    factory = session_factory()
    with factory.begin() as db:
        row = db.get(WorkerHeartbeat, FULL_WORKER)
        previous_full = row.observed_at if row else None
        row = db.get(WorkerHeartbeat, STRATEGY_WORKER)
        previous_strategy = row.observed_at if row else None
        db.execute(delete(WorkerHeartbeat))
    try:
        heartbeat(factory, STRATEGY_WORKER)
        stale = client.get("/ready")
        assert stale.status_code == 503
        assert stale.json()["checks"] == {"database": "ok", "worker": "stale"}
        heartbeat(factory, FULL_WORKER)
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["checks"] == {"database": "ok", "worker": "ok"}
        assert ready.headers["Cache-Control"] == "no-store"
        UUID(ready.headers["X-Request-ID"])
        assert ready.headers["X-Request-ID"] != stale.headers["X-Request-ID"]
        with factory.begin() as db:
            db.get(WorkerHeartbeat, FULL_WORKER).observed_at = utc_now() - timedelta(minutes=20)
        assert client.get("/ready").status_code == 503
        assert client.get("/health").json() == {"status": "ok"}
    finally:
        with factory.begin() as db:
            db.execute(delete(WorkerHeartbeat))
            db.add_all([WorkerHeartbeat(role=role, observed_at=time) for role, time in (
                (FULL_WORKER, previous_full), (STRATEGY_WORKER, previous_strategy)
            ) if time is not None])


def test_readiness_database_error(client):
    from app.db.session import get_db

    class UnavailableDatabase:
        def scalar(self, _query):
            raise OperationalError("private content", {}, Exception())

    client.app.dependency_overrides[get_db] = UnavailableDatabase
    try:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["checks"] == {"database": "unavailable", "worker": "unknown"}
        assert "private content" not in response.text
    finally:
        client.app.dependency_overrides.pop(get_db)


def test_account_delete_with_derived_data_and_resumable_cleanup(client, register_account, bearer_headers, workspace, monkeypatch):
    email, account = register_account()
    own = bearer_headers(email)
    _, other = register_account()
    other_token = bearer_headers(other["email"])
    uid = account["id"]
    source_id = seed_resume(email)
    pdf = write_case(next(case for case in cases() if case["format"] == "pdf"), workspace)
    uploaded = client.post("/api/v1/resumes/upload", headers=own, files={"file": ("audit.pdf", pdf.read_bytes())})
    assert uploaded.status_code == 201
    resume_id = uploaded.json()["id"]
    job = write(client, "POST", "/jobs", own, {
        "position_name": "Synthetic analyst", "job_description": "Synthetic analyst job for account deletion testing."
    }, 201)
    version = write(client, "POST", "/resume-versions", own, {
        "request_id": str(uuid4()), "content_id": source_id, "version_name": "Audit copy",
        "change_summary": "Copy selected evidence", "block_numbers": [1], "confirmed": True,
    }, 201)
    record = write(client, "POST", "/applications", own, {
        "job_id": job["id"], "resume_version_id": version["id"], "request_id": str(uuid4())
    }, 201)
    interview = write(client, "POST", "/interviews/sessions", own, {
        "mode": "combined", "job_id": job["id"], "request_id": str(uuid4())
    }, 201)
    factory = session_factory()
    with factory.begin() as db:
        file_key = db.get(Resume, resume_id).storage_key
        stored = storage_path(file_key)
        pending = ResumeJob(resume_id=resume_id, kind="parse", dedupe_key="synthetic", state="running", payload={})
        db.add(pending)
        db.flush()
        pending_id = pending.id
    assert stored.is_file()
    request = {"password": PASSWORD, "confirmed": True}
    result = client.request("DELETE", "/api/v1/users/me", headers=own, json=request)
    assert result.status_code == 409 and result.json()["error"]["code"] == "ACCOUNT_TASK_RUNNING"
    with factory.begin() as db:
        db.get(ResumeJob, pending_id).state = "queued"
    assert client.request("DELETE", "/api/v1/users/me", headers=own,
                          json={**request, "password": "Incorrect"}).status_code == 403
    assert client.request("DELETE", "/api/v1/users/me", headers=own, json={**request, "confirmed": False}).status_code == 422
    session = client.post("/api/v1/auth/session", headers=BROWSER_HEADERS,
                          data={"username": email, "password": PASSWORD})
    assert session.status_code == 200
    assert client.request("DELETE", "/api/v1/users/me", json=request).status_code == 403
    result = client.request("DELETE", "/api/v1/users/me", headers=BROWSER_HEADERS, json=request)
    assert result.status_code == 202, result.text
    assert "Max-Age=0" in result.headers["set-cookie"]
    assert client.get("/api/v1/users/me", headers=own).status_code == 401
    assert client.get("/api/v1/users/me", headers=other_token).json()["id"] == other["id"]
    with factory() as db:
        for model, identifier in ((User, uid), (Resume, resume_id), (ResumeJob, pending_id),
                                  (ResumeVersion, version["id"]), (JobApplication, record["id"]),
                                  (InterviewSession, interview["id"])):
            assert db.get(model, identifier) is None
        assert db.get(PendingFileDeletion, file_key) is not None
    assert stored.exists()

    class BlockedFile:
        def unlink(self, *, missing_ok):
            raise PermissionError()
    from app.services import account_deletion
    with monkeypatch.context() as patch:
        patch.setattr(account_deletion, "storage_path", lambda key: BlockedFile() if key == file_key else storage_path(key))
        while clean_file_once(factory):
            with factory() as db:
                issue = db.get(PendingFileDeletion, file_key)
                if issue is not None and issue.attempts:
                    break
    with factory.begin() as db:
        issue = db.get(PendingFileDeletion, file_key)
        assert issue.attempts == 1 and issue.next_attempt_at > utc_now()
        # The MySQL column stores whole seconds, so force the test retry into the past.
        issue.next_attempt_at = utc_now() - timedelta(seconds=2)
    while clean_file_once(factory):
        if not stored.exists():
            break
    assert not stored.exists()
    with factory() as db:
        assert db.get(PendingFileDeletion, file_key) is None


def test_learning_upload_limits_have_request_ids(client, bearer_headers):
    token = bearer_headers()
    file = {"file": ("oversized.docx", b"x" * (1024 * 1024 + 64 * 1024))}
    for route in ("/resources/upload", "/assignments/any-topic/upload"):
        result = client.post("/api/v1/learning" + route, headers=token, files=file)
        assert result.status_code == 413, result.text
        assert result.json()["error"]["code"] == "LEARNING_FILE_LIMIT"
        assert result.headers["Cache-Control"] == "no-store"
        UUID(result.headers["X-Request-ID"])


@pytest.mark.skipif(not os.getenv("CAREER_OPERATIONS_BROWSER"), reason="Requires isolated test servers")
def test_delete_account_browser(register_account):
    email, _ = register_account()
    base = os.environ["CAREER_OPERATIONS_BROWSER"].rstrip("/")
    options = {"channel": os.environ["CAREER_BROWSER_CHANNEL"]} if os.getenv("CAREER_BROWSER_CHANNEL") else {}
    with sync_playwright() as runner:
        browser = runner.chromium.launch(**options)
        page = browser.new_page()
        page.goto(base + "/settings")
        expect(page).to_have_url(base + "/login")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(PASSWORD)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(base + "/settings")
        page.get_by_role("button", name="删除我的账户").click()
        page.get_by_label("当前密码").fill("Incorrect")
        page.get_by_role("checkbox").check()
        page.get_by_role("button", name="确认删除账户").click()
        expect(page.get_by_role("alert")).to_have_text("密码验证失败")
        page.get_by_label("当前密码").fill(PASSWORD)
        page.get_by_role("button", name="确认删除账户").click()
        expect(page.get_by_text("账户已删除。")).to_be_visible()
        page.goto(base + "/settings")
        expect(page).to_have_url(base + "/login")
        browser.close()
