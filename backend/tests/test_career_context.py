import os
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import select

from app.db.session import session_factory
from app.models.application import JobApplication
from app.models.discovery import DiscoverySession, ProjectRecommendation
from app.models.interview import InterviewReport, InterviewSession
from app.models.learning import LearningPath
from app.services.job_workflow import run_job_once
from conftest import PASSWORD
from test_applications import seed_resume
from test_discovery import queue, result, worker
from test_interviews import Fake, enqueue as enqueue_interview, status as interview_status, worker as interview_worker
from test_jobs import FakeProvider, JD
from test_product_acceptance import API, read, write
from test_resumes import workspace


class RoleInterview(Fake):
    def generate(self, prompt, data, schema):
        answer = super().generate(prompt, data, schema)
        if prompt.name == "interview_start":
            point = "SQL 分组" if "数据岗" in data["target"] else "用户访谈"
            answer.question = f"请用一段实例解释{point}。"
            answer.knowledge_point = point
        return answer


def test_two_jobs_keep_selected_sources(client, register_account, bearer_headers, workspace):
    email, account = register_account()
    own = bearer_headers(email)
    outsider = bearer_headers()
    content = seed_resume(email)
    write(client, "PUT", "/profiles/me", own, {"undergraduate_major": "合成案例", "target_position": "跨模块验收"})

    def create_job(title):
        created = write(client, "POST", "/jobs", own, {"position_name": title, "job_description": JD}, 201)
        route = f"/jobs/{created['id']}"
        write(client, "POST", route + "/parse", own, {"provider_host": "127.0.0.1",
                                                     "accept_external_processing": True}, 202)
        assert run_job_once(session_factory(), FakeProvider)
        parsed = read(client, route, own)
        confirmed = write(client, "PUT", route + "/requirements", own,
                          {"revision": parsed["revision"], "requirements": parsed["requirements"]})
        body = {"content_id": content, "revision": confirmed["revision"]}
        report = write(client, "POST", route + "/match", own, body)
        version = write(client, "POST", "/resume-versions", own,
                        {"request_id": str(uuid4()), "content_id": content, "target_job_id": created["id"],
                         "version_name": title, "change_summary": "定向证据", "block_numbers": [1], "confirmed": True}, 201)
        app = write(client, "POST", "/applications", own, {"job_id": created["id"], "request_id": str(uuid4()),
                     "resume_version_id": version["id"], "job_match_id": report["id"]}, 201)
        return report, version, app, route, body

    match_a, version_a, app_a, route_a, payload_a = create_job("合成数据岗 A")
    match_b, _, app_b, _, _ = create_job("合成研究岗 B")
    newer_a = write(client, "POST", route_a + "/match", own, {**payload_a, "assessments": {"0": "not_capable"}})
    assert newer_a["id"] != match_a["id"]
    assert read(client, route_a + "/match", own)["id"] == newer_a["id"]
    assert read(client, f"/job-matches/{match_a['id']}", own)["id"] == match_a["id"]
    changed = write(client, "PATCH", route_a, own, {"job": {
        "position_name": app_a["job"]["position"], "job_description": "更新 JD：本版本的资料不能覆盖已选择的投递。"
    }})
    assert changed["revision"] > match_a["revision"]
    sent = write(client, "POST", f"/applications/{app_a['id']}/status", own, {
        "request_id": str(uuid4()), "revision": app_a["revision"], "status": "applied"
    })
    assert sent["job"]["match_id"] == match_a["id"]
    assert read(client, f"/applications/{app_a['id']}", own)["job"]["jd"] == JD

    def project(application, match, title):
        creation = {"title": title, "application_id": application["id"], "job_match_id": match["id"]}
        session = write(client, "POST", "/discovery/sessions", own, creation, 201)
        sid = session["id"]

        def step(body):
            task = queue(client, own, sid, body)
            worker()
            return result(client, own, task)["result_id"]

        step({"kind": "turn", "message": "我在练习中手工整理表格三小时，重复核对多份记录。"})
        pain = step({"kind": "pain"})
        opportunity = step({"kind": "opportunity", "reference_id": pain})
        preview = write(client, "POST", f"/discovery/sessions/{sid}/preview", own,
                        {"kind": "recommend", "reference_id": opportunity})
        assert preview["payload"]["background"]["job_match"]["id"] == match["id"]
        assert preview["payload"]["background"]["target_position"] == application["job"]["position"]
        step({"kind": "recommend", "reference_id": opportunity})
        detail = read(client, f"/discovery/sessions/{sid}", own)
        assert len(detail["projects"]) == 3
        rec = detail["projects"][0]
        write(client, "PUT", f"/projects/recommendations/{rec['id']}", own, {"selected": True})
        prd = step({"kind": "prd", "reference_id": rec["id"]})
        assert read(client, f"/prds/{prd}", own)["recommendation_id"] == rec["id"]
        return session, rec, prd

    session_a, project_a, prd_a = project(app_a, match_a, "数据探索 A")
    session_b, project_b, _ = project(app_b, match_b, "研究探索 B")
    write(client, "POST", "/discovery/sessions", own, {
        "title": "错误岗位", "application_id": app_a["id"], "job_match_id": match_b["id"]
    }, 422)
    write(client, "POST", "/discovery/sessions", own, {
        "title": "不应替换旧报告", "application_id": app_a["id"], "job_match_id": newer_a["id"]
    }, 422)
    write(client, "POST", "/discovery/sessions", outsider, {
        "title": "不应读他人", "application_id": app_a["id"], "job_match_id": match_a["id"]
    }, 404)

    context_url = f"/applications/{app_a['id']}/career-context"
    context = read(client, context_url, own)
    assert context["match_id"] == match_a["id"]
    assert {row["session_id"] for row in context["projects"]} == {session_a["id"]}
    assert read(client, f"/interviews/options?application_id={app_a['id']}", own)["projects"][0]["id"] == project_a["id"]
    assert client.get(API + context_url, headers=outsider).status_code == 404
    setup_a = {"mode": "combined", "application_id": app_a["id"], "target": "合成研究岗 B"}
    appointment = write(client, "POST", "/interview-schedules", own, {
        "application_id": app_a["id"], "request_id": str(uuid4()), "timezone": "UTC",
        "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "interview_round": "interview_1", "interview_type": "online",
    }, 201)
    scheduled = write(client, "POST", "/interviews/prepare", own, {"mode": "combined", "interview_schedule_id": appointment["id"]})
    assert scheduled["sources"]["resume_version"]["id"] == version_a["id"]
    assert scheduled["sources"]["job"]["match_id"] == match_a["id"]
    assert scheduled["sources"]["plan"]["prd_id"] == prd_a
    write(client, "POST", "/interviews/prepare", own, {**setup_a, "recommendation_id": project_b["id"]}, 422)

    def practice(setup, topic):
        session = write(client, "POST", "/interviews/sessions", own, {**setup, "request_id": str(uuid4())}, 201)
        route = f"/interviews/sessions/{session['id']}"
        question_task = enqueue_interview(client, own, API + route, {"kind": "start"})
        interview_worker(RoleInterview)
        assert interview_status(client, own, API + route, question_task)["state"] == "succeeded"
        question = read(client, route + "/current-question", own)["question"]
        response_task = enqueue_interview(client, own, API + route, {"kind": "answer", "question_id": question["id"],
                                                                     "answer": "先核对输入并记录输出。"})
        interview_worker(RoleInterview)
        assert interview_status(client, own, API + route, response_task)["state"] == "succeeded"
        report = write(client, "POST", route + "/finish", own, {})
        assert {row["knowledge_point"] for row in report["weaknesses"]} == {topic}
        return session, report

    interview_a, report_a = practice(setup_a, "SQL 分组")
    _, report_b = practice({"mode": "combined", "application_id": app_b["id"]}, "用户访谈")
    assert report_b["id"] > report_a["id"]
    source_api = f"/learning/interview-sources/{report_a['id']}"
    assert read(client, source_api, own)["application_id"] == app_a["id"]
    assert client.get(API + source_api, headers=outsider).status_code == 404
    body = {"weekly_minutes": 150, "goal": "复练", "interview_report_id": report_a["id"]}
    path = write(client, "POST", "/learning/paths/generate", own, body, 201)
    assert write(client, "POST", "/learning/paths/generate", own, body, 201)["id"] == path["id"]
    revised = write(client, "PATCH", f"/learning/paths/{path['id']}", own, {"weekly_minutes": 180})
    assert revised["data"]["source"]["report_id"] == report_a["id"]
    write(client, "POST", "/learning/paths/generate", outsider, body, 404)
    with session_factory()() as db:
        assert db.get(JobApplication, app_a["id"]).snapshot["match_id"] == match_a["id"]
        assert db.get(DiscoverySession, session_a["id"]).job_match_id == match_a["id"]
        assert db.get(DiscoverySession, session_a["id"]).application_id == app_a["id"]
        assert db.get(DiscoverySession, session_b["id"]).job_match_id == match_b["id"]
        assert db.get(ProjectRecommendation, project_a["id"]).session_id == session_a["id"]
        assert db.get(InterviewSession, interview_a["id"]).context["sources"]["application"]["id"] == app_a["id"]
        assert db.get(InterviewReport, report_a["id"]).session_id == interview_a["id"]
        saved = db.scalar(select(LearningPath).where(LearningPath.id == path["id"], LearningPath.user_id == account["id"]))
        assert saved.data["source"]["match_id"] == match_a["id"]
        assert saved.data["source"]["weaknesses"] == ["SQL 分组"]
        assert any(module["id"] == "sql" and module["reason"] == "复练本次面试薄弱项" for module in saved.data["modules"])

    if os.getenv("CAREER_SPRINT3_BROWSER"):
        browser_flow(email, app_a["id"], session_a["id"], interview_a["id"], report_a["id"], match_a["id"])


