import io
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import session_factory
from app.models.career import CareerAnalysis, SkillEvidence, SkillProfile
from app.models.job import JobAnalysisTask, JobMatch
from app.models.resume import Resume, ResumeContent
from app.models.user import User
from app.services.job_matching_service import score
from app.services.job_workflow import run_job_once
from job_cases import CASES, PREFERRED, SQL

API = "/api/v1"
JD = "星河科技招聘 AI 产品实习生。负责用户访谈。必须掌握 SQL。了解 Python 者优先。"

@pytest.mark.parametrize("case", CASES, ids=lambda case: case[0])
def test_scoring(case):
    _, requirements, person, assessments, expected = case
    result = score(requirements, person, assessments)
    assert (result["overall_score"], result["evidence_coverage"]) == expected
    if case[0] == "03-inferred":
        assert result["hard_flags"][0]["evidence_status"] == "inferred"
    if case[0] == "06-year-conflict":
        assert result["hard_flags"][0]["status"] == "unmet"
        assert result["verdict"] == "当前匹配较低，建议先补足关键能力"

def test_explicit_highest_degree_conflict_and_missing_qualification():
    requirement = {"name":"硕士学历","category":"education","importance":"required","kind":"degree","quote":"硕士及以上"}
    known = score([requirement], {"education":["最高学历：本科"]}, {})
    unknown = score([requirement], {"education":["本科"]}, {})
    assert known["hard_flags"][0]["status"] == "unmet"
    assert unknown["overall_score"] is None

def seed_candidate(email):
    with session_factory().begin() as db:
        owner = db.scalar(select(User).where(User.email == email))
        resume = Resume(user_id=owner.id, original_filename="合成简历.pdf", storage_key=uuid4().hex,
                        file_type="pdf", file_size=1, parse_status="parsed")
        db.add(resume)
        db.flush()
        content = ResumeContent(resume_id=resume.id, version=1, parser_version="test", extracted_text="熟悉 SQL",
                                blocks=[], structured_data={}, confirmed=True)
        db.add(content)
        db.flush()
        analysis = CareerAnalysis(user_id=owner.id, content_id=content.id, target_direction="产品经理",
                                  analysis_result={}, model_name="fixture", prompt_version="fixture")
        db.add(analysis)
        db.flush()
        skill = SkillProfile(analysis_id=analysis.id, skill_name="SQL", skill_category="数据", proficiency_level="基础",
                             evidence_status="verified", analysis_reason="合成测验")
        db.add(skill)
        db.flush()
        db.add(SkillEvidence(skill_profile_id=skill.id, source_type="test", block_number=1, source_content="合成 SQL 测验已通过"))
        return content.id

class FakeProvider:
    def __init__(self, settings):
        pass
    def generate(self, prompt, payload, output):
        if prompt.name == "job_description":
            return output.model_validate({"company_name":"星河科技","location":"不存在",
                "duties":["负责用户访谈","编造职责"],"requirements":[SQL,{**PREFERRED, "importance":"required"}]})
        assert "合成 SQL 测验已通过" not in str(payload)
        return output.model_validate({"rationale":"按现有证据准备","resume_focus":[],"interview_focus":["说明查询口径"],"projects":[],"next_steps":["准备 SQL 示例"]})
    def close(self):
        pass

class FailingProvider(FakeProvider):
    def generate(self, *args):
        raise ApiError(504, "MODEL_TIMEOUT", "超时")

def test_job_lifecycle(client, register_account, bearer_headers, monkeypatch):
    from pydantic import SecretStr
    settings = get_settings()
    monkeypatch.setattr(settings,"llm_base_url","http://127.0.0.1:9909")
    monkeypatch.setattr(settings,"llm_model","test")
    monkeypatch.setattr(settings,"llm_api_key",SecretStr("test"))
    email, _ = register_account()
    own, other = bearer_headers(email), bearer_headers()
    content = seed_candidate(email)
    imported = client.post(f"{API}/jobs/import", files={"file": ("job.txt", io.BytesIO(JD.encode()))}, headers=own)
    assert imported.json()["job_description"] == JD
    assert client.get(f"{API}/jobs").status_code == 401
    created = client.post(f"{API}/jobs", json={"position_name":"AI 产品实习生","job_description":JD}, headers=own)
    assert created.status_code == 201, created.text
    url = f"{API}/jobs/{created.json()['id']}"
    assert client.get(url, headers=other).status_code == 404
    assert client.get(f"{API}/jobs", headers=other).json() == []
    options = {"provider_host":"127.0.0.1","accept_external_processing":True}
    assert client.post(url + "/parse", json={**options,"accept_external_processing":False}, headers=own).status_code == 422
    task = client.post(url + "/parse", json=options, headers=own).json()
    assert client.delete(url, headers=own).status_code == 409
    assert client.post(url + "/parse", json=options, headers=own).json()["id"] == task["id"]
    assert run_job_once(session_factory(), FailingProvider)
    task_url = f"{API}/job-analysis-tasks/{task['id']}"
    assert client.get(task_url, headers=own).json()["error_code"] == "MODEL_TIMEOUT"
    assert client.get(task_url, headers=other).status_code == 404
    attempted = client.post(url + "/parse", headers=own, json={**options,"retry":True})
    assert attempted.json()["attempt"] == 2
    assert run_job_once(session_factory(), FakeProvider)
    detail = client.get(url, headers=own).json()
    assert detail["parsed"]["company_name"] == "星河科技"
    assert detail["parsed"]["location"] is None
    assert detail["parsed"]["duties"] == ["负责用户访谈"]
    assert [row["importance"] for row in detail["requirements"]] == ["required","preferred"]
    saved = client.put(url + "/requirements", headers=own, json={"revision":detail["revision"],"requirements":detail["requirements"]}).json()
    request = {"content_id":content,"revision":saved["revision"]}
    matched = client.post(url + "/match", headers=own, json=request)
    assert matched.status_code == 200, matched.text
    match = matched.json()
    assert match["overall_score"] == 100
    assert client.post(url + "/match", headers=own, json=request).json()["id"] == match["id"]
    assert client.get(f"{API}/job-matches", headers=own).json()[0]["id"] == match["id"]
    match_url = f"{API}/job-matches/{match['id']}"
    assert client.get(match_url + "/gaps", headers=other).status_code == 404
    gap, = client.get(match_url + "/gaps", headers=own).json()
    assert (gap["priority"], gap["estimated_cost"]) == ("中", "低")
    assert client.post(match_url + "/recommendations", headers=own, json=options).status_code == 202
    assert run_job_once(session_factory(), FakeProvider)
    assert client.get(url + "/match", headers=own).json()["recommendations"]["interview_focus"]
    assert client.delete(url, headers=own).status_code == 204
    with session_factory()() as db:
        assert db.get(JobMatch, match["id"]) is None and db.get(JobAnalysisTask, task["id"]) is None
