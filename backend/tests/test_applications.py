from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import os

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import session_factory
from app.models.application import ApplicationStatusHistory, InterviewSchedule, JobApplication
from app.models.resume import ResumeContent
from app.services.job_strategy_service import run_strategy_once
from app.services.job_workflow import run_job_once
from test_jobs import FakeProvider, JD, seed_candidate
from test_product_acceptance import read, write


def key():
    return str(uuid4())


def seed_resume(email):
    identifier = seed_candidate(email)
    with session_factory().begin() as db:
        source = db.get(ResumeContent, identifier)
        source.blocks = [
            {"number": 1, "text": "用 SQL 整理合成数据。"},
            {"number": 2, "text": "整理两份合成访谈记录。"},
        ]
    return identifier


class StrategyFixture:
    def __init__(self, _settings):
        pass

    def generate(self, prompt, payload, output):
        assert prompt.name == "job_strategy"
        assert "星河科技" not in str(payload) and "合成数据" not in str(payload)
        assert "label" not in str(payload) and "contact" not in str(payload)
        assert payload["summary"]["submitted"] > 0
        return output.model_validate({
            "current_state": "开始记录求职进展",
            "observations": ["已有投递记录"],
            "inferences": ["待核对的情况"],
            "hypotheses": ["跟进结果还未补齐"],
            "priority_actions": ["补记笔试和面试结果"],
            "next_goal": "增加可核对样本",
        })

    def close(self):
        pass


class StrategyFailure(StrategyFixture):
    def generate(self, *args):
        raise ApiError(504, "MODEL_TIMEOUT", "模型响应超时")


@pytest.fixture
def model_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:9909")
    monkeypatch.setattr(settings, "llm_model", "test")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test"))
    return settings


