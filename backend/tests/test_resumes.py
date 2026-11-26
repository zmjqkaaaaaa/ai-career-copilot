from datetime import date
from io import BytesIO
import subprocess
import sys
from types import SimpleNamespace

import pytest
from docx import Document
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from app.ai.evidence import redact_blocks, validate_analysis, validate_extraction
from app.ai.prompts import EXTRACT
from app.ai.provider import Provider
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import session_factory
from app.models.resume import Resume
from app.resume_worker import run_once
from app.schemas.career import CareerResult, StructuredResume
from app.services.job_matching_service import candidate, score
from app.services.resume_parser import MAX_FILE_BYTES, parse_resume
from job_cases import requirement
from resume_fixtures import cases, write_case

RESUMES = "/api/v1/resumes"
CONSENT = {"accept_external_processing": True, "provider_host": "127.0.0.1"}

def test_worker_import_registers_foreign_keys_without_loading_api():
    completed = subprocess.run(
        [sys.executable, "-c", "import app.resume_worker; from app.db.base import Base; print(len(Base.metadata.sorted_tables))"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert int(completed.stdout.strip()) >= 8

@pytest.fixture
def workspace(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "resume_storage_dir", tmp_path / "private")
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:9876/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test-placeholder"))
    return tmp_path

@pytest.mark.parametrize("case", cases(), ids=lambda case: case["id"])
def test_parse_ten_synthetic_resumes(case, tmp_path):
    blocks = parse_resume(write_case(case, tmp_path), case["format"])
    assert [block["number"] for block in blocks] == list(range(1, len(blocks) + 1))
    assert case["education"] in " ".join(block["text"] for block in blocks)
    desensitized = redact_blocks(blocks)
    text = " ".join(block["text"] for block in desensitized)
    assert "candidate@example.com" not in text
    for field in ("projects", "skills", "internships"):
        assert all(value in text for value in case[field])


def test_pdf_recovers_adobe_gb1_text_without_tounicode(tmp_path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    cid_system = DictionaryObject({
        NameObject("/Registry"): TextStringObject("Adobe"),
        NameObject("/Ordering"): TextStringObject("GB1"),
        NameObject("/Supplement"): NumberObject(5),
    })
    font = DictionaryObject({
        NameObject("/Subtype"): NameObject("/Type0"),
        NameObject("/Encoding"): NameObject("/Identity-H"),
        NameObject("/DescendantFonts"): ArrayObject([DictionaryObject({NameObject("/CIDSystemInfo"): cid_system})]),
    })
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 40 780 Td <06fd125408dc09e5> Tj 0 -20 Td <0ff9063f0f4d07310f220e64> Tj ET")
    page[NameObject("/Contents")] = stream
    path = tmp_path / "gb1.pdf"
    writer.write(path)

    assert "工作经历" not in PdfReader(path).pages[0].extract_text()
    blocks = parse_resume(path, "pdf")
    assert [block["text"] for block in blocks] == ["工作经历", "研发相关系统"]
    assert blocks[1]["section"] == "other_experiences"


def test_docx_preserves_project_bullets_inside_nested_tables(tmp_path):
    path = tmp_path / "nested.docx"
    document = Document()
    document.add_paragraph("项目经历")
    cell = document.add_table(rows=1, cols=1).cell(0, 0)
    cell.paragraphs[0].text = "求职成长助手"
    cell.add_table(rows=1, cols=1).cell(0, 0).text = "参与需求拆解并交付产品需求文档"
    cell.add_paragraph("使用 SQL 核对投递记录")
    document.add_paragraph("第二个项目：库存看板")
    document.save(path)
    content = [block["text"] for block in parse_resume(path, "docx")]
    assert content == ["项目经历", "求职成长助手\n参与需求拆解并交付产品需求文档\n使用 SQL 核对投递记录", "第二个项目：库存看板"]


def test_local_resume_draft_preserves_experiences_and_ownership(client, bearer_headers, workspace):
    year = date.today().year
    document = Document()
    for paragraph in (
        "教育经历", f"合成大学　硕士　信息工程　{year - 1}-{year + 2}",
        "实习经历", "模拟公司 产品实习 2025.01-2025.04", "负责需求梳理并输出两份报告", "跟踪异常案例",
        "第二公司 数据实习 2025.05-2025.08", "使用 SQL 验证库存",
        "项目经历", "库存看板 2025.01-2025.06", "制作原型", "技能能力", "SQL",
    ):
        document.add_paragraph(paragraph)
    stream = BytesIO()
    document.save(stream)
    headers = bearer_headers()
    created = client.post(f"{RESUMES}/upload", headers=headers, files={"file": ("sample.docx", stream.getvalue())})
    base = f"{RESUMES}/{created.json()['id']}"
    assert client.post(base + "/parse", headers=headers).status_code == 202
    assert run_once(local_only=True)
    parsed = client.get(base + "/content", headers=headers).json()
    blocks = parsed["blocks"]
    internship = next(block for block in blocks if block["section"] == "internships")
    assert internship["text"].splitlines()[-2:] == ["负责需求梳理并输出两份报告", "跟踪异常案例"]
    wrong_group = StructuredResume.model_validate({"projects": [
        {"original": "跟踪异常案例", "source": {"block_number": internship["number"], "quote": "跟踪异常案例"}}
    ]})
    corrected, rejected = validate_extraction(wrong_group, blocks)
    assert rejected == 0
    assert len(corrected.internships) == 2 and len(corrected.projects) == 1
    assert corrected.internships[0].original == internship["text"]

    data = {"content_id": parsed["id"], "hidden_blocks": [internship["number"]]}
    assert client.post(base + "/local-draft", headers=bearer_headers(), json=data).status_code == 404
    local = client.post(base + "/local-draft", headers=headers, json=data)
    assert local.status_code == 201, local.text
    draft = local.json()
    assert draft["metadata_json"]["method"] == "local_sections" and not draft["confirmed"]
    assert len(draft["structured_data"]["internships"]) == 1
    assert len(draft["structured_data"]["projects"]) == 1
    assert all(block["number"] != internship["number"] for block in draft["model_blocks"])
    draft_api = "/api/v1/profiles/me/resume-draft"
    assert client.get(draft_api, headers=headers).json() is None
    confirmed = client.put(base + "/content", headers=headers, json={"content_id": draft["id"], "structured_data": draft["structured_data"]})
    assert confirmed.status_code == 200 and confirmed.json()["confirmed"]
    prefill = client.get(draft_api, headers=headers)
    assert prefill.status_code == 200, prefill.text
    fields = prefill.json()["fields"]
    assert prefill.json()["content_id"] == confirmed.json()["id"]
    assert fields["graduate_school"] == "合成大学" and fields["graduate_major"] == "信息工程"
    assert fields["graduation_year"] == year + 2 and fields["skills"] == ["SQL"]
    assert fields["project_experience"][0]["title"].startswith("库存看板")
    assert len(fields["internship_experience"]) == 1
    assert client.get(draft_api, headers=bearer_headers()).json() is None
    assert client.get("/api/v1/profiles/me", headers=headers).status_code == 404
    assert client.delete(base, headers=headers).status_code == 204


def test_career_analysis_recovers_practice_omitted_by_the_model():
    blocks = [{"number": 1, "location": "第 1 页", "section": "projects",
               "text": "设计 Prompt V1-V3 并测试结构化输出。计划使用 SQL 核对库存。"}]
    draft = CareerResult.model_validate({"summary": {"title": "合成材料", "reason": "模型未返回能力项"}})
    skills = {item.name: item for item in validate_analysis(draft, blocks).skills}
    assert skills["Prompt Engineering"].status == "resume_supported"
    assert skills["Prompt Engineering"].sources[0].block_number == 1
    assert skills["SQL"].status == "unknown"

@pytest.mark.parametrize("file_type", ["pdf", "docx"])
def test_design_portfolio_becomes_traceable_job_evidence(client, bearer_headers, workspace, file_type):
    contribution = "个人贡献：负责用户访谈并梳理需求"
    process = "设计过程：绘制交互原型并组织可用性测试"
    proposed = "计划使用 SQL 核对留存数据"
    cover = ["设计作品集", "案例一：仓库管理原型", contribution]
    continuation = [process, proposed, "关于我", "使用 Figma"]
    stream = BytesIO()
    if file_type == "pdf":
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        pdf = canvas.Canvas(stream)
        for page in (cover, continuation):
            pdf.setFont("STSong-Light", 14)
            for index, line in enumerate(page):
                pdf.drawString(50, 790 - 25 * index, line)
            pdf.showPage()
        pdf.save()
    else:
        document = Document()
        for line in [*cover[1:], *continuation]:
            document.add_paragraph(line)
        document.save(stream)

    headers = bearer_headers()
    name = "设计材料.pdf" if file_type == "pdf" else "交互设计作品集.docx"
    created = client.post(f"{RESUMES}/upload", headers=headers, files={"file": (name, stream.getvalue())})
    assert created.status_code == 201, created.text
    resume_id = created.json()["id"]
    base = f"{RESUMES}/{resume_id}"
    assert client.post(base + "/parse", headers=headers).status_code == 202
    assert run_once(local_only=True)
    parsed = client.get(base + "/content", headers=headers).json()
    project_blocks = [block for block in parsed["blocks"] if block["section"] == "projects"]
    process_block = next(block for block in project_blocks if process in block["text"])
    assert any(contribution in block["text"] for block in project_blocks)
    if file_type == "pdf":
        assert process_block["location"] == "第 2 页"
    assert all("使用 Figma" not in block["text"] for block in project_blocks)
    draft = client.post(base + "/local-draft", headers=headers, json={"content_id": parsed["id"], "hidden_blocks": []})
    assert draft.status_code == 201, draft.text
    confirmed = client.put(base + "/content", headers=headers, json={
        "content_id": draft.json()["id"], "structured_data": draft.json()["structured_data"],
    })
    assert confirmed.status_code == 200, confirmed.text
    with session_factory()() as db:
        person = candidate(db, db.get(Resume, resume_id).user_id, confirmed.json()["id"], None)
        result = score([requirement("用户研究", "product"), requirement("原型设计", "product"),
                        requirement("SQL", "data")], person, {})
    research, prototype, sql = result["requirements"]
    assert contribution in research["sources"][0]["quote"]
    assert prototype["sources"][0]["block_number"] == process_block["number"]
    assert sql["status"] == "pending_not_provided" and not sql["sources"]


def test_upload_validation_and_empty_pdf(client, bearer_headers, workspace):
    headers = bearer_headers()
    for filename, data, status in (
        ("unsupported.zip", b"ZIP", 415),
        ("fake.pdf", b"not pdf", 415),
        ("fake.docx", b"PK\x03\x04broken", 422),
        ("oversize.pdf", b"%PDF-" + b"x" * MAX_FILE_BYTES, 413),
    ):
        assert client.post(f"{RESUMES}/upload", headers=headers, files={"file": (filename, data)}).status_code == status
    assert list((workspace / "private").iterdir()) == []
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(stream)
    result = client.post(f"{RESUMES}/upload", headers=headers, files={"file": ("empty.pdf", stream.getvalue())})
    assert result.status_code == 201
    base = f"{RESUMES}/{result.json()['id']}"
    job = client.post(f"{base}/parse", headers=headers).json()
    assert job["scheduled_at"] and job["started_at"] is None
    assert not run_once(local_only=False)
    assert run_once(local_only=True)
    progress = client.get(f"/api/v1/resume-jobs/{job['id']}", headers=headers)
    assert progress.json()["state"] == "failed" and progress.json()["error_code"] == "NO_RESUME_TEXT"
    assert progress.json()["finished_at"]
    assert client.delete(base, headers=headers).status_code == 204

class SyntheticProvider:
    def __init__(self, _settings):
        pass

    def close(self):
        pass

    def generate(self, prompt, payload, output):
        blocks = payload["blocks"]
        assert all("candidate@example.com" not in block["text"] for block in blocks)
        study = next(block for block in blocks if "虚构南岸学院" in block["text"])
        sql = next(block for block in blocks if "SQL" in block["text"])
        project = next(block for block in blocks if "库存看板原型" in block["text"])
        education = {"block_number": study["number"], "quote": "虚构南岸学院｜国际贸易本科"}
        skill = {"block_number": sql["number"], "quote": "SQL"}
        origin = {"block_number": project["number"], "quote": "库存看板原型"}
        if prompt.name == "resume_extraction":
            return output.model_validate({
                "education": [{"original": education["quote"], "source": education}],
                "skills": [{"original": "SQL", "source": skill},
                           {"original": "Python", "source": {"block_number": sql["number"], "quote": "Python"}}],
                "projects": [{"original": origin["quote"], "source": origin}],
            })
        if prompt.name == "career_analysis":
            return output.model_validate({
                "summary": {"title": "商科与库存项目", "reason": "简历写到了商科和课堂项目。", "sources": [education]},
                "skills": [
                    {"name": "SQL", "level": "基础", "status": "self_reported", "reason": "简历技能清单自述", "sources": [skill]},
                    {"name": "Python", "level": "有实践迹象", "status": "verified", "reason": "无外部测验证据", "sources": [skill]},
                ],
            })
        return output.model_validate({"suggestions": [
            {"section": "内容", "original": origin, "rewritten": "独立主导库存看板，提高销量30%",
             "reason": "强调效果", "interview_question": "如何测得效果？", "needs_evidence": False}
        ]})

def create_parsed(client, headers, workspace):
    path = write_case(cases()[1], workspace)
    uploaded = client.post(f"{RESUMES}/upload", headers=headers, files={"file": (path.name, path.read_bytes())})
    assert uploaded.status_code == 201, uploaded.text
    base = f"{RESUMES}/{uploaded.json()['id']}"
    first = client.post(f"{base}/parse", headers=headers)
    assert first.status_code == 202
    key = first.json()["id"]
    assert client.post(f"{base}/parse", headers=headers).json()["id"] == key
    assert client.delete(base, headers=headers).status_code == 409
    assert run_once(provider_factory=SyntheticProvider)
    content = client.get(f"{base}/content", headers=headers).json()
    assert content["version"] == 1
    return base, uploaded.json()["id"], content, key

def test_resume_ai_workflow_and_isolation(client, bearer_headers, workspace):
    own, other = bearer_headers(), bearer_headers()
    base, resume_id, parsed, parse_job = create_parsed(client, own, workspace)
    assert client.get(f"{base}/content", headers=other).status_code == 404
    assert client.get(f"/api/v1/resume-jobs/{parse_job}", headers=other).status_code == 404
    assert client.get(RESUMES, headers=other).json() == []
    assert client.delete(base, headers=other).status_code == 404
    assert client.get(RESUMES).status_code == 401
    preview = client.get(f"{base}/preview", headers=own, params={"content_id": parsed["id"]})
    assert "candidate@example.com" not in preview.text
    assert client.post(f"{base}/extract", headers=own, json={"content_id": parsed["id"]}).status_code == 422
    assert client.post(f"{base}/extract", headers=own, json={
        "content_id": parsed["id"], **CONSENT, "provider_host": "wrong.example",
    }).status_code == 409
    extract = client.post(f"{base}/extract", headers=own, json={
        "content_id": parsed["id"], "hidden_blocks": [1], **CONSENT,
    })
    assert extract.status_code == 202, extract.text
    assert run_once(provider_factory=SyntheticProvider)
    draft = client.get(f"{base}/content", headers=own).json()
    assert draft["metadata_json"]["rejected"] == 1 and draft["structured_data"]["skills"][0]["original"] == "SQL"
    assert draft["metadata_json"]["prompt_version"] == "extract-2"
    assert all(block["number"] != 1 for block in draft["model_blocks"])
    confirmed = client.put(f"{base}/content", headers=own,
                           json={"content_id": draft["id"], "structured_data": draft["structured_data"]})
    assert confirmed.status_code == 200, confirmed.text
    confirmed_id = confirmed.json()["id"]
    body = {"resume_id": resume_id, "content_id": confirmed_id, "target_direction": "AI 产品经理", **CONSENT}
    analyze = client.post("/api/v1/career/analyze", headers=own, json=body)
    assert analyze.status_code == 202
    assert run_once(provider_factory=SyntheticProvider)
    assert client.post("/api/v1/career/analyze", headers=own, json=body).json()["id"] == analyze.json()["id"]
    history = client.get("/api/v1/career/analyses", headers=own).json()
    assert len(history) == 1
    profile = client.get("/api/v1/career/profile", headers=own).json()
    assert client.get("/api/v1/career/profile", headers=other, params={"analysis_id": history[0]["id"]}).status_code == 404
    skills = {skill["name"]: skill for skill in profile["report"]["skills"]}
    assert skills["SQL"]["status"] == "self_reported" and skills["SQL"]["sources"]
    assert skills["Python"]["status"] == "unknown" and not skills["Python"]["sources"]
    optimization = client.post(f"{base}/optimize", headers=own, json={
        "content_id": confirmed_id, "target_direction": "AI 产品经理", **CONSENT,
    })
    assert optimization.status_code == 202, optimization.text
    assert run_once(provider_factory=SyntheticProvider)
    records = client.get(f"{base}/optimizations", headers=own).json()
    assert records[0]["needs_evidence"] and "30%" not in records[0]["optimized_content"]
    item = f"{base}/optimizations/{records[0]['id']}/confirm"
    assert client.post(item, headers=other, json={"text": "别人的修改"}).status_code == 404
    assert client.post(item, headers=own, json={"text": "库存看板模拟原型"}).json()["confirmed_text"] == "库存看板模拟原型"
    assert client.get(f"{base}/content", headers=own).json()["id"] == confirmed_id
    assert client.delete(base, headers=own).status_code == 204
    assert client.get("/api/v1/career/analyses", headers=own).json() == []
    assert not list((workspace / "private").iterdir())

def test_model_failure_requires_explicit_retry(client, bearer_headers, workspace):
    headers = bearer_headers()
    base, _, content, _ = create_parsed(client, headers, workspace)
    class Unavailable(SyntheticProvider):
        def generate(self, *_arguments):
            raise ApiError(504, "MODEL_TIMEOUT", "simulated timeout")
    body = {"content_id": content["id"], **CONSENT}
    job = client.post(f"{base}/extract", headers=headers, json=body).json()
    assert run_once(provider_factory=Unavailable)
    same = client.post(f"{base}/extract", headers=headers, json=body).json()
    assert same["error_code"] == "MODEL_TIMEOUT" and same["attempt"] == 1
    retried = client.post(f"{base}/extract", headers=headers, json={**body, "retry": True}).json()
    assert retried["id"] == job["id"] and retried["attempt"] == 2
    assert run_once(provider_factory=SyntheticProvider)
    assert client.get(f"{base}/content", headers=headers).json()["structured_data"] is not None
    assert client.delete(base, headers=headers).status_code == 204

def test_provider_rejects_malformed_response(monkeypatch, workspace, caplog):
    provider = Provider(get_settings())
    choices = [SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"skills":42}'))]
    usage = SimpleNamespace(prompt_tokens=23, completion_tokens=7)
    monkeypatch.setattr(provider.client.chat.completions, "create", lambda **_: SimpleNamespace(choices=choices, usage=usage))
    try:
        with caplog.at_level("INFO", logger="app.ai.provider"), pytest.raises(ApiError) as error:
            provider.generate(EXTRACT, {"blocks": [{"text": "private-fixture-text"}]}, StructuredResume)
        assert error.value.code == "MODEL_OUTPUT_INVALID"
        assert "status=MODEL_OUTPUT_INVALID" in caplog.text
        assert "input_tokens=23 output_tokens=7" in caplog.text
        assert "private-fixture-text" not in caplog.text
        assert "test-placeholder" not in caplog.text
    finally:
        provider.close()
