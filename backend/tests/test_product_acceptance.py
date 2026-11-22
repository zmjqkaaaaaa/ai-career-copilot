"""One account progresses through every module via public application interfaces."""
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from app.db.session import session_factory
from app.resume_worker import run_once
from app.services.github_service import GitHub
from app.services.job_workflow import run_job_once
from app.services.learning_assessment import exam
from conftest import PASSWORD
from test_code_projects import GitHubFake, code_worker, enqueue as project_queue, status as project_status
from test_discovery import queue as discovery_queue, result as discovery_result, worker as discovery_worker
from test_interviews import enqueue as interview_queue, status as interview_status, worker as interview_worker
from test_jobs import FakeProvider as JobProvider, JD
from test_learning import process as learning_worker, queue as learning_queue
from test_resumes import SyntheticProvider, create_parsed, workspace  # shared synthetic DOCX fixture

API = "/api/v1"
RETROSPECTIVE = "验收样本：需要清楚说明库存统计口径。"


def read(client, route, headers, params=None):
    response = client.get(API + route, headers=headers, params=params)
    assert response.status_code == 200, f"{route}: {response.status_code} {response.text}"
    return response.json()


def write(client, method, route, headers, data, expected=200):
    response = client.request(method, API + route, headers=headers, json=data)
    assert response.status_code == expected, f"{route}: {response.status_code} {response.text}"
    return response.json()