@pytest.mark.parametrize("index", range(5))
def test_five_accounts_end_to_end(index, client, register_account, bearer_headers, model_settings):
    email, user = register_account()
    headers = bearer_headers(email)
    second = bearer_headers()
    source = seed_resume(email)
    year = datetime.now(UTC).year
    title = f"合成产品岗 {index}"
    data = {"position_name": title, "company_name": "星河科技", "location": "武汉", "job_type": "internship",
            "source_url": f"https://example.invalid/{index}",
            "job_description": JD, "metadata": {"industry": "软件", "education": "本科",
            "skills": ["SQL"], "source": "测试输入", "published_at": f"{year}-01-01", "source_status": "open"}}
    job = write(client, "POST", "/jobs/import-jd", headers, data, 201)
    jid = job["id"]
    url = f"/jobs/{jid}"
    write(client, "POST", "/jobs/import-jd", headers, data, 409)
    write(client, "PATCH", url, headers, {"favorite": True})
    assert [row["id"] for row in read(client, "/jobs", headers, {"company": "星河", "title": title, "city": "武",
            "industry": "软", "education": "本科", "skill": "SQL", "favorite": True,
            "published_from": f"{year}-01-01", "published_to": f"{year}-01-01"})] == [jid]
    assert read(client, "/jobs", second) == []
    write(client, "PATCH", url, second, {"favorite": False}, 404)
    if index == 0:
        write(client, "POST", "/jobs/import-jd", headers, {"position_name": "无效链接", "source_url": "ftp://x"}, 422)
        link_only = write(client, "POST", "/jobs/import-jd", headers,
                          {"position_name": "待补 JD", "source_url": "https://example.invalid/link"}, 201)
        assert link_only["job_description"] == ""
        assert client.get(f"/api/v1/jobs/{link_only['id']}/parse-preview", headers=headers).status_code == 422
        write(client, "POST", "/jobs", headers, {"position_name": "手动录入", "job_description": JD}, 201)
    write(client, "POST", url + "/parse", headers,
          {"accept_external_processing": True, "provider_host": "127.0.0.1"}, 202)
    assert run_job_once(session_factory(), FakeProvider)
    parsed = read(client, url, headers)
    confirmed = write(client, "PUT", url + "/requirements", headers,
                      {"revision": parsed["revision"], "requirements": parsed["requirements"]})
    match = write(client, "POST", url + "/match", headers, {"content_id": source, "revision": confirmed["revision"]})
    assert any(item["name"] == "SQL" for item in match["score_details"]["requirements"])
    proposal = write(client, "POST", "/resume-versions/preview", headers, {"content_id": source, "target_job_id": jid})
    assert len(proposal["blocks"]) == 2
    base = {"version_name": "岗位定向版", "change_summary": "先呈现 SQL", "block_numbers": [1, 2],
            "confirmed": True, "request_id": key()}
    new_version = {**base, "content_id": source, "target_job_id": jid}
    write(client, "POST", "/resume-versions", headers, {**new_version, "block_numbers": [42]}, 422)
    write(client, "POST", "/resume-versions", headers, {**new_version, "content": "编造经历"}, 422)
    write(client, "POST", "/resume-versions", second, new_version, 404)
    v1 = write(client, "POST", "/resume-versions", headers, new_version, 201)
    assert write(client, "POST", "/resume-versions", headers, new_version, 201)["id"] == v1["id"]
    v2 = write(client, "PATCH", f"/resume-versions/{v1['id']}", headers,
               {**base, "request_id": key(), "block_numbers": [2]}, 201)
    assert v2["version_number"] == 2 and len(read(client, f"/resume-versions/{v1['id']}", headers)["content"]) == 2
    write(client, "PATCH", f"/resume-versions/{v1['id']}", headers, {**base, "request_id": key()}, 409)

    record = {"job_id": jid, "request_id": key(), "resume_version_id": v1["id"], "next_action": "准备面试",
              "contact": "测试专用联系人", "channel": "手动站点"}
    app = write(client, "POST", "/applications", headers, record, 201)
    endpoint = f"/applications/{app['id']}"
    assert write(client, "POST", "/applications", headers, record, 201)["id"] == app["id"]
    write(client, "POST", "/applications", headers, {**record, "request_id": key()}, 409)
    write(client, "POST", "/applications", second, record, 404)
    assert client.get("/api/v1" + endpoint + "/history", headers=second).status_code == 404
    sent = {"request_id": key(), "revision": app["revision"], "status": "applied", "notes": "用户手动投递",
            "applied_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat()}
    app = write(client, "POST", endpoint + "/status", headers, sent)
    assert write(client, "POST", endpoint + "/status", headers, sent)["revision"] == app["revision"]
    write(client, "PATCH", endpoint, headers, {"revision": app["revision"], "resume_version_id": v2["id"]}, 409)
    write(client, "POST", endpoint + "/status", headers, {**sent, "status": "made_up"}, 422)
    write(client, "POST", endpoint + "/status", headers, {**sent, "request_id": key()}, 409)
    for status in ("written_test", "interview_1", "offer"):
        app = write(client, "POST", endpoint + "/status", headers,
                    {"request_id": key(), "revision": app["revision"], "status": status})
    history = read(client, endpoint + "/history", headers)
    assert [row["new_status"] for row in history] == ["offer", "interview_1", "written_test", "applied", "wishlist"]

    when = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=2)
    appointment = {"application_id": app["id"], "request_id": key(), "timezone": "UTC",
                   "scheduled_at": when.isoformat(), "interview_round": "interview_1", "interview_type": "online"}
    calendar = write(client, "POST", "/interview-schedules", headers, appointment, 201)
    assert write(client, "POST", "/interview-schedules", headers, appointment, 201)["id"] == calendar["id"]
    write(client, "POST", "/interview-schedules", headers, {**appointment, "request_id": key()}, 409)
    write(client, "POST", "/interview-schedules", headers, {**appointment, "request_id": key(), "timezone": "Asia/Shanghai"}, 422)
    write(client, "POST", "/interview-schedules", second, appointment, 404)
    edit = {name: appointment[name] for name in ("timezone", "scheduled_at", "interview_round", "interview_type")}
    write(client, "PATCH", f"/interview-schedules/{calendar['id']}", headers, {
        **edit, "revision": calendar["revision"], "result": "passed", "retrospective": "真实面试复盘（测试样本）"})

    write(client, "PATCH", url, headers, {"job": {**{name: data[name] for name in
          ("position_name", "company_name", "location", "job_type", "source_url")},
          "job_description": "不同的版本。新的招聘要求用于测试历史数据保留。"}}, 200)
    setup = {"interview_schedule_id": calendar["id"], "mode": "combined"}
    prepared = write(client, "POST", "/interviews/prepare", headers, setup)
    assert prepared["sources"]["resume_version"]["id"] == v1["id"]
    assert prepared["sources"]["job"]["revision"] == match["revision"]
    session = write(client, "POST", "/interviews/sessions", headers, {**setup, "request_id": key()}, 201)
    assert session["sources"]["application"]["id"] == app["id"]
    write(client, "POST", "/interviews/prepare", second, setup, 404)

    stats = read(client, "/job-analytics", headers)
    assert stats["sample_insufficient"] and stats["summary"]["rates"]["invited"]["rate"] is None
    with session_factory()() as db:
        app_count = db.scalar(select(func.count()).select_from(JobApplication).where(
            JobApplication.user_id == user["id"], JobApplication.applied_at.is_not(None)))
        offer_count = db.scalar(select(func.count(func.distinct(ApplicationStatusHistory.application_id)))
            .join(JobApplication, JobApplication.id == ApplicationStatusHistory.application_id)
            .where(JobApplication.user_id == user["id"], ApplicationStatusHistory.new_status == "offer"))
        pass_count = db.scalar(select(func.count(func.distinct(InterviewSchedule.application_id))).where(
            InterviewSchedule.user_id == user["id"], InterviewSchedule.details["result"].as_string() == "passed"))
        assert (stats["summary"]["submitted"], stats["summary"]["offer"], stats["summary"]["interview_passed"]) == (
            app_count, offer_count, pass_count) == (1, 1, 1)
    assert read(client, "/job-pipeline", headers)["columns"]["offer"][0]["id"] == app["id"]
    preview = write(client, "POST", "/job-strategy/preview", headers, {})
    assert "星河科技" not in str(preview["payload"]) and "测试专用联系人" not in str(preview["payload"])
    write(client, "POST", "/job-strategy/analyze", second, {"approval": preview["approval"]}, 409)
    submitted = write(client, "POST", "/job-strategy/analyze", headers, {"approval": preview["approval"]}, 202)
    path = f"/job-strategy/reports/{submitted['id']}"
    if index == 0:
        assert run_strategy_once(session_factory(), StrategyFailure, report_id=submitted["id"])
        assert read(client, path, headers)["error_code"] == "MODEL_TIMEOUT"
        write(client, "POST", "/job-strategy/analyze", headers, {"approval": preview["approval"]}, 202)
    assert run_strategy_once(session_factory(), StrategyFixture, report_id=submitted["id"])
    result = read(client, path, headers)
    assert result["state"] == "succeeded" and result["analysis"]["inferences"] == []
    assert result["statistics"]["summary"] == stats["summary"]
    assert client.get("/api/v1" + path, headers=second).status_code == 404
    assert client.delete("/api/v1" + url, headers=headers).status_code == 204
    assert read(client, url, headers)["archived"]
    assert read(client, endpoint, headers)["job"]["jd"] == JD


