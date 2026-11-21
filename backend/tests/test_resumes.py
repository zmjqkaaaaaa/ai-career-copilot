from io import BytesIO
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from app.ai.evidence import redact_blocks
from app.ai.prompts import EXTRACT
from app.ai.provider import Provider
from app.core.config import get_settings
from app.core.errors import ApiError
from app.resume_worker import run_once
from app.schemas.career import StructuredResume
from app.services.resume_parser import MAX_FILE_BYTES, parse_resume
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
    assert run_once()
    progress = client.get(f"/api/v1/resume-jobs/{job['id']}", headers=headers)
    assert progress.json()["state"] == "failed" and progress.json()["error_code"] == "NO_RESUME_TEXT"
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

def test_provider_rejects_malformed_response(monkeypatch, workspace):
    provider = Provider(get_settings())
    choices = [SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"skills":42}'))]
    monkeypatch.setattr(provider.client.chat.completions, "create", lambda **_: SimpleNamespace(choices=choices, usage=None))
    try:
        with pytest.raises(ApiError) as error:
            provider.generate(EXTRACT, {"blocks": []}, StructuredResume)
        assert error.value.code == "MODEL_OUTPUT_INVALID"
    finally:
        provider.close()
