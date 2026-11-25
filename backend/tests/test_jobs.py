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
from app.services.job_availability import resume_weekly_availability
from app.services.job_matching_service import confirmed_practice, score
from app.services.job_workflow import run_job_once
from job_cases import CASES, PREFERRED, SQL, requirement

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


def test_same_resume_produces_distinct_grounded_evidence_for_each_jd():
    sql = "用 SQL 核对出库前后的库存流水"
    prd = "参与需求拆解并撰写产品需求文档"
    exclusions = ["计划开展用户访谈", "尚未使用 RAG", "使用 NoSQL 验证原型"]
    blocks = [{"number": index, "text": line} for index, line in enumerate([sql, prd, *exclusions], 1)]
    facts = {"projects": [
        {"original": block["text"], "source": {"block_number": block["number"], "quote": block["text"]}}
        for block in blocks
    ]}
    facts["projects"].append({"original": "使用 RAG 搭建系统", "source": {"block_number": 1, "quote": "使用 RAG 搭建系统"}})
    person = {"practice": confirmed_practice(facts, blocks)}
    data = score([SQL, requirement("RAG", "ai")], person, {})
    product = score([requirement("PRD", "product", kind="experience"), requirement("用户研究", "product")], person, {})
    for report, quote, block_number in [(data, sql, 1), (product, prd, 2)]:
        related, missing = report["requirements"]
        assert (related["status"], related["evidence_status"]) == ("partial", "inferred")
        assert related["sources"] == [{"block_number": block_number, "quote": quote}]
        assert missing["status"] == "pending_not_provided"
        assert report["hard_flags"][0] == related
    assert score([SQL], {"practice": person["practice"][4:]}, {})["overall_score"] is None
    assert score([SQL], person, {0: "not_capable"})["requirements"][0]["status"] == "unmet"


def test_compound_jd_identifies_missing_deliverables_despite_prd_evidence():
    quote = "负责撰写产品需求文档并设计原型"
    evidence = {"block_number": 2, "quote": "参与撰写产品需求文档"}
    must = requirement("PRD", "product", quote=quote)
    person = {"practice": [evidence], "skills": {"prd": {"status": "self_reported", "level": "自述", "sources": [evidence]}}}
    row, = score([must], person, {})["requirements"]
    assert row["status"] == "partial"
    assert row["checks"] == [{"name": "PRD", "sources": [evidence]}, {"name": "原型设计", "sources": []}]
    assert "原型设计" in row["interpretation"]
    alternate, = score([{**must, "quote": "负责撰写产品需求文档或设计原型"}], person, {})["requirements"]
    assert alternate["status"] == "matched" and not alternate["checks"]


def test_matching_uses_ai_major_and_confirmed_work_as_contextual_evidence():
    text = "负责组建数据与算法团队。搭建 RAG 检索流水线。推动应用上线。"
    education = "人工智能专业，工学学士"
    blocks = [{"number": 1, "text": text}, {"number": 2, "text": education}]
    facts = {"other_experiences": [{"original": text, "source": {"block_number": 1, "quote": text}}]}
    person = {
        "practice": confirmed_practice(facts, blocks),
        "academic_evidence": [{"block_number": 2, "quote": education}],
        "education": [education],
    }
    requirements = [
        requirement("对AI的热情", "ai", quote="对AI有足够的热情"),
        requirement("团队协作精神", "communication"),
        requirement("交付意识", "practice"),
        requirement("适应快节奏工作方式", "practice"),
        requirement("掌握微调 LLM", "ai"),
        requirement("本科及以上学历在读", "education", kind="degree", quote="本科及以上学历在读"),
    ]
    report = score(requirements, person, {})
    ai, collaboration, delivery, pace, fine_tuning, enrollment = report["requirements"]
    assert (ai["status"], ai["evidence_status"]) == ("partial", "inferred")
    assert [source["block_number"] for source in ai["sources"]] == [1, 2]
    assert collaboration["status"] == delivery["status"] == "partial"
    assert pace["status"] == "pending_interview" and not pace["sources"]
    assert fine_tuning["status"] == "pending_not_provided"
    assert enrollment["status"] == "pending_no_evidence"
    enrolled = score([requirements[-1]], {**person, "education": ["人工智能本科在读"]}, {})["requirements"][0]
    assert enrolled["status"] == "matched"
    manual = score([requirements[0]], person, {0: "no_evidence"})["requirements"][0]
    assert manual["status"] == "pending_no_evidence" and not manual["sources"]


