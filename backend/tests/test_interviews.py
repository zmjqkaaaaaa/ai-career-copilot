import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ai.provider import Provider
from app.core.errors import ApiError
from app.db.session import session_factory
from app.models.code_project import CodeProject, ProjectFile, ProjectSnapshot
from app.models.interview import InterviewSession
from app.models.job import JobPosition, JobRequirement
from app.models.resume import Resume, ResumeContent
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.interview import EvaluationDraft
from app.services.code_project_workflow import run_code_project_once
from app.services.codebase_parser import parse_file
from app.services.github_service import GitHub
from app.services.interview_engine import run_interview_once
from app.services.interview_evaluation_service import evaluate, rules
from app.services.resumes import utc_now
from interview_cases import AI_QUESTIONS, BACKGROUNDS, PRODUCT_QUESTIONS, PROJECT_PROBES

PREFIX = "/api/v1/interviews"
PUBLIC_REPO = "https://github.com/sindresorhus/yocto-queue"
SHA = "7" * 40
ANSWER = "我先提取输入，再核对字段并做异常测试。"


def seed(email, major, skill, experience):
    with session_factory().begin() as db:
        user = db.scalar(select(User).where(User.email == email))
        db.add(UserProfile(user_id=user.id, undergraduate_major=major, skills=[skill], interested_industries=[],
                           internship_experience=[], project_experience=[{"title": experience}], target_position="AI 产品实习"))
        resume = Resume(user_id=user.id, original_filename="测试简历.pdf", storage_key=uuid4().hex,
                        file_type="pdf", file_size=1, parse_status="parsed")
        job = JobPosition(user_id=user.id, position_name="AI 产品实习", job_description="验证独立完成需求分析和评估指标",
                          parsed={}, confirmed=True, revision=1)
        repo = CodeProject(user_id=user.id, slug="fictional/interview", metadata_json={}, active_commit=SHA)
        db.add_all([resume, job, repo])
        db.flush()
        row = ResumeContent(resume_id=resume.id, version=1, parser_version="test", extracted_text=experience,
                            blocks=[{"number": 1, "text": experience}], structured_data={}, confirmed=True)
        snapshot = ProjectSnapshot(project_id=repo.id, commit_sha=SHA, data={})
        db.add_all([row, snapshot, JobRequirement(job_id=job.id, revision=1, ordinal=1,
                   requirement={"name": "需求分析与指标设计", "importance": "required"})])
        db.flush()
        source, index = parse_file("main.py", "Python", "def assess(row):\n    return row.get('score')\n")
        db.add(ProjectFile(snapshot_id=snapshot.id, path="main.py", blob_sha=SHA, size=len(source),
                           content=source, index_data=index, metadata_json={"priority": 2, "kind": "source",
                           "language": "Python", "core": True, "readable": True}))
        return user.id, row.id, job.id, repo.id


class Fake:
    def __init__(self, _):
        pass

    def close(self):
        pass

    def generate(self, prompt, data, schema):
        if prompt.name == "interview_start":
            refs = data["sources"]
            target_sources = {"resume": "resume", "project": "code", "product": "jd", "technical": "jd"}
            expected = target_sources.get(data["mode"], "resume")
            reference = next(item for item in refs if item["kind"] == expected)
            point = {"resume": "个人贡献", "code": "函数输入", "jd": "实际验证"}[expected]
            return schema.model_validate({"question": f"请说明你对「{point}」的理解？", "knowledge_point": point,
                "basis": "source", "references": [reference["id"]], "hint": "先说一个具体例子"})
        answer = data["answer"]
        draft = {"ratings": [{"dimension": row["key"], "level": 3, "reason": "给出步骤", "quote": answer[:40]}
                             for row in data["rubric"]],
                 "strengths": ["步骤清楚"], "missing": ["缺少异常案例"], "corrected_idea": "说明验证方法",
                 "answer_outline": ["输入", "步骤", "结果"], "exercise": "构造两个异常样本", "acceptance": "说明处理结果",
                 "action": "follow_up", "followup_quote": answer[:8], "followup_reason": "没有给出异常案例",
                 "next_question": {"question": "请举一个你会如何验证的异常输入？", "knowledge_point": "异常输入",
                                   "basis": "answer", "references": []}}
        return schema.model_validate(draft)


