from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import os
from threading import Event
from time import monotonic
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import delete, select
from starlette.requests import Request

from app.ai.provider import Provider
from app.core.config import ModelPrice, get_settings
from app.core.errors import ApiError
from app.core.rate_limit import SharedAuthRateLimiter, clear_expired_windows
from app.db.session import session_factory
from app.evaluations.cases import STRATEGY_INPUT
from app.ai.job_strategy_prompts import STRATEGY_PROMPT
from app.models.operations import AuthRateWindow, LlmCallMetric
from app.models.application import JobApplication
from app.models.user import User
from app.schemas.application import StrategyResult
from app.services.llm_monitoring_service import TaskContext, summary, task_provider
from app.services.resumes import utc_now
from app.services.worker_scheduler import run_queues
from conftest import PASSWORD
from test_product_acceptance import read
from test_resumes import workspace
from tools.sprint5_benchmark import seed


def cleanup_application_account(account_id):
    with session_factory().begin() as db:
        db.execute(delete(JobApplication).where(JobApplication.user_id == account_id))
        db.execute(delete(User).where(User.id == account_id))


def test_board_pagination_keeps_analytics_and_other_users_isolated(client, register_account, bearer_headers):
    email, account = register_account()
    owner, outsider = bearer_headers(email), bearer_headers()
    try:
        seed(account["id"], 140)
        full = read(client, "/job-pipeline", owner)
        limited = read(client, "/job-pipeline?limit_per_status=30", owner)
        first = limited["columns"]["offer"]
        assert len(full["columns"]["offer"]) == 35 and len(first) == 30
        assert limited["counts"]["offer"] == 35 and limited["has_more"]["offer"]
        cursor = {"recent": True, "status": "offer", "limit": 30, "before_time": first[-1]["updated_at"], "before_id": first[-1]["id"]}
        remaining = read(client, "/applications", owner, cursor)
        assert [row["id"] for row in first + remaining] == [row["id"] for row in full["columns"]["offer"]]
        assert read(client, "/applications", outsider, cursor) == []
        assert client.get("/api/v1/applications?recent=true&before_id=1", headers=owner).status_code == 422
        assert len(limited["next_actions"]) == 5
        assert all(row["next_action"] for row in limited["next_actions"])
        analytics = read(client, "/job-analytics", owner)
        assert analytics["summary"]["submitted"] == 140
        assert sum(row["count"] for row in analytics["trend"]) == 140
        assert read(client, "/job-analytics", outsider)["summary"]["submitted"] == 0
    finally:
        cleanup_application_account(account["id"])


@pytest.mark.skipif(not os.getenv("CAREER_SPRINT5_BROWSER"), reason="Requires isolated browser servers")
def test_board_loads_more_without_loading_analytics(register_account):
    email, account = register_account()
    base = os.environ["CAREER_SPRINT5_BROWSER"].rstrip("/")
    channel = os.getenv("CAREER_BROWSER_CHANNEL")
    try:
        seed(account["id"], 140)
        with sync_playwright() as runner:
            browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
            page = browser.new_page()
            seen = []
            page.on("request", lambda request: seen.append(request.url))
            page.goto(base + "/application-workspace?tab=board")
            page.get_by_label("邮箱").fill(email)
            page.get_by_label("密码").fill(PASSWORD)
            page.get_by_role("button", name="登录", exact=True).click()
            board = page.get_by_label("投递看板", exact=True)
            column = board.locator("section").filter(has=page.get_by_role("heading", name="Offer 35", exact=True))
            expect(column.get_by_role("article")).to_have_count(30)
            column.get_by_role("button", name="查看更多Offer").click()
            expect(column.get_by_role("article")).to_have_count(35)
            assert not any("/api/v1/job-analytics" in url for url in seen)
            assert any("/api/v1/job-pipeline?limit_per_status=30" in url for url in seen)
            browser.close()
    finally:
        cleanup_application_account(account["id"])


def test_two_worker_lanes_start_short_task_before_slow_finishes():
    slow_started, slow_finished, short_done = Event(), Event(), Event()
    limit = monotonic() + 3

    class EndTest(Exception):
        pass

    def slow(_):
        slow_started.set()
        try:
            return short_done.wait(1)
        finally:
            slow_finished.set()

    def fast(_):
        assert slow_started.wait(1) and not slow_finished.is_set()
        short_done.set()
        return False

    def heartbeat():
        if short_done.is_set():
            raise EndTest()
        assert monotonic() < limit

    with pytest.raises(EndTest):
        run_queues(None, (slow, fast), heartbeat, 2)


