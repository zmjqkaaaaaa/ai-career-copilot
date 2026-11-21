import json
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document
from sqlalchemy import select

from app.ai.provider import Provider
from app.core.errors import ApiError
from app.db.session import session_factory
from app.models.career import CareerAnalysis, SkillEvidence, SkillProfile
from app.models.code_project import ProjectQuiz, ProjectSnapshot, QuizAttempt
from app.models.discovery import DiscoverySession, InterestRecord, PainPoint, ProjectRecommendation
from app.models.interview import InterviewReport, InterviewSession
from app.models.job import JobPosition
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.learning import EvaluationOutput
from app.services.learning_assessment import exam
from app.services.learning_workflow import evidence_review, rubric, run_learning_once, static_check

PREFIX = "/api/v1/learning"
CASES = [
    ("低空经济", "Python", "用 Python 分析任务", "python"),
    ("国际贸易", "SQL", "做 SQL 岗位分析", "sql"),
    ("设计", "需求分析", "用户研究和访谈", "research"),
    ("信息管理", "RAG", "准备 RAG 知识库", "rag"),
    ("物流工程", "FastAPI", "练 FastAPI 接口", "api"),
]


def seed_learning(email, major, skill):
    with session_factory().begin() as db:
        account = db.scalar(select(User).where(User.email == email))
        db.add(UserProfile(user_id=account.id, undergraduate_major=major, skills=[skill],
                           interested_industries=[], internship_experience=[], project_experience=[],
                           target_position="AI 产品经理实习"))
        db.add(JobPosition(user_id=account.id, position_name="AI 产品经理实习",
                           job_description=f"需要 {skill}，收集实际案例及测试证据", revision=1))


def post(client, headers, path, body, status=201):
    res = client.post(PREFIX + path, json=body, headers=headers)
    assert res.status_code == status, res.text
    return res.json()