def run_browser(email, refs):
    base = os.environ["CAREER_ACCEPTANCE_BROWSER"].rstrip("/")
    with sync_playwright() as runner:
        channel = os.environ.get("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page(viewport={"width": 1280, "height": 900}, timezone_id="UTC")
        page.goto(base + "/growth")
        expect(page).to_have_url(base + "/login")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(PASSWORD)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(base + "/growth")
        expect(page.get_by_text("已通过测评 1 项", exact=False)).to_be_visible()
        page.get_by_role("button", name="成长报告", exact=True).click()
        expect(page.get_by_text("独立知识与应用选择题通过", exact=False).first).to_be_visible()
        page.goto(base + "/")
        expect(page.get_by_text("合成贯通验收", exact=False).first).to_be_visible()
        expect(page.get_by_text("测评已验证 · 1 项", exact=True)).to_be_visible()
        expect(page.get_by_role("link", name=refs["proposal_name"])).to_have_attribute(
            "href", f"/project-recommendations?session={refs['discovery']}"
        )
        expect(page.get_by_role("link", name="查看面试报告")).to_have_attribute(
            "href", f"/interview-practice?tab=report&session={refs['interview']}"
        )
        expect(page.get_by_role("region", name="今日学习任务").locator("li").first).to_be_visible()
        expect(page.get_by_role("region", name="当前投递进度").get_by_text("一面", exact=True)).to_be_visible()
        action = page.get_by_role("region", name="下一步行动")
        expect(action.get_by_text("准备库存问题复盘")).to_be_visible()
        action.get_by_role("link", name="前往处理").click()
        board = f"/application-workspace?tab=board&application={refs['application']}"
        expect(page).to_have_url(base + board)
        expect(page.get_by_role("link", name="查看匹配与能力差距")).to_have_attribute(
            "href", f"/job-matching?job={refs['job']}&match={refs['match']}"
        )
        expect(page.get_by_role("link", name="查看投递简历")).to_have_attribute(
            "href", f"/application-workspace?tab=versions&version={refs['resume_version']}"
        )
        page.goto(base + f"/application-workspace?tab=schedules&application={refs['application']}&schedule={refs['schedule']}")
        page.get_by_role("button", name="编辑日程或结果").click()
        page.get_by_label("面试结果").select_option("passed")
        page.get_by_label("面试复盘").fill(RETROSPECTIVE)
        page.get_by_role("button", name="保存面试日程").click()
        expect(page.get_by_text(RETROSPECTIVE, exact=False)).to_be_visible()
        page.get_by_role("link", name="进入模拟面试").click()
        expect(page).to_have_url(base + f"/interview-practice?schedule={refs['schedule']}")
        expect(page.get_by_text("使用关联投递保存的 JD 和简历版本。")).to_be_visible()
        page.goto(base + "/application-workspace?tab=analytics")
        expect(page.get_by_text("面试通过率 · 1/1 · 样本不足")).to_be_visible()
        expect(page.get_by_role("rowheader", name="库存定向版")).to_be_visible()
        page.goto(base + f"/project-recommendations?session={refs['discovery']}")
        page.get_by_role("link", name="在项目工作台关联仓库").click()
        expect(page.get_by_text("关联方案 · " + refs["proposal_name"])).to_be_visible()
        page.goto(base + f"/project-workspace?project={refs['repository']}")
        expect(page.get_by_text("已关联方案 · " + refs["proposal_name"])).to_be_visible()
        page.get_by_role("link", name="使用此版本练习项目面试").click()
        expect(page.get_by_label("面试模式")).to_have_value("project")
        expect(page.get_by_label("选择已导入仓库")).to_have_value(str(refs["repository"]))
        expect(page.get_by_label("仓库提交")).to_have_value(refs["commit"])
        page.get_by_role("button", name="核对面试准备").click()
        expect(page.get_by_text("关联项目 PRD · 第 2 版")).to_be_visible()
        page.goto(base + f"/interview-practice?tab=report&session={refs['interview']}")
        expect(page.get_by_role("heading", name="逐题复盘")).to_be_visible()
        page.reload()
        expect(page.get_by_role("heading", name="逐题复盘")).to_be_visible()
        anonymous = browser.new_page()
        url = base + f"/interview-practice?tab=report&session={refs['interview']}"
        anonymous.goto(url)
        expect(anonymous).to_have_url(base + "/login")
        anonymous.get_by_label("邮箱").fill(email)
        anonymous.get_by_label("密码").fill(PASSWORD)
        anonymous.get_by_role("button", name="登录", exact=True).click()
        expect(anonymous).to_have_url(url)
        expect(anonymous.get_by_role("heading", name="逐题复盘")).to_be_visible()
        browser.close()


def test_one_account_across_nine_stages(client, register_account, bearer_headers, workspace):
    # The application itself handles auth, files, workers, scoring, snapshots and persistence.
    # Deterministic model responses keep the same chain reproducible across runs.
    host = "127.0.0.1"
    consent = {"provider_host": host, "accept_external_processing": True}
    email, account = register_account("合成贯通验收")
    headers = bearer_headers(email)
    outsider = bearer_headers()
    me = read(client, "/users/me", headers)
    assert me["id"] == account["id"]
    profile = write(client, "PUT", "/profiles/me", headers, {
        "target_position": "AI 产品实习生", "undergraduate_major": "国际贸易", "skills": ["SQL"],
        "project_experience": [{"title": "库存看板原型", "description": "合成课程练习"}],
    })
    refs = {"account": me["id"], "profile": profile["id"]}

    resume_path, resume_id, parsed, _ = create_parsed(client, headers, workspace)
    extracted = client.post(resume_path + "/extract", headers=headers, json={"content_id": parsed["id"], **consent})
    assert extracted.status_code == 202, extracted.text
    assert run_once(provider_factory=SyntheticProvider)
    draft = client.get(resume_path + "/content", headers=headers).json()
    confirmed = client.put(resume_path + "/content", headers=headers,
                           json={"content_id": draft["id"], "structured_data": draft["structured_data"]})
    assert confirmed.status_code == 200, confirmed.text
    content_id = confirmed.json()["id"]
    write(client, "POST", "/career/analyze", headers, {"resume_id": resume_id, "content_id": content_id,
          "target_direction": profile["target_position"], **consent}, 202)
    assert run_once(provider_factory=SyntheticProvider)
    career = read(client, "/career/profile", headers)
    ability = next(row for row in career["report"]["skills"] if row["name"] == "SQL")
    assert ability["status"] == "self_reported" and ability["sources"]
    refs.update(resume=resume_id, confirmed_resume=content_id, career=career["analysis"]["id"])

    job = write(client, "POST", "/jobs/import-jd", headers, {
        "position_name": profile["target_position"], "job_description": JD,
        "source_url": "https://example.invalid/synthetic-inventory-role",
    }, 201)
    job_url = f"/jobs/{job['id']}"
    write(client, "PATCH", job_url, headers, {"favorite": True})
    assert [item["id"] for item in read(client, "/jobs", headers, {"favorite": True})] == [job["id"]]
    write(client, "POST", job_url + "/parse", headers, consent, 202)
    assert run_job_once(session_factory(), JobProvider)
    job = read(client, job_url, headers)
    assert job["requirements"]
    confirmed_job = write(client, "PUT", job_url + "/requirements", headers,
                          {"revision": job["revision"], "requirements": job["requirements"]})
    match = write(client, "POST", job_url + "/match", headers,
                  {"content_id": content_id, "revision": confirmed_job["revision"]})
    assert match["content_id"] == content_id and match["overall_score"] is not None
    refs.update(job=job["id"], match=match["id"])

    saved_resume = write(client, "POST", "/resume-versions", headers, {
        "request_id": str(uuid4()), "content_id": content_id, "target_job_id": job["id"],
        "version_name": "库存定向版", "change_summary": "保留已确认的原文",
        "block_numbers": [row["number"] for row in confirmed.json()["blocks"]], "confirmed": True,
    }, 201)
    application = write(client, "POST", "/applications", headers, {
        "job_id": job["id"], "request_id": str(uuid4()), "resume_version_id": saved_resume["id"],
        "job_match_id": match["id"], "next_action": "准备库存问题复盘",
    }, 201)
    application = write(client, "POST", f"/applications/{application['id']}/status", headers, {
        "request_id": str(uuid4()), "revision": application["revision"], "status": "applied"
    })
    application = write(client, "POST", f"/applications/{application['id']}/status", headers, {
        "request_id": str(uuid4()), "revision": application["revision"], "status": "interview_1"
    })
    appointment = {"timezone": "UTC", "interview_round": "interview_1", "interview_type": "online",
                   "scheduled_at": (datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(hours=2)).isoformat()}
    schedule = write(client, "POST", "/interview-schedules", headers, {
        **appointment, "application_id": application["id"], "request_id": str(uuid4()),
    }, 201)
    assert schedule["application_id"] == application["id"]
    refs.update(application=application["id"], resume_version=saved_resume["id"], schedule=schedule["id"])
    discovery = write(client, "POST", "/discovery/sessions", headers, {
        "title": "库存学习项目", "weekly_hours": 3, "application_id": application["id"], "job_match_id": match["id"]
    }, 201)
    sid = discovery["id"]
    background = read(client, f"/discovery/sessions/{sid}", headers)["background"]
    assert background["career_analysis_id"] == refs["career"]
    assert background["undergraduate_major"] == profile["undergraduate_major"]
    assert background["job_match"]["id"] == match["id"] and background["job_match"]["score"] == match["overall_score"]
    assert next(row for row in background["abilities"] if row["name"] == "SQL")["sources"] == ability["sources"]

    def step(body):
        task = discovery_queue(client, headers, sid, body)
        discovery_worker()
        return discovery_result(client, headers, task)["result_id"]

    step({"kind": "turn", "message": "在合成仓储课程里，我用 SQL 和表格复核库存，后来手工整理了三小时。"})
    pain = step({"kind": "pain"})
    research = step({"kind": "research", "reference_id": pain, "sources": [{
        "url": "https://example.com/synthetic-reference", "title": "合成资料", "excerpt": "支持记录检索", "source_type": "official"}]})
    source = read(client, f"/research/competitors/{research}", headers)["data"]["sources"][0]
    assert source["method"] == "user_supplied"
    chance = step({"kind": "opportunity", "reference_id": pain, "research_id": research})
    step({"kind": "recommend", "reference_id": chance})
    options = read(client, "/projects/recommendations", headers)
    assert len(options) == 3
    proposal = options[0]["id"]
    write(client, "PUT", f"/projects/recommendations/{proposal}", headers, {"selected": True})
    prd = step({"kind": "prd", "reference_id": proposal})
    snapshot = read(client, f"/prds/{prd}", headers)
    assert snapshot["recommendation_id"] == proposal and "验收标准" in snapshot["content"]
    revised = write(client, "PUT", f"/prds/{prd}", headers, {"version": 1, "title": "合成验收 PRD 第二版",
                    "content": snapshot["content"] + "\n\n库存练习验收条目。"}, 201)
    refs.update(discovery=sid, pain=pain, market=research, proposal=proposal, proposal_name=options[0]["data"]["name"], prd=revised["id"])

    live_github = os.getenv("CAREER_ACCEPTANCE_LIVE_GITHUB") == "1"
    repo_url = "https://github.com/sindresorhus/yocto-queue" if live_github else "https://github.com/school/course"
    assert client.post(API + "/code-projects/import", headers=outsider,
                       json={"url": repo_url, "recommendation_id": proposal}).status_code == 404
    imported = write(client, "POST", "/code-projects/import", headers,
                     {"url": repo_url, "recommendation_id": proposal}, 202)
    repo = imported["project"]["id"]
    repo_url = f"/code-projects/{repo}"
    code_worker(github=GitHub if live_github else GitHubFake)
    project_status(client, headers, API + repo_url, imported["task"]["id"])
    project = read(client, repo_url, headers)
    commit = project["active_commit"]
    assert len(commit) == 40 and project["recommendation_id"] == proposal
    assert read(client, f"/code-projects/recommendations/{proposal}", headers)["name"] == refs["proposal_name"]
    files = read(client, repo_url + "/files", headers)
    source_path = "index.js" if live_github else "main.py"
    source_file = next(row for row in files if row["path"] == source_path)
    assert source_file["loaded"]
    task = project_queue(client, headers, repo, {"kind": "quiz", "commit": commit, "dimension": "functions",
                         "mode": "function", "file_id": source_file["id"]})
    code_worker()
    quiz = project_status(client, headers, API + repo_url, task)["result_id"]
    task = project_queue(client, headers, repo, {"kind": "grade", "commit": commit,
                         "quiz_id": quiz, "answer": "我能按源码解释输入、返回与边界。"})
    code_worker()
    attempt = project_status(client, headers, API + repo_url, task)["result_id"]
    assert read(client, repo_url + "/mastery-report", headers)["attempts"][0]["id"] == attempt
    refs.update(repository=repo, commit=commit, quiz=quiz, code_attempt=attempt, live_github=live_github)

    opts = {"mode": "project", "repository_id": repo, "interview_schedule_id": schedule["id"], "commit": commit}
    prep = write(client, "POST", "/interviews/prepare", headers, opts)
    assert prep["sources"]["plan"]["prd_id"] == revised["id"]
    assert prep["sources"]["job"]["match_id"] == match["id"]
    assert prep["sources"]["resume_version"]["id"] == saved_resume["id"]
    assert prep["sources"]["application"]["id"] == application["id"]
    assert prep["sources"]["application"]["schedule_id"] == schedule["id"]
    assert prep["sources"]["analysis_id"] == refs["career"]
    assert prep["sources"]["repository"]["commit"] == commit
    assert "practice" in prep["source_types"] and prep["has_project_code"]
    interview = write(client, "POST", "/interviews/sessions", headers, {**opts, "request_id": str(uuid4())}, 201)
    iv = f"/interviews/sessions/{interview['id']}"
    task = interview_queue(client, headers, API + iv, {"kind": "start"})
    interview_worker()
    assert interview_status(client, headers, API + iv, task)["state"] == "succeeded"
    question = read(client, iv + "/current-question", headers)["question"]
    assert any(item.get("commit") == commit for item in question["references"])
    task = interview_queue(client, headers, API + iv, {"kind": "answer", "question_id": question["id"],
                           "answer": "我先看函数的输入，再逐步核对返回值。"})
    interview_worker()
    assert interview_status(client, headers, API + iv, task)["state"] == "succeeded"
    assert read(client, iv, headers)["question"]["parent_id"] == question["id"]
    report = write(client, "POST", iv + "/finish", headers, {})
    assert report["answered"] == 1 and report["practice_evidence"]
    assert report["sources"] == prep["sources"]
    training = read(client, "/interviews/training-plans", headers)["tasks"]
    assert training and training[0]["report_id"] == report["id"]
    refs.update(interview=interview["id"], interview_report=report["id"], interview_training=training[0]["id"])

    diag = read(client, "/learning/diagnosis", headers)
    evidence = {(row["source"], row["ref"]) for topic in diag["topics"] for row in topic["evidence"]}
    expected = {("个人档案", profile["id"]), ("简历职业画像", refs["career"]), ("岗位匹配报告", match["id"]),
                ("痛点分析", pain), ("已选项目", proposal), ("项目 PRD", revised["id"]), ("项目掌握", attempt),
                ("面试报告", report["id"]), ("面试训练任务", training[0]["id"])}
    assert expected <= evidence, expected - evidence
    assert diag["suggested_minutes"] == 180 and diag["summary"]["verified"] == 0
    roadmap = write(client, "POST", "/learning/paths/generate", headers,
                    {"weekly_minutes": diag["suggested_minutes"], "goal": "SQL 和需求分析"}, 201)
    assert roadmap["data"]["target"] == job["position_name"]
    assert read(client, "/learning/tasks/daily", headers)["tasks"]
    lesson = write(client, "POST", "/learning/sessions", headers, {"topic": "sql", "mode": "sql"}, 201)
    queued = learning_queue(client, headers, {"kind": "lesson", "record_id": lesson["id"], "message": "我先根据岗位分组。"})
    learning_worker()
    assert read(client, "/learning/jobs", headers)[0]["id"] == queued["id"]
    assert len(read(client, f"/learning/sessions/{lesson['id']}/history", headers)["messages"]) == 2
    submission = write(client, "POST", "/learning/assignments/sql/submit", headers, {
        "request_id": str(uuid4()), "kind": "analysis", "content": "先根据岗位分组，再核对样例。",
        "sample_outputs": {"before": 3, "distinct": 2}}, 201)
    learning_queue(client, headers, {"kind": "evaluation", "record_id": submission["id"]})
    learning_worker()
    saved = read(client, "/learning/assignments/sql/submissions", headers)[0]
    assert saved["id"] == submission["id"] and all(row["passed"] for row in saved["evaluation"]["fixture"])
    assessment = write(client, "POST", "/learning/assessments/start", headers, {"topic": "sql"}, 201)
    body = {"answers": {row["id"]: row["correct"] for row in exam("sql", 0)}}
    score = write(client, "POST", f"/learning/assessments/{assessment['id']}/submit", headers, body)
    assert score["result"]["score"] == 100
    progress = read(client, "/learning/reports", headers)
    assert progress["diagnosis"]["summary"]["verified"] == 1
    assert progress["history"][0]["assessment_id"] == assessment["id"]
    assert read(client, "/learning/paths", headers)[0]["version"] > roadmap["version"]
    refs.update(learning_path=roadmap["id"], learning_assessment=assessment["id"], learning_submission=submission["id"])
    linked_path = write(client, "POST", "/learning/paths/generate", headers, {
        "weekly_minutes": 150, "goal": "复盘项目面试", "interview_report_id": report["id"]
    }, 201)
    assert linked_path["data"]["source"]["application_id"] == application["id"]
    assert linked_path["data"]["source"]["match_id"] == match["id"]
    refs["linked_learning_path"] = linked_path["id"]

    overview = read(client, "/dashboard", headers)
    assert overview["target_position"] == profile["target_position"] and overview["profile_complete"]
    assert overview["skills"]["verified"] == 1
    assert overview["match"]["id"] == match["id"]
    assert overview["match"]["gaps"] == [
        {"name": item["name"], "status": item["status"]}
        for item in read(client, f"/job-matches/{match['id']}/gaps", headers)[:4]
    ]
    assert overview["projects"][0]["id"] == proposal
    assert overview["projects"][0]["selected"]
    assert overview["tasks"]
    assert overview["interview"]["session_id"] == interview["id"]
    assert overview["interview"]["score"] == report["score"]
    assert overview["applications"] == {"interview_1": 1}
    assert overview["next_action"] == {"kind": "application", "text": "准备库存问题复盘",
                                       "application_id": application["id"]}
    foreign_overview = read(client, "/dashboard", outsider)
    assert not foreign_overview["projects"] and not foreign_overview["tasks"] and not foreign_overview["applications"]
    assert foreign_overview["match"] is None and foreign_overview["interview"] is None

    for route in (f"/career/profile?analysis_id={refs['career']}", f"/jobs/{job['id']}",
                  f"/discovery/sessions/{sid}", f"/prds/{revised['id']}", repo_url, iv + "/report",
                  f"/learning/paths/{roadmap['id']}", f"/learning/assessments/{assessment['id']}/result"):
        assert client.get(API + route, headers=outsider).status_code == 404, route
    assert read(client, "/learning/reports", outsider)["diagnosis"]["summary"]["verified"] == 0
    if os.getenv("CAREER_ACCEPTANCE_BROWSER"):
        run_browser(email, refs)
        refs["same_account_browser"] = True
    else:
        write(client, "PATCH", f"/interview-schedules/{schedule['id']}", headers, {
            **appointment, "revision": schedule["revision"], "result": "passed", "retrospective": RETROSPECTIVE,
        })
    updated = read(client, "/interview-schedules", headers)
    assert [(item["id"], item["result"], item["retrospective"]) for item in updated] == [
        (schedule["id"], "passed", RETROSPECTIVE)
    ]
    assert read(client, "/interview-schedules", outsider) == []
    history = read(client, f"/applications/{application['id']}/history", headers)
    assert [item["new_status"] for item in history] == ["interview_1", "applied", "wishlist"]
    analytics = read(client, "/job-analytics", headers)
    assert analytics["sample_insufficient"]
    assert {key: analytics["summary"][key] for key in ("submitted", "invited", "interview_passed")} == {
        "submitted": 1, "invited": 1, "interview_passed": 1,
    }
    assert analytics["summary"]["rates"]["interview_passed"]["rate"] is None
    if os.getenv("CAREER_ACCEPTANCE_REPORT"):
        path = Path(os.environ["CAREER_ACCEPTANCE_REPORT"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**refs, "linked_evidence": sorted(expected), "match_score": match["overall_score"],
                                    "interview_passed": analytics["summary"]["interview_passed"],
                                    "assessment_score": score["result"]["score"]}, ensure_ascii=False, indent=2), encoding="utf-8")