def test_shared_auth_limiter_is_atomic_across_instances(client):
    factory = session_factory()
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 123)})
    limits = [SharedAuthRateLimiter(factory, "synthetic-auth-throttle", 3600) for _ in range(2)]
    action = "test_" + uuid4().hex

    def check(index):
        try:
            limits[index % 2].check(request, action, 5)
        except ApiError as exc:
            assert exc.status_code == 429 and int(exc.headers["Retry-After"]) > 0
            return False
        return True

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(check, range(12))) == 5
    with factory.begin() as db:
        row = AuthRateWindow(fingerprint=uuid4().hex * 2, window_start=1, expires_at=2, hits=1)
        db.add(row)
    assert clear_expired_windows(factory) >= 1


def test_monitor_persists_only_metadata_and_estimated_usage(client, register_account, workspace, monkeypatch):
    _, account = register_account()
    factory = session_factory()
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_prices", {settings.llm_model: ModelPrice(
        input_per_million="2", output_per_million="4", currency="CNY"
    )})
    payload = {"summary": "synthetic marker never persisted"}
    now = utc_now()
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
    good = '{"current_state":"样本较少","observations":[],"inferences":[],"hypotheses":[],"priority_actions":["收集记录"],"next_goal":"补齐样本"}'
    for attempt, content in ((1, good), (2, "{not json")):
        provider = task_provider(Provider, settings, factory,
                                 TaskContext("job_strategy", account["id"], 7, attempt, now - timedelta(seconds=2), now))
        monkeypatch.setattr(provider.client.chat.completions, "create", lambda **_: SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))], usage=usage
        ))
        try:
            if attempt == 1:
                assert provider.generate(STRATEGY_PROMPT, payload, StrategyResult).current_state
            else:
                with pytest.raises(ApiError):
                    provider.generate(STRATEGY_PROMPT, payload, StrategyResult)
        finally:
            provider.close()
    with factory() as db:
        rows = db.scalars(select(LlmCallMetric).where(LlmCallMetric.user_id == account["id"])
                          .order_by(LlmCallMetric.id)).all()
        assert [row.status for row in rows] == ["ok", "MODEL_OUTPUT_INVALID"]
        assert [row.queue_wait_ms for row in rows] == [2000, None]
        assert {row.estimated_cost for row in rows} == {Decimal("0.00400000")}
        assert set(LlmCallMetric.__table__.columns.keys()).isdisjoint({"content", "payload", "response", "secret"})
        results = summary(db, now.date(), now.date(), "task", account["id"])
        assert len(results) == 1 and results[0]["calls"] == 2
        assert results[0]["currency"] == "CNY" and results[0]["estimated_cost"] == "0.00800000"
        assert results[0]["retry_calls"] == 1 and results[0]["failure_rate"] == .5
        assert results[0]["input_tokens"] == 2000 and results[0]["output_tokens"] == 1000
    with factory.begin() as db:
        db.execute(delete(User).where(User.id == account["id"]))
    with factory() as db:
        assert not summary(db, now.date(), now.date(), "task", account["id"])


def test_pdf_decoder_limits_are_applied_before_reading(monkeypatch):
    from pypdf import get_configuration
    from pypdf.errors import LimitReachedError
    from app.services import resume_parser

    original = get_configuration()

    def fake_reader(_stream):
        active = get_configuration()
        assert active.zlib_maximum_output_length == resume_parser.MAX_PDF_STREAM_BYTES
        assert active.array_based_stream_maximum_output_length == resume_parser.MAX_PDF_STREAM_BYTES
        assert active.jbig2dec_binary is None
        raise LimitReachedError("synthetic limit")

    monkeypatch.setattr(resume_parser, "PdfReader", fake_reader)
    with pytest.raises(ApiError) as failure:
        list(resume_parser.pdf_sections(None))
    assert failure.value.status_code == 413 and failure.value.code == "PDF_TOO_COMPLEX"
    assert get_configuration() == original


@pytest.mark.skipif(os.getenv("CAREER_SPRINT5_LIVE") != "1", reason="Requires a single approved synthetic provider call")
def test_live_synthetic_usage(client, register_account):
    settings = get_settings()
    assert settings.app_env == "test" and settings.db_name == "career_copilot_test"
    assert urlsplit(settings.llm_base_url).hostname == os.environ["CAREER_EVAL_APPROVED_HOST"]
    _, account = register_account()
    factory = session_factory()
    now = utc_now()
    provider = task_provider(Provider, settings, factory, TaskContext("synthetic_benchmark", account["id"], 1, 1, now, now))
    try:
        provider.generate(STRATEGY_PROMPT, STRATEGY_INPUT, StrategyResult)
        with factory() as db:
            rows = db.scalars(select(LlmCallMetric).where(LlmCallMetric.user_id == account["id"])).all()
            assert len(rows) == 1
            row = rows[0]
            assert row.status == "ok" and row.input_tokens and row.output_tokens
            print(f"model={row.model} duration_ms={row.duration_ms} input={row.input_tokens} output={row.output_tokens} "
                  f"estimated_cost_configured={row.estimated_cost is not None}")
    finally:
        provider.close()
        with factory.begin() as db:
            db.execute(delete(User).where(User.id == account["id"]))