def fetch(client, headers, path):
    res = client.get(PREFIX + path, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def queue(client, headers, body):
    private = post(client, headers, "/preview", body, 200)
    paths = {"lesson": f"/sessions/{body['record_id']}/messages", "path": f"/paths/{body['record_id']}/coach",
             "evaluation": f"/submissions/{body['record_id']}/evaluate"}
    path = paths[body["kind"]]
    data = {**body, "approval": private["approval"]}
    job = post(client, headers, path, data, 202)
    assert post(client, headers, path, data, 202)["id"] == job["id"]
    return job


class Fake:
    def __init__(self, _):
        pass

    def close(self):
        pass

    def generate(self, prompt, payload, schema):
        if prompt.name == "learning_evaluation":
            return schema.model_validate({"ratings": [{"criterion": key, "quote": "先根据岗位分组",
                "level": 2, "reason": "方法清楚，缺少验收样本"} for key in payload["rubric"]],
                "correct": ["尝试按组处理"], "errors": [], "missing": ["缺少缺失值用例"],
                "revision": "加一个空表样本，再写出预期结果", "next_step": "手算并核对分母"})
        return schema.model_validate({"explanation": "先说明字段如何分组。",
               "example": "两个岗位有同一个方向。", "question": "哪一列用于分组？",
               "next_step": "用两行样本推演", "summary": "讲过如何分组"})


def process(provider=Fake):
    assert run_learning_once(session_factory(), provider)


@pytest.mark.parametrize("major,skill,goal,topic", CASES)
def test_diagnosis_path_and_assessment(client, register_account, bearer_headers, major, skill, goal, topic):
    email, _ = register_account()
    seed_learning(email, major, skill)
    headers = bearer_headers(email)
    diagnose = fetch(client, headers, "/diagnosis")
    assert len(diagnose["categories"]) == 6
    assert next(row for row in diagnose["topics"] if row["topic"] == topic)["status"] == "self_reported"
    payload = {"weekly_minutes": 70, "goal": goal}
    path = post(client, headers, "/paths/generate", payload)
    assert post(client, headers, "/paths/generate", payload)["id"] == path["id"]
    seen = set()
    for entry in path["data"]["modules"]:
        assert set(entry["requires"]) <= seen
        seen.add(entry["id"])
    tasks = fetch(client, headers, "/tasks/daily?day=2026-11-21")
    assert tasks["minutes"] <= 10
    task_id = tasks["tasks"][0]["id"]
    assert fetch(client, headers, "/tasks/daily?day=2026-11-21")["tasks"][0]["id"] == task_id
    edit = client.patch(f"{PREFIX}/tasks/{task_id}", headers=headers, json={"status": "completed", "actual_minutes": 8})
    assert edit.status_code == 200 and edit.json()["actual_minutes"] == 8
    assert fetch(client, headers, "/progress")["diagnosis"]["summary"]["verified"] == 0
    assessment = post(client, headers, "/assessments/start", {"topic": topic})
    assert post(client, headers, "/assessments/start", {"topic": topic})["id"] == assessment["id"]
    assert all("correct" not in row for row in assessment["questions"])
    answers = {row["id"]: row["correct"] for row in exam(topic, 0)}
    endpoint = f"/assessments/{assessment['id']}/submit"
    result = post(client, headers, endpoint, {"answers": answers}, 200)
    assert result["result"]["score"] == 100 and result["result"]["mode"] == "first"
    assert post(client, headers, endpoint, {"answers": answers}, 200) == result
    revised = fetch(client, headers, "/paths")[0]
    assert revised["version"] == 2 and topic in revised["data"]["verified"]
    assert fetch(client, headers, "/progress")["history"][0]["data"]["status"] == "verified"
    retake = post(client, headers, "/assessments/start", {"topic": topic})
    wrong = {row["id"]: str((int(row["correct"]) + 1) % 3) for row in exam(topic, 1)}
    post(client, headers, f"/assessments/{retake['id']}/submit", {"answers": wrong}, 200)
    assert fetch(client, headers, "/progress")["history"][0]["data"]["status"] == "unknown"
    repeat = post(client, headers, "/assessments/start", {"topic": topic})
    post(client, headers, f"/assessments/{repeat['id']}/submit", {"answers": answers}, 200)
    assert fetch(client, headers, "/progress")["diagnosis"]["summary"]["verified"] == 0
    assert client.get(PREFIX + f"/paths/{path['id']}", headers=bearer_headers()).status_code == 404


def test_mentor_assignment_and_resources(client, bearer_headers):
    headers = bearer_headers()
    session = post(client, headers, "/sessions", {"topic": "sql", "mode": "socratic"})
    job = queue(client, headers, {"kind": "lesson", "record_id": session["id"], "message": "我把 COUNT 当成分组。"})
    process()
    first = fetch(client, headers, f"/sessions/{session['id']}/history")
    assert len(first["messages"]) == 2 and first["session"]["summary"]["question"]
    queue(client, headers, {"kind": "lesson", "record_id": session["id"], "message": "明白了，需要 GROUP BY。"})
    process()
    assert len(fetch(client, headers, f"/sessions/{session['id']}/history")["messages"]) == 4
    assert fetch(client, headers, "/jobs")[1]["id"] == job["id"]
    assert client.get(PREFIX + f"/sessions/{session['id']}/history", headers=bearer_headers()).status_code == 404
    response = client.post(PREFIX + "/resources/upload", headers=headers, data={"title": "学习笔记", "topic": "sql"},
                           files={"file": ("note.md", b"GROUP BY", "text/plain")})
    assert response.status_code == 201, response.text
    assert response.json()["text"] == "GROUP BY"
    document = Document()
    document.add_paragraph("可核对的学习说明")
    buffer = BytesIO()
    document.save(buffer)
    doc = client.post(PREFIX + "/resources/upload", headers=headers, data={"title": "文档", "topic": "sql"},
                      files={"file": ("lesson.docx", buffer.getvalue())})
    assert doc.status_code == 201 and doc.json()["text"] == "可核对的学习说明"
    assert client.post(PREFIX + "/resources/upload", headers=headers, data={"title": "伪文档", "topic": "sql"},
                       files={"file": ("fake.docx", b"invalid")}).status_code == 415
    assert client.post(PREFIX + "/resources/upload", headers=headers, data={"title":"unsafe", "topic":"sql"},
                       files={"file": ("program.exe", b"GROUP BY")}).status_code == 415
    assert all(row["id"] != response.json()["id"] for row in fetch(client, bearer_headers(), "/resources?topic=sql"))
    content = {"request_id": str(uuid4()), "kind": "analysis", "content": "先根据岗位分组，再核对指标。",
               "sample_outputs": {"before": 3, "distinct": 3}}
    sub = post(client, headers, "/assignments/sql/submit", content)
    assert post(client, headers, "/assignments/sql/submit", content)["id"] == sub["id"]
    queue(client, headers, {"kind": "evaluation", "record_id": sub["id"]})
    process()
    checked = fetch(client, headers, "/assignments/sql/submissions")[0]
    assert checked["status"] == "needs_revision" and checked["evaluation"]["score"] == 50
    assert [item["passed"] for item in checked["evaluation"]["fixture"]] == [True, False]
    update = post(client, headers, "/assignments/sql/submit",
                  {**content, "request_id": str(uuid4()), "content": content["content"] + "补充空表样本。"})
    assert update["version"] == 2


def test_retry_timeout_and_static_evidence(client, bearer_headers):
    headers = bearer_headers()
    session = post(client, headers, "/sessions", {"topic": "python", "mode": "python"})
    queued = queue(client, headers, {"kind": "lesson", "record_id": session["id"], "message": "什么是缺失值？"})

    class Timeout(Fake):
        def generate(self, *_):
            raise ApiError(504, "MODEL_TIMEOUT", "测试超时")

    process(Timeout)
    assert fetch(client, headers, "/jobs")[0]["error"] == "MODEL_TIMEOUT"
    assert post(client, headers, f"/jobs/{queued['id']}/retry", {}, 202)["attempt"] == 2
    process()
    assert fetch(client, headers, "/jobs")[0]["state"] == "succeeded"
    assert rubric("analysis", "mvp") != rubric("code", "python")
    assert rubric("text", "rag") != rubric("text", "sql")
    check = static_check("code", "python", "def broken:")
    assert check["status"] == "syntax_error"
    draft = EvaluationOutput.model_validate({"ratings": [{"criterion": "代码结构", "quote": "invented",
                   "level": 4, "reason": "模拟无据评分"}], "revision": "改函数定义", "next_step": "重读语法"})
    outcome = evidence_review(draft, {"rubric": rubric("code", "python"), "content": "def broken:", "static": check})
    assert outcome["score"] is None and outcome["status"] == "needs_revision"


def test_diagnosis_maps_prior_stages(client, register_account, bearer_headers):
    from test_interviews import seed

    email, _ = register_account()
    uid, resume, _, repo = seed(email, "信息管理", "Python", "SQL 课程作业")
    with session_factory().begin() as db:
        analysis = CareerAnalysis(user_id=uid, content_id=resume, target_direction="AI 产品",
                                  model_name="synthetic", prompt_version="test", analysis_result={})
        discovery = DiscoverySession(user_id=uid, title="虚构分析", mode="guided", weekly_hours=3)
        interview = InterviewSession(user_id=uid, request_id=str(uuid4()), target="AI 产品",
                                     state="finished", settings={}, context={})
        snapshot = db.scalar(select(ProjectSnapshot).where(ProjectSnapshot.project_id == repo))
        quiz = ProjectQuiz(snapshot_id=snapshot.id, data={})
        db.add_all([analysis, discovery, interview, quiz])
        db.flush()
        skill = SkillProfile(analysis_id=analysis.id, skill_name="Python", skill_category="coding", proficiency_level="basic",
                             evidence_status="verified", analysis_reason="提供过代码片段")
        db.add(skill)
        db.flush()
        db.add_all([
            SkillEvidence(skill_profile_id=skill.id, source_type="resume", block_number=1, source_content="用 Python 整理样本"),
            InterestRecord(user_id=uid, session_id=discovery.id, data={"name": "RAG"}),
            PainPoint(user_id=uid, session_id=discovery.id, data={"pain_point_name": "模拟访谈资料难以定位"}),
            QuizAttempt(snapshot_id=snapshot.id, quiz_id=quiz.id, data={"score": 80, "dimension": "api"}),
            InterviewReport(session_id=interview.id, data={"answered": 2, "score": 65,
                          "weaknesses": [{"knowledge_point": "结构化输出"}]}),
        ])
    result = fetch(client, bearer_headers(email), "/diagnosis")
    assert result["suggested_minutes"] == 180
    observed = {item["source"] for topic in result["topics"] for item in topic["evidence"]}
    assert {"个人档案", "简历职业画像", "岗位 JD（学习优先级）", "兴趣探索", "痛点分析", "项目掌握", "面试报告", "面试薄弱项"} <= observed
    assert result["summary"]["verified"] == 0


@pytest.mark.skipif(os.getenv("CAREER_LIVE_LEARNING") != "1", reason="Requires synthetic materials and configured model")
def test_live_learning(client, bearer_headers):
    headers = bearer_headers()
    path = post(client, headers, "/paths/generate", {"weekly_minutes": 140, "goal": "练习 SQL 关联与聚合"})
    queue(client, headers, {"kind": "path", "record_id": path["id"]})
    process(Provider)
    road = fetch(client, headers, "/paths")[0]
    assert road["data"]["mentor"], fetch(client, headers, "/jobs")[0]
    session = post(client, headers, "/sessions", {"topic": "sql", "mode": "socratic"})
    for message in ("我用 COUNT(*) 数岗位，可是关联技能表后结果变大，为什么？",
                    "如果一个岗位有两个技能，JOIN 会有两行，我应该用 COUNT(DISTINCT job_id)。"):
        queue(client, headers, {"kind": "lesson", "record_id": session["id"], "message": message})
        process(Provider)
        actual = fetch(client, headers, "/jobs")[0]
        assert actual["state"] == "succeeded", actual
    history = fetch(client, headers, f"/sessions/{session['id']}/history")
    assert len(history["messages"]) == 4
    submission = post(client, headers, "/assignments/sql/submit", {"kind": "code", "request_id": str(uuid4()),
                  "content": "SELECT direction, COUNT(*) AS n FROM jobs GROUP BY direction;\n-- 示例：两个 AI 岗位和一个数据岗，预期分别为 2 和 1。",
                  "sample_outputs": {"before": 3, "distinct": 2}})
    queue(client, headers, {"kind": "evaluation", "record_id": submission["id"]})
    process(Provider)
    evaluation = fetch(client, headers, "/assignments/sql/submissions")[0]["evaluation"]
    assert evaluation and evaluation["revision"], fetch(client, headers, "/jobs")[0]
    assert all(row["passed"] for row in evaluation["fixture"])
    if os.getenv("CAREER_LEARNING_REPORT_DIR"):
        path = Path(os.environ["CAREER_LEARNING_REPORT_DIR"])
        path.mkdir(parents=True, exist_ok=True)
        (path / "live-learning.json").write_text(json.dumps({"path": road, "lesson": history, "evaluation": evaluation},
                                                              ensure_ascii=False, indent=2), encoding="utf-8")

