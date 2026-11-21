from datetime import UTC, datetime
import os

import pytest
from app.ai.provider import Provider
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import session_factory
from app.schemas.discovery import PRD_FIELDS
from app.services.discovery_workflow import run_discovery_once
from app.services.market_research_service import collect_sources

PREFIX = "/api/v1"
CASES = [
    ("低空经济", "巡检日志", "重复整理巡检日志用了三小时"),
    ("国际贸易", "合规材料", "上周手工复核假设的报关资料"),
    ("教育", "课程笔记", "周一复习时找不到上次的课程笔记"),
    ("零售", "库存核对", "模拟库存核对时反复核算缺货"),
    ("物流", "运输异常", "在练习里花两小时整理运输异常"),
]

class FakeProvider:
    def __init__(self, _settings):
        pass

    def close(self):
        pass

    def generate(self, prompt, payload, schema):
        if prompt.name == "discovery_turn":
            last = payload["messages"][-1]
            assert last["role"] == "user" and last["id"]
            return schema.model_validate({
                "reply": "先记录证据。",
                "questions": ["当时用了哪些工具？", "其中哪个环节耗时最长？"],
                "learning_note": "用一次具体经历理解现有替代方案。",
                "interests": [
                    {"name": "用户未表达的兴趣", "category": "行业", "origin": "stated",
                     "reason": "模拟错误引用", "evidence_message_id": last["id"], "confidence": "high"}
                ],
            })
        if prompt.name == "discovery_pain":
            last = next(item for item in reversed(payload["messages"]) if item["role"] == "user")
            return schema.model_validate({"pain_points": [{
                "pain_point_name": "整理耗时", "target_user": "一线人员", "scenario": "记录后汇总",
                "user_problem": "重复整理", "current_solution": "手动汇总",
                "validation_status": "interview_reported", "confidence": "high",
                "evidence": [{"kind": "experience", "detail": last["text"], "message_id": last["id"]},
                             {"kind": "observation", "detail": "无来源内容", "message_id": -1}],
                "interview_questions": ["上次耗时多长？"],
            }]})
        if prompt.name == "discovery_research":
            return schema.model_validate({"competitors": [{
                "product_name": "合成竞品", "official_source": 1, "features": {"text": "记录检索", "sources": [1], "evidence_excerpt": "支持记录检索"},
                "business_model": {"text": "未经证实的收费", "sources": [999]},
            }]})
        if prompt.name == "discovery_opportunity":
            assert "pain:1" in payload["evidence"]
            return schema.model_validate({"ratings": [
                {"dimension": "demand", "rating": 4, "basis": "evidence", "reason": "存在用户自述", "references": ["pain:1"]},
                {"dimension": "role_fit", "rating": 3, "basis": "evidence", "reason": "引用不支持此项", "references": ["pain:1"]},
                {"dimension": "portfolio", "rating": 4, "basis": "ai_inference", "reason": "尚待验证", "references": []},
            ], "differentiation": "分析整理时间", "feasibility": "先用合成资料", "validation_plan": "收集三例"})
        if prompt.name == "discovery_recommend":
            assert payload["background"]["undergraduate_major"]
            return schema.model_validate({"projects": [{
                "name": name, "direction": kind, "background": "合成场景", "target_user": "一线人员",
                "pain": "整理耗时", "positioning": "可复查练习", "features": [feature], "ai_use": "整理输入",
                "stack": ["Python"], "difficulty": "入门", "estimated_hours": length,
                "learning": ["验证假设"], "role_alignment": "调研与评估", "differentiation": "明确场景",
                "risks": ["需要核对数据"], "reason": "符合目标方向", "deliverable": deliverable,
            } for kind, name, feature, length, deliverable in [
                ("workflow","整理工作台","任务流",24,"流程原型"), ("analysis","成本拆解器","耗时分析",12,"分析报告"),
                ("evaluation","摘要评估器","错误标注",48,"评估样本集"),
            ]]})
        return schema.model_validate({"title": "合成 PRD", "sections": {key: "尚待用户核对。" for key in PRD_FIELDS}})

def worker(factory=FakeProvider, search=collect_sources):
    assert run_discovery_once(session_factory(), factory, search)

def queue(client, headers, sid, body):
    path = f"{PREFIX}/discovery/sessions/{sid}"
    preview = client.post(f"{path}/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    paths = {
        "turn": f"{path}/messages", "pain": f"{path}/pain-points",
        "research": f"{PREFIX}/research/competitors?session_id={sid}",
        "opportunity": f"{PREFIX}/opportunities/evaluate?session_id={sid}",
        "recommend": f"{PREFIX}/projects/recommendations?session_id={sid}",
        "prd": f"{PREFIX}/projects/recommendations/{body.get('reference_id')}/prd",
    }
    payload = {**body, "approval": preview.json()["approval"]}
    queued = client.post(paths[body["kind"]], headers=headers, json=payload)
    assert queued.status_code == 202, queued.text
    assert client.post(paths[body["kind"]], headers=headers, json=payload).json()["id"] == queued.json()["id"]
    return queued.json()["id"]