def test_rate_threshold():
    from app.services.job_pipeline_service import metrics
    examples = [{"valid": True, "resume_passed": True, "written_test": False, "written_passed": False,
                "invited": True, "interview_decided": True, "interview_passed": False, "offer": False}] * 5
    assert metrics(examples)["rates"]["invited"] == {"numerator": 5, "denominator": 5, "rate": 1.0}
    assert metrics(examples)["rates"]["written_passed"]["rate"] is None


def test_concurrent_schedule_across_timezones(client, bearer_headers):
    from zoneinfo import ZoneInfo

    headers = bearer_headers()
    job = write(client, "POST", "/jobs", headers, {
        "position_name": "并发日程验收", "job_description": "合成 JD：整理用户访谈和数据分析材料。"
    }, 201)
    record = write(client, "POST", "/applications", headers, {
        "job_id": job["id"], "request_id": key()
    }, 201)
    start = (datetime.now(UTC) + timedelta(days=1)).replace(second=0, microsecond=0)
    common = {"application_id": record["id"], "interview_round": "interview_1", "interview_type": "online"}

    def submit(zone):
        offset = start.astimezone(ZoneInfo(zone))
        return client.post("/api/v1/interview-schedules", headers=headers, json={
            **common, "request_id": key(), "timezone": zone, "scheduled_at": offset.isoformat()
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(submit, ["UTC", "Asia/Shanghai"]))
    assert sorted(response.status_code for response in replies) == [201, 409]
    winner = next(response.json() for response in replies if response.status_code == 201)
    assert datetime.fromisoformat(winner["scheduled_at"]) == start
    write(client, "PATCH", f"/interview-schedules/{winner['id']}", headers, {
        "interview_round": common["interview_round"], "interview_type": common["interview_type"],
        "revision": winner["revision"], "timezone": "UTC", "scheduled_at": start.isoformat(), "result": "cancelled",
    })
    assert submit("Asia/Shanghai").status_code == 201


@pytest.mark.skipif(os.getenv("CAREER_PHASE9_LIVE") != "1", reason="Requires approved live model access")
def test_live_strategy_with_synthetic_counts(client, bearer_headers):
    headers = bearer_headers()
    for index in range(5):
        job = write(client, "POST", "/jobs", headers, {
            "position_name": f"合成岗位 {index}", "job_description": "合成 JD：协助整理统计口径和用户反馈。"
        }, 201)
        write(client, "POST", "/applications", headers, {
            "job_id": job["id"], "request_id": key(), "applied_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        }, 201)
    preview = write(client, "POST", "/job-strategy/preview", headers, {})
    assert "合成岗位" not in str(preview["payload"]) and preview["payload"]["summary"]["submitted"] == 5
    submitted = write(client, "POST", "/job-strategy/analyze", headers, {"approval": preview["approval"]}, 202)
    assert run_strategy_once(session_factory(), report_id=submitted["id"])
    stored = read(client, f"/job-strategy/reports/{submitted['id']}", headers)
    assert stored["state"] == "succeeded", stored["error_code"]
    assert stored["analysis"]["priority_actions"] and stored["statistics"]["summary"]["submitted"] == 5