def browser_flow(email, application_id, discovery_id, interview_id, report_id, match_id):
    base = os.environ["CAREER_SPRINT3_BROWSER"].rstrip("/")
    channel = os.getenv("CAREER_BROWSER_CHANNEL")
    with sync_playwright() as runner:
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page()
        page.goto(base + f"/application-workspace?tab=board&application={application_id}")
        expect(page).to_have_url(base + "/login")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(PASSWORD)
        page.get_by_role("button", name="登录", exact=True).click()
        page.get_by_role("link", name="查看匹配与能力差距").click()
        expect(page).to_have_url(re.compile(rf"[?&]match={match_id}(?:&|$)"))
        expect(page.get_by_role("heading", name="匹配报告")).to_be_visible()
        page.go_back()
        page.get_by_role("link", name="查看本次投递的推荐项目").click()
        page.get_by_role("button", name="数据探索 A").click()
        expect(page).to_have_url(re.compile(rf"[?&]session={discovery_id}(?:&|$)"))
        expect(page.get_by_role("button", name="研究探索 B")).to_have_count(0)
        page.goto(base + f"/interview-practice?tab=report&session={interview_id}")
        page.get_by_role("link", name="将本次薄弱项加入学习路线").click()
        expect(page).to_have_url(re.compile(rf"[?&]report={report_id}(?:&|$)"))
        expect(page.get_by_text("本次面试 · 合成数据岗 A · 薄弱项 SQL 分组")).to_be_visible()
        page.get_by_role("button", name="根据本次面试生成路线").click()
        expect(page.get_by_role("link", name=f"面试报告 #{report_id}")).to_be_visible()
        expect(page.get_by_text("用户访谈", exact=True)).to_have_count(0)
        page.reload()
        expect(page.get_by_role("link", name=f"面试报告 #{report_id}")).to_be_visible()
        browser.close()