def result(client, headers, task):
    state = client.get(f"{PREFIX}/discovery/tasks/{task}", headers=headers).json()
    assert state["state"] == "succeeded", f"{state['kind']}: {state['state']} ({state['error_code']})"
    return state

def session(client, headers, title):
    return client.post(f"{PREFIX}/discovery/sessions", headers=headers, json={"title": title, "weekly_hours": 6}).json()["id"]

@pytest.mark.parametrize("case", CASES, ids=[item[0] for item in CASES])
def test_workflow_five_backgrounds(client, bearer_headers, case):
    major, direction, event = case
    headers = bearer_headers()
    assert client.put(f"{PREFIX}/profiles/me", headers=headers, json={"undergraduate_major": major, "target_position":"AI 产品经理"}).status_code == 200
    sid = session(client, headers, direction)
    base = f"{PREFIX}/discovery/sessions/{sid}"
    for message in (event, "实际是手动汇总，使用了表格。"):
        task = queue(client, headers, sid, {"kind":"turn", "message":message})
        worker()
        result(client, headers, task)
    detail = client.get(base, headers=headers).json()
    assert detail["background"]["undergraduate_major"] == major
    assert len(detail["messages"]) == 4
    assert len(detail["messages"][-1]["details"]["questions"]) == 2
    assert detail["interests"][0]["data"]["origin"] == "inferred"
    assert client.get(base, headers=bearer_headers()).status_code == 404
    task = queue(client, headers, sid, {"kind":"pain"})
    worker()
    pain = result(client, headers, task)["result_id"]
    saved = client.get(f"{PREFIX}/pain-points", headers=headers).json()[0]["data"]
    assert saved["validation_status"] == "hypothesis" and len(saved["evidence"]) == 1
    task = queue(client, headers, sid, {"kind":"research", "reference_id":pain, "sources":[{
        "url":"https://example.com/synthetic", "title":"合成来源", "excerpt":"支持记录检索", "source_type":"official",
    }]})
    worker()
    research = result(client, headers, task)["result_id"]
    claims = client.get(f"{PREFIX}/research/competitors/{research}", headers=headers).json()
    assert claims["competitors"][0]["data"]["business_model"] is None
    assert claims["data"]["sources"][0]["method"] == "user_supplied"
    task = queue(client, headers, sid, {"kind":"opportunity", "reference_id":pain, "research_id":research})
    worker()
    opportunity = result(client, headers, task)["result_id"]
    scored = client.get(f"{PREFIX}/opportunities", headers=headers).json()[0]["data"]
    assert (scored["score"], scored["coverage"]) == (100, 15)
    assert next(item for item in scored["ratings"] if item["dimension"] == "role_fit")["rating"] is None
    task = queue(client, headers, sid, {"kind":"recommend", "reference_id":opportunity})
    worker()
    result(client, headers, task)
    projects = client.get(f"{PREFIX}/projects/recommendations", headers=headers).json()
    assert len(projects) >= 3 and len({p["data"]["direction"] for p in projects}) == len(projects)
    project = projects[0]["id"]
    assert client.put(f"{PREFIX}/projects/recommendations/{project}", headers=headers, json={"selected":True, "favorite":True}).status_code == 200
    task = queue(client, headers, sid, {"kind":"prd", "reference_id":project})
    worker()
    prd_id = result(client, headers, task)["result_id"]
    original = client.get(f"{PREFIX}/prds/{prd_id}", headers=headers).json()
    assert original["version"] == 1 and "## 验收标准" in original["content"]
    edited = client.put(f"{PREFIX}/prds/{prd_id}", headers=headers, json={
        "title":"编辑后的草稿","version":1,"content":original["content"] + "\n\n已补充验收说明。",
    })
    assert edited.status_code == 201 and edited.json()["version"] == 2
    markdown = client.get(f"{PREFIX}/prds/{edited.json()['id']}/markdown", headers=headers)
    assert markdown.headers["content-type"].startswith("text/markdown") and "已补充" in markdown.text

def test_timeout_retry_and_stale_preview(client, bearer_headers):
    headers = bearer_headers()
    sid = session(client, headers, "超时测试")
    class Timeout(FakeProvider):
        def generate(self, *_):
            raise ApiError(504, "MODEL_TIMEOUT", "模拟超时")
    base = f"{PREFIX}/discovery/sessions/{sid}"
    body = {"kind":"turn", "message":"最近一次整理日志用了一小时"}
    preview = client.post(f"{base}/preview", headers=headers, json=body).json()
    rejected = client.post(f"{base}/messages", headers=headers, json={**body, "message":"内容变化", "approval":preview["approval"]})
    assert rejected.status_code == 409
    task = queue(client, headers, sid, body)
    worker(Timeout)
    path = f"{PREFIX}/discovery/tasks/{task}"
    assert client.get(path, headers=headers).json()["error_code"] == "MODEL_TIMEOUT"
    assert client.post(path + "/retry", headers=headers).json()["attempt"] == 2
    worker()
    assert result(client, headers, task)["attempt"] == 2
    assert len(client.get(base + "/messages", headers=headers).json()) == 2