def test_ai_major_alone_does_not_prove_specific_technical_practice():
    study = {"block_number": 1, "quote": "人工智能专业，工学学士"}
    person = {"academic_evidence": [study]}
    requirements = [requirement("对AI的热情", "ai"), requirement("熟练部署 RAG", "ai")]
    ai, specific = score(requirements, person, {})["requirements"]
    assert ai["status"] == "partial" and ai["sources"] == [study]
    assert specific["status"] == "pending_not_provided"


@pytest.mark.parametrize(("jd", "status"), [
    ("每周至少实习4天以上", "matched"),
    ("每周需到岗七天", "unmet"),
    ("每周至少实习四天且连续实习三个月", "partial"),
    ("每周最多到岗四天", "pending_not_provided"),
    ("每周实习4天或5天", "pending_no_evidence"),
])
def test_weekly_internship_availability_reads_reviewed_resume_header(jd, status):
    blocks = [{"number": 1, "text": "[已脱敏]\n一周可实习6天 | AI 产品经理实习生"}]
    person = {"weekly_availability": resume_weekly_availability(blocks)}
    entry = requirement("每周到岗天数", "practice", kind="availability", quote=jd)
    row, = score([entry], person, {})["requirements"]
    assert row["status"] == status
    if status in {"matched", "unmet", "partial"}:
        assert row["sources"] == [{"block_number": 1, "quote": "一周可实习6天"}]
        assert row["evidence_status"] == "self_reported"


def test_weekly_availability_does_not_reuse_past_experience_or_pick_conflicting_days():
    reviewed = [{"number": 1, "text": "上一段实习每周实习6天。计划每周可到岗六天。"}]
    assert not resume_weekly_availability(reviewed)
    entry = requirement("每周到岗天数", "practice", kind="availability", quote="每周至少到岗4天")
    reviewed = [{"number": 1, "text": "每周可实习6天\n每周可实习2天"}]
    row, = score([entry], {"weekly_availability": resume_weekly_availability(reviewed)}, {})["requirements"]
    assert row["status"] == "pending_no_evidence"

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


class InvalidAdviceProvider(FakeProvider):
    def __init__(self, settings):
        self.calls = 0

    def generate(self, prompt, payload, output):
        self.calls += 1
        assert prompt.version == "job-advice-2"
        raise ApiError(502, "MODEL_OUTPUT_INVALID", "格式不符合要求")


class RecoveringAdviceProvider(InvalidAdviceProvider):
    def generate(self, prompt, payload, output):
        if not self.calls:
            return super().generate(prompt, payload, output)
        self.calls += 1
        return FakeProvider.generate(self, prompt, payload, output)


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
    assert match["resume"]["original_filename"] == "合成简历.pdf"
    assert match["resume"]["version"] == 1 and match["resume"]["content_id"] == content
    assert client.get(f"{API}/resumes/{match['resume']['resume_id']}/content",
                      params={"content_id": content}, headers=other).status_code == 404
    assert client.post(url + "/match", headers=own, json=request).json()["id"] == match["id"]
    assert client.get(f"{API}/job-matches", headers=own).json()[0]["id"] == match["id"]
    match_url = f"{API}/job-matches/{match['id']}"
    assert client.get(match_url + "/gaps", headers=other).status_code == 404
    gap, = client.get(match_url + "/gaps", headers=own).json()
    assert (gap["priority"], gap["estimated_cost"]) == ("中", "低")
    advice = client.post(match_url + "/recommendations", headers=own, json=options)
    assert advice.status_code == 202
    advice_id = advice.json()["id"]
    invalid = InvalidAdviceProvider(settings)
    assert run_job_once(session_factory(), lambda _: invalid)
    assert invalid.calls == 2
    fallback = client.get(match_url, headers=own).json()["recommendations"]
    assert fallback["generation_method"] == "local_fallback"
    assert any("Python" in step for step in fallback["next_steps"])
    assert client.get(f"{API}/job-analysis-tasks/{advice_id}", headers=own).json()["error_code"] == "MODEL_OUTPUT_INVALID"
    manual_retry = client.post(match_url + "/recommendations", headers=own, json={**options,"retry":True})
    assert manual_retry.json()["id"] == advice_id and manual_retry.json()["attempt"] == 2
    recovering = RecoveringAdviceProvider(settings)
    assert run_job_once(session_factory(), lambda _: recovering)
    assert recovering.calls == 2
    actual = client.get(match_url, headers=own).json()["recommendations"]
    assert actual["interview_focus"] and "generation_method" not in actual
    assert client.delete(url, headers=own).status_code == 204
    with session_factory()() as db:
        assert db.get(JobMatch, match["id"]) is None and db.get(JobAnalysisTask, task["id"]) is None