def worker(provider=Fake):
    assert run_interview_once(session_factory(), provider)


def create(client, headers, **values):
    req = {"mode": "technical", "minutes": 15, "request_id": str(uuid4()), **values}
    response = client.post(f"{PREFIX}/sessions", headers=headers, json=req)
    assert response.status_code == 201, response.text
    return response.json()


def enqueue(client, headers, path, body, mismatched=None):
    preview = client.post(path + "/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    route = path + ("/start" if body["kind"] == "start" else "/answers")
    data = {**body, "approval": preview.json()["approval"]}
    if mismatched:
        bad = client.post(route, headers=headers, json={**data, **mismatched})
        assert bad.status_code == 409, bad.text
    accepted = client.post(route, headers=headers, json=data)
    assert accepted.status_code == 202, accepted.text
    assert client.post(route, headers=headers, json=data).json()["id"] == accepted.json()["id"]
    return accepted.json()


def status(client, headers, path, task):
    response = client.get(f"{path}/tasks/{task['id']}", headers=headers)
    return response.json()


@pytest.mark.parametrize("mode,major,skill,experience", BACKGROUNDS)
def test_interview_modes(client, register_account, bearer_headers, mode, major, skill, experience):
    email, _ = register_account()
    _, resume, job, repo = seed(email, major, skill, experience)
    headers = bearer_headers(email)
    data = {"mode": mode, "resume_content_id": resume, "job_id": job, "repository_id": repo}
    check = client.post(f"{PREFIX}/prepare", headers=headers, json=data)
    assert check.status_code == 200 and check.json()["sources"]["repository"]["commit"] == SHA
    assert check.json()["sources"]["resume"]["content_id"] == resume
    item = create(client, headers, **data)
    path = f"{PREFIX}/sessions/{item['id']}"
    assert client.get(path, headers=bearer_headers()).status_code == 404
    start = enqueue(client, headers, path, {"kind": "start"})
    worker()
    assert status(client, headers, path, start)["state"] == "succeeded"
    first = client.get(path + "/current-question", headers=headers).json()["question"]
    assert first["hint"] is None and first["references"] and "text" not in first["references"][0]
    if mode == "project":
        assert first["references"][0]["path"] == "main.py"
    assert client.get(path, headers=headers).json()["question"]["id"] == first["id"]
    body = {"kind": "answer", "question_id": first["id"], "answer": ANSWER}
    turn = enqueue(client, headers, path, body, mismatched={"answer": "changed"})
    worker()
    assert status(client, headers, path, turn)["state"] == "succeeded"
    active = client.get(path, headers=headers).json()
    assert active["question"]["parent_id"] == first["id"]
    assert active["answered"] == 1 and "score" not in active
    enqueue(client, headers, path, {"kind": "answer", "question_id": active["question"]["id"], "answer": "我会分别验证空输入和格式异常。"})
    worker()
    before = client.post(path + "/finish", headers=headers).json()
    after = client.post(path + "/finish", headers=headers).json()
    assert before == after and after["answered"] == 2 and after["score"] == 75
    assert len(after["turns"][0]["ratings"]) in {11, 12}
    assert after["sources"]["repository"]["commit"] == SHA
    assert client.get(f"{PREFIX}/sessions", headers=headers).json()[0]["id"] == item["id"]
    tasks = client.get(f"{PREFIX}/training-plans", headers=headers).json()["tasks"]
    assert tasks[0]["review_question"] and tasks[0]["acceptance"]
    task_url = f"{PREFIX}/training-tasks/{tasks[0]['id']}"
    assert client.patch(task_url, headers=bearer_headers(), json={"state": "done"}).status_code == 404
    assert client.patch(task_url, headers=headers, json={"state": "done"}).json()["state"] == "done"


def test_timeout_retry_then_timer_finishes(client, register_account, bearer_headers):
    email, _ = register_account()
    seed(email, "设计", "Python", "测试项目")
    headers = bearer_headers(email)
    path = f"{PREFIX}/sessions/{create(client, headers)['id']}"
    task = enqueue(client, headers, path, {"kind": "start"})

    class Timeout(Fake):
        def generate(self, *_):
            raise ApiError(504, "MODEL_TIMEOUT", "测试超时")

    worker(Timeout)
    assert status(client, headers, path, task)["error_code"] == "MODEL_TIMEOUT"
    assert client.post(f"{path}/tasks/{task['id']}/retry", headers=headers).json()["attempt"] == 2
    worker()
    assert status(client, headers, path, task)["state"] == "succeeded"
    with session_factory().begin() as db:
        row = db.get(InterviewSession, int(path.rsplit("/", 1)[1]))
        row.deadline_at = utc_now() - timedelta(seconds=2)
    worker()
    report = client.get(path + "/report", headers=headers).json()
    assert report["finish_reason"] == "time_limit" and report["score"] is None and report["answered"] == 0


def test_fixture_and_rubric_boundaries():
    assert (len(PRODUCT_QUESTIONS), len(PROJECT_PROBES), len(AI_QUESTIONS)) == (20, 10, 10)
    assert len({*PRODUCT_QUESTIONS, *PROJECT_PROBES, *AI_QUESTIONS}) == 40
    assert {item["key"] for item in rules("technical")} != {item["key"] for item in rules("product")}
    model = EvaluationDraft.model_validate({
        "ratings": [{"dimension": "concept", "level": 4, "reason": "术语解释正确", "quote": "不存在的原话"}],
        "corrected_idea": "待复练", "exercise": "比较典型输入", "acceptance": "说明不同结果",
        "contribution_claim": "我负责了整个系统",
    })
    outcome = evaluate("technical", model, "使用 Python")
    assert outcome["score"] is None and outcome["coverage"] == 0 and outcome["contribution_claim"] is None
    model.ratings[0].quote = "使用 Python"
    limited = evaluate("technical", model, "使用 Python")
    assert limited["coverage"] == 12 and limited["score"] is None


def test_missing_resume_and_invalid_schedule(client, bearer_headers):
    headers = bearer_headers()
    assert client.post(PREFIX + "/prepare", headers=headers, json={"mode": "resume"}).status_code == 422
    assert client.post(PREFIX + "/prepare", headers=headers, json={"mode": "combined", "minutes": 10,
                       "stage_minutes": {"technical": 10}}).status_code == 422


def test_combined_moves_across_all_stages_and_holds_source_version(client, register_account, bearer_headers):
    email, _ = register_account()
    _, _, _, repo = seed(email, "计算机", "SQL", "用合成数据做测试")
    headers = bearer_headers(email)
    item = create(client, headers, mode="combined", minutes=7, deep_followup=False)
    path = f"{PREFIX}/sessions/{item['id']}"
    enqueue(client, headers, path, {"kind": "start"})
    worker()
    with session_factory().begin() as db:
        project = db.get(CodeProject, repo)
        project.active_commit = "8" * 40
        db.add(ProjectSnapshot(project_id=repo, commit_sha=project.active_commit, data={}))
    for stage in ("intro", "resume", "project", "product", "technical", "scenario", "reverse"):
        state = client.get(path, headers=headers).json()
        question = state["question"]
        assert question["stage"] == stage and question["parent_id"] is None
        if stage == "project":
            assert question["references"][0]["commit"] == SHA
        enqueue(client, headers, path, {"kind": "answer", "question_id": question["id"], "answer": ANSWER})
        worker()
    report = client.get(path + "/report", headers=headers).json()
    assert report["finish_reason"] == "planned_complete" and report["answered"] == 7
    assert report["unassessed_stages"] == [] and report["sources"]["repository"]["commit"] == SHA


@pytest.mark.skipif(os.getenv("CAREER_LIVE_INTERVIEWS") != "1", reason="Uses public GitHub and synthetic answers with real model")
def test_live_interview(client, register_account, bearer_headers):
    email, _ = register_account()
    seed(email, "合成计算机", "JavaScript", "课上分析过虚构任务")
    headers = bearer_headers(email)
    imported = client.post("/api/v1/code-projects/import", headers=headers, json={"url": PUBLIC_REPO})
    assert imported.status_code == 202, imported.text
    pid = imported.json()["project"]["id"]
    assert run_code_project_once(session_factory(), github_factory=GitHub)
    code_project = client.get(f"/api/v1/code-projects/{pid}", headers=headers).json()
    assert code_project["active_commit"], code_project["tasks"]
    item = create(client, headers, mode="project", repository_id=pid, commit=code_project["active_commit"], deep_followup=True)
    path = f"{PREFIX}/sessions/{item['id']}"
    job = enqueue(client, headers, path, {"kind": "start"})
    worker(Provider)
    actual = status(client, headers, path, job)
    assert actual["state"] == "succeeded", actual
    detail = client.get(path, headers=headers).json()
    assert any(item.get("path") == "index.js" for item in detail["question"]["references"])
    for answer in ("我阅读了公开源码。Node 的构造参数是 value，存到节点的 value 属性；next 初始未设置。入队将新节点链接到尾部并增加计数；空队列的头尾都会指向新节点。出队没有参数，队列空时返回 undefined；否则前移队头并递减计数，变空时清空尾引用，最后返回原队头的数据。",
                   "我没有参与开发，只阅读了公开代码。若队列为空，提前返回 undefined，计数仍为 0；若刚移除最后一个节点，清空尾引用可维持空队列头尾一致。再入队按队头为空的分支重设头尾，计数回到 1。"):
        question = client.get(path, headers=headers).json()["question"]
        if not question:
            break
        job = enqueue(client, headers, path, {"kind": "answer", "question_id": question["id"], "answer": answer})
        worker(Provider)
        actual = status(client, headers, path, job)
        assert actual["state"] == "succeeded", actual
    report = client.post(path + "/finish", headers=headers).json()
    assert report["answered"] >= 1 and report["turns"][0]["references"]
    tasks = client.get(PREFIX + "/training-plans", headers=headers).json()
    directory = os.getenv("CAREER_INTERVIEW_REPORT_DIR")
    if directory:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        (out / "live-interview.json").write_text(json.dumps({"report": report, "training": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.skipif(os.getenv("CAREER_LIVE_INTERVIEW_CALIBRATION") != "1", reason="Uses synthetic answers with real model")
def test_live_rubric_calibration():
    from app.ai.interview_prompts import TURN
    from app.core.config import get_settings
    from app.services.interview_evaluation_service import ANCHORS

    prompt = "如果模型返回不符合 JSON Schema 的结果，应该如何处理？"
    answers = {
        "concise_correct": "先做 JSON 解析和 Schema 校验；失败时最多重试一次，仍失败返回明确错误并记录错误类型。",
        "jargon_only": "我们赋能智能生态，使用 RAG、Embedding、Agent、多模态、闭环、低延迟、大模型和高可用。",
        "technical_error": "模型的 HTTP 状态为 200 就证明内容符合 JSON Schema，可以跳过本地校验直接写进数据库。",
        "missing_evidence": "我暂时不知道该如何处理。",
    }
    provider = Provider(get_settings())
    try:
        results = {}
        for name, answer in answers.items():
            result = provider.generate(TURN, {"target": "AI 产品经理", "mode": "technical", "stage": "technical",
                "next_stage": None, "current_question": prompt, "knowledge_point": "结构化输出",
                "answer": answer, "rubric": rules("technical"), "anchors": ANCHORS, "sources": []}, EvaluationDraft)
            results[name] = {"answer": answer, "model_ratings": [row.model_dump() for row in result.ratings],
                             **evaluate("technical", result, answer)}
    finally:
        provider.close()
    directory = os.getenv("CAREER_INTERVIEW_REPORT_DIR")
    if directory:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        (out / "rubric-calibration.json").write_text(json.dumps({"question": prompt, "results": results},
                                                                ensure_ascii=False, indent=2), encoding="utf-8")
    assert results["concise_correct"]["score"] is not None
    for kind in ("jargon_only", "technical_error"):
        bad = results[kind]["score"]
        assert bad is None or results["concise_correct"]["score"] > bad