def test_search_empty_results_and_missing_key(client, bearer_headers, monkeypatch):
    from pydantic import SecretStr
    headers = bearer_headers()
    sid = session(client, headers, "市场来源边界")
    queue(client, headers, sid, {"kind":"turn","message":"当时用纸记载了巡检过程"})
    worker()
    task = queue(client, headers, sid, {"kind":"pain"})
    worker()
    pain = result(client, headers, task)["result_id"]
    monkeypatch.setattr(get_settings(), "tavily_api_key", None)
    body = {"kind":"research", "reference_id":pain, "queries":["巡检记录竞品"]}
    preview = client.post(f"{PREFIX}/discovery/sessions/{sid}/preview", headers=headers, json=body)
    assert preview.json()["error"]["code"] == "DISCOVERY_SEARCH_NOT_CONFIGURED"
    monkeypatch.setattr(get_settings(), "tavily_api_key", SecretStr("synthetic"))
    task = queue(client, headers, sid, body)
    worker(search=lambda *_: [])
    research = result(client, headers, task)["result_id"]
    detail = client.get(f"{PREFIX}/research/competitors/{research}", headers=headers).json()
    assert detail["data"]["status"] == "insufficient_results" and not detail["competitors"]

def test_tavily_transport_contract(monkeypatch):
    from pydantic import SecretStr
    class Transport:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def post(self, url, headers, json):
            assert url == "https://api.tavily.com/search" and headers["Authorization"] == "Bearer synthetic"
            assert json["search_depth"] == "basic" and json["query"] == "合成测试"
            class Result:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {"results":[{"url":"https://example.com/source#example", "title":"资料", "content":"原文"}]}
            return Result()
    monkeypatch.setattr("app.services.market_research_service.httpx2.Client", Transport)
    monkeypatch.setattr(get_settings(), "tavily_api_key", SecretStr("synthetic"))
    data = collect_sources(get_settings(), ["合成测试"], [])
    assert data[0]["method"] == "tavily" and data[0]["id"] == 1
    assert datetime.fromisoformat(data[0]["collected_at"]).tzinfo == UTC

@pytest.mark.skipif(os.environ.get("CAREER_LIVE_DISCOVERY") != "1", reason="Opt in to real model calls with synthetic content")
def test_live_model_discovery(client, bearer_headers):
    headers = bearer_headers()
    sid = session(client, headers, "合成低空巡检探索")
    task = queue(client, headers, sid, {"kind":"turn", "message":"我对低空经济感兴趣。昨天下午我在虚构巡检练习中手工整理了三十条任务，用了两小时。作为模拟调度员，我导出表格后逐条补写异常说明。"})
    worker(Provider)
    reply = result(client, headers, task)
    task = queue(client, headers, sid, {"kind":"pain"})
    worker(Provider)
    pain = result(client, headers, task)["result_id"]
    assert pain and reply["result_id"]
    task = queue(client, headers, sid, {"kind":"research", "reference_id":pain, "sources":[{
        "url":"https://docs.n8n.io/build/integrate-ai/", "title":"n8n Integrate AI", "excerpt":"Build AI-powered workflows in n8n with LLM providers, agents, tools, memory, and MCP servers.", "source_type":"official",
    }]})
    worker(Provider)
    research = result(client, headers, task)["result_id"]
    task = queue(client, headers, sid, {"kind":"opportunity", "reference_id":pain, "research_id":research})
    worker(Provider)
    opportunity = result(client, headers, task)["result_id"]
    task = queue(client, headers, sid, {"kind":"recommend", "reference_id":opportunity})
    worker(Provider)
    selected = result(client, headers, task)["result_id"]
    assert client.put(f"{PREFIX}/projects/recommendations/{selected}", headers=headers, json={"selected": True}).status_code == 200
    task = queue(client, headers, sid, {"kind":"prd", "reference_id":selected})
    worker(Provider)
    prd = result(client, headers, task)["result_id"]
    document = client.get(f"{PREFIX}/prds/{prd}", headers=headers).json()["content"]
    assert "## 验收标准" in document
    report = client.get(f"{PREFIX}/research/competitors/{research}", headers=headers).json()
    assert report["data"]["sources"][0]["method"] == "user_supplied"
    directory = os.environ.get("CAREER_DISCOVERY_REPORT_DIR")
    if directory:
        import json
        from pathlib import Path

        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        (output / "competitor-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "prd-example.md").write_text(document, encoding="utf-8")
