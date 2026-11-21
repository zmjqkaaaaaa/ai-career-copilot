import base64
import json
import os
from pathlib import Path

import httpx2
import pytest

from app.ai.provider import Provider
from app.core.errors import ApiError
from app.db.session import session_factory
from app.services.code_project_workflow import run_code_project_once
from app.services.codebase_parser import mask_source, parse_file
from app.services.github_service import GitHub, normalize_repo

PREFIX = "/api/v1/code-projects"
REV = "1" * 40
NEW = "2" * 40
GIT_TREE = "f" * 40
SOURCE = """from utils import total
from fastapi import FastAPI
app = FastAPI()

def twice(value):
    return total(value, value)

def compute(data):
    return twice(data)

@app.get('/count')
def count():
    return compute(2)
"""
UTIL = """def total(left, right):
    return left + right
"""
SPEC = {
    "README.md": ("0", "# Study project"),
    "main.py": ("a", SOURCE),
    "utils.py": ("b", UTIL),
    "requirements.txt": ("c", "fastapi==0.121.0\nsqlalchemy>=2\n"),
    "tests/browser.test.ts": ("d", "export function probe(): boolean { return true }"),
    "archive/image.png": ("e", "binary"),
    ".env": ("3", "should never read"),
    "creds/client-secret.json": ("4", "should never read"),
    "node_modules/ignored.js": ("5", "should never read"),
    "README-LINK.md": ("6", "should never read"),
}


class GitHubFake:
    revision = REV

    def head(self, slug):
        assert slug == "school/course"
        return {"default_branch": "main", "language": "Python", "stargazers_count": 12}, self.revision, GIT_TREE

    def tree(self, slug, sha):
        return [{"type": "blob", "mode": "120000" if tag == "6" else "100644",
                 "path": path, "size": len(source.encode()), "sha": tag * 40}
                for path, (tag, source) in SPEC.items()]

    def text(self, slug, sha, size):
        assert sha[0] in "0abcd"
        return next(source for tag, source in SPEC.values() if tag * 40 == sha)

    def close(self):
        pass


class TeachingFake:
    def __init__(self, _settings):
        pass

    def close(self):
        pass

    def generate(self, prompt, payload, contract):
        if prompt.name == "mentor_quiz":
            return contract.model_validate({
                "question": "compute 为什么调用 twice？", "concept": "函数调用",
                "expected_answer": "参考内容仅在评分后返回",
                "rubric": [{"label": "调用", "expected": "指出 twice"}, {"label": "返回", "expected": "说明返回值"}],
                "references": [payload["evidence"][0]["id"]],
            })
        if prompt.name == "mentor_grade":
            return contract.model_validate({"criteria": [{"index": 1, "result": "correct", "feedback": "找到调用"},
                {"index": 2, "result": "partial", "feedback": "可说明返回值"}],
                "explanation": "识别了调用和一部分返回值", "practice": "跟踪负数输入"})
        return contract.model_validate({"overview": "代码走读", "sections": [
            {"title": "调用说明", "explanation": "入口调用了一个子函数", "status": "observed", "references": [1]},
            {"title": "虚构判断", "explanation": "无依据", "status": "observed", "references": [999]},
        ]})


def code_worker(provider=TeachingFake, github=GitHubFake):
    assert run_code_project_once(session_factory(), provider, github)


def import_project(client, headers, url="https://github.com/school/course"):
    response = client.post(PREFIX + "/import", headers=headers, json={"url": url})
    assert response.status_code == 202, response.text
    return response.json()


def enqueue(client, headers, pid, body, bad=False):
    path = f"{PREFIX}/{pid}"
    preview = client.post(path + "/preview", headers=headers, json=body)
    assert preview.status_code == 200, preview.text
    if body["kind"] == "grade":
        assert "参考内容仅在评分后返回" not in preview.text
    action = {"analyze": "analyze", "explain": "explain", "chat": "chat", "quiz": "quizzes/generate",
              "grade": f"quizzes/{body.get('quiz_id')}/submit"}[body["kind"]]
    data = {**body, "approval": preview.json()["approval"]}
    if bad:
        changed = client.post(f"{path}/{action}", headers=headers, json={**data, "question": "changed"})
        assert changed.status_code == 409
    queued = client.post(f"{path}/{action}", headers=headers, json=data)
    assert queued.status_code == 202, queued.text
    repeated = client.post(f"{path}/{action}", headers=headers, json=data)
    assert repeated.json()["id"] == queued.json()["id"]
    return queued.json()["id"]


def status(client, headers, path, taskid, expected="succeeded"):
    task = client.get(f"{path}/tasks/{taskid}", headers=headers).json()
    assert task["state"] == expected, f"{task['kind']} {task['state']}: {task['error_code']}"
    return task


def test_project_full_flow(client, bearer_headers):
    headers = bearer_headers()
    item = import_project(client, headers)
    pid = item["project"]["id"]
    endpoint = f"{PREFIX}/{pid}"
    assert import_project(client, headers)["task"]["id"] == item["task"]["id"]
    code_worker()
    status(client, headers, endpoint, item["task"]["id"])
    assert client.get(endpoint, headers=headers).json()["active_commit"] == REV
    files = client.get(endpoint + "/files", headers=headers).json()
    assert {row["path"] for row in files} == {"README.md", "main.py", "utils.py", "requirements.txt", "tests/browser.test.ts"}
    main = next(row["id"] for row in files if row["path"] == "main.py")
    tfile = next(row["id"] for row in files if row["path"].endswith(".ts"))
    loaded = client.post(f"{endpoint}/files/{tfile}/load", headers=headers).json()
    code_worker()
    status(client, headers, endpoint, loaded["task"]["id"])
    assert client.get(f"{endpoint}/files/{tfile}", headers=headers).json()["index"]["symbols"][0]["name"] == "probe"
    arch = client.get(endpoint + "/architecture", headers=headers).json()
    assert {"fastapi", "sqlalchemy", "Python", "TypeScript"} <= {item["name"] for item in arch["tech_stack"]}
    assert arch["routes"][0]["path"] == "/count"
    assert any(row["to"] == "utils.py" for row in arch["imports"])
    assert any(row["caller"] == "compute" and row["name"] == "twice" for row in arch["calls"])
    lookup = client.get(endpoint + "/knowledge", headers=headers, params={"q": "twice"}).json()
    assert lookup["matches"][0]["path"] == "main.py"
    for kind, extra in [("analyze", {}), ("explain", {"file_id": main, "symbol": "compute"}),
                        ("chat", {"question": "这个 compute 如何执行"})]:
        task = enqueue(client, headers, pid, {"commit": REV, "kind": kind, **extra}, bad=kind == "explain")
        code_worker()
        status(client, headers, endpoint, task)
    explanation = client.get(endpoint + "/explanations", headers=headers).json()[0]
    assert len(explanation["sections"]) == 1
    citation = explanation["evidence"][0]
    assert citation["code"] == "\n".join(SOURCE.split("\n")[citation["start"] - 1:citation["end"]])
    assert client.get(endpoint + "/chat/history", headers=headers).json()[0]["question"].endswith("如何执行")
    task = enqueue(client, headers, pid, {"commit": REV, "kind": "quiz", "dimension": "functions", "mode": "function", "file_id": main})
    code_worker()
    quiz = status(client, headers, endpoint, task)["result_id"]
    assert "expected_answer" not in client.get(endpoint + "/quizzes", headers=headers).json()[0]
    task = enqueue(client, headers, pid, {"commit": REV, "kind": "grade", "quiz_id": quiz, "answer": "调用 twice 后返回"})
    code_worker()
    status(client, headers, endpoint, task)
    assert client.put(endpoint + "/mastery-report/self-report", headers=headers,
                      json={"dimension": "functions", "note": "可以画调用路径"}).status_code == 201
    report = client.get(endpoint + "/mastery-report", headers=headers).json()
    assert report["attempts"][0]["score"] == 75
    functions = next(row for row in report["dimensions"] if row["key"] == "functions")
    assert (functions["status"], functions["self_report"]) == ("verified_in_quiz", "可以画调用路径")
    other = bearer_headers()
    assert client.get(endpoint + "/files", headers=other).status_code == 404
    assert client.get(endpoint + "/mastery-report", headers=other).status_code == 404
    assert client.delete(endpoint, headers=other).status_code == 404

    class Updated(GitHubFake):
        revision = NEW

    from unittest.mock import patch
    with patch("app.api.v1.endpoints.code_projects.time", return_value=3):
        refreshed = client.post(endpoint + "/refresh", headers=headers).json()
    code_worker(github=Updated)
    status(client, headers, endpoint, refreshed["task"]["id"])
    assert client.get(endpoint, headers=headers).json()["active_commit"] == NEW
    assert client.get(endpoint + "/mastery-report", headers=headers).json()["attempts"] == []
    prior = client.get(endpoint + "/mastery-report", headers=headers, params={"commit": REV})
    assert prior.json()["attempts"][0]["score"] == 75
    assert client.get(f"{endpoint}/files/{main}", headers=headers).status_code == 404
    assert client.delete(endpoint, headers=headers).status_code == 204


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://github.com@localhost/a/b", "https://github.com:443/a/b",
    "https://github.com/a/b/extra", "https://github.com/a/b?q=1", "https://github.com/a/%2E%2E", "https://[invalid/a/b"])
def test_invalid_urls(url):
    with pytest.raises(ApiError) as error:
        normalize_repo(url)
    assert error.value.code == "GITHUB_URL_INVALID"


@pytest.mark.parametrize("repo_status, repo, reason", [
    (404, {}, "GITHUB_PUBLIC_REPO_UNAVAILABLE"),
    (200, {"private": True, "size": 10}, "GITHUB_PUBLIC_REPO_UNAVAILABLE"),
    (200, {"private": False, "size": 99999}, "GITHUB_REPO_TOO_LARGE"),
    (403, {}, "GITHUB_RATE_LIMIT"),
    (302, {}, "GITHUB_UPSTREAM"),
])
def test_github_rejects_unsafe_or_limited_repository(repo_status, repo, reason):
    def transport(request):
        assert request.url.host == "api.github.com"
        assert request.url.path == "/repos/school/course"
        return httpx2.Response(repo_status, json=repo, headers={"X-RateLimit-Remaining": "0"})
    with httpx2.Client(base_url="https://api.github.com", transport=httpx2.MockTransport(transport)) as client:
        with pytest.raises(ApiError) as error:
            GitHub(client).head("school/course")
    assert error.value.code == reason


def test_tree_truncation_and_text_blob_bound():
    def transport(request):
        if "/trees/" in request.url.path:
            assert request.url.params["recursive"] == "1"
            return httpx2.Response(200, json={"truncated": True, "tree": []})
        return httpx2.Response(200, json={"encoding": "base64", "sha": REV,
            "content": base64.b64encode(b"a\x00b").decode("ascii")})
    with httpx2.Client(base_url="https://api.github.com", transport=httpx2.MockTransport(transport)) as client:
        github = GitHub(client)
        for call, reason in [(lambda: github.tree("school/course", REV), "GITHUB_TREE_TOO_LARGE"),
                             (lambda: github.text("school/course", REV, 3), "GITHUB_FILE_UNREADABLE"),
                             (lambda: github.text("school/course", REV, 131073), "GITHUB_FILE_TOO_LARGE")]:
            with pytest.raises(ApiError) as error:
                call()
            assert error.value.code == reason


def test_credentials_mask_preserves_line_numbers():
    raw = 'def hello():\n    password = "synthetic-Password-1234"\n    return 4\n'
    clean, index = parse_file("main.py", "Python", raw)
    assert "synthetic-Password" not in clean
    assert index["symbols"][0] == {"name": "hello", "kind": "function", "start": 1, "end": 3}
    assert mask_source("start\n-----BEGIN PRIVATE KEY-----\nkey data\n-----END PRIVATE KEY-----\nend").splitlines()[-1] == "end"
    assert "key data" not in mask_source("-----BEGIN PRIVATE KEY-----\nkey data\n-----END PRIVATE KEY-----")


@pytest.mark.skipif(os.getenv("CAREER_LIVE_PROJECTS") != "1", reason="Requires public GitHub and configured model")
def test_live_public_repositories(client, bearer_headers):
    headers = bearer_headers()
    fixtures = [
        ("pallets/itsdangerous", "Python"), ("sindresorhus/yocto-queue", "JavaScript"), ("sindresorhus/is", "TypeScript"),
    ]
    reports = []
    for slug, language in fixtures:
        imported = import_project(client, headers, f"https://github.com/{slug}")
        code_worker(github=GitHub)
        pid = imported["project"]["id"]
        path = f"{PREFIX}/{pid}"
        status(client, headers, path, imported["task"]["id"])
        detail = client.get(path, headers=headers).json()
        commit = detail["active_commit"]
        arch = client.get(path + "/architecture", headers=headers).json()
        assert any(value["name"] == language for value in arch["tech_stack"]), arch["tech_stack"]
        source_file = next(file for file in client.get(path + "/files", headers=headers).json()
                           if file["loaded"] and file["language"] == language and file["kind"] == "source")
        full = client.get(f"{path}/files/{source_file['id']}", headers=headers).json()
        assert full["index"]["status"] == "parsed"
        reports.append({"repository": slug, "commit": commit, "tested_file": full["path"], "architecture": arch})
        if language != "JavaScript":
            continue
        for kind, extra in [("analyze", {}), ("explain", {"file_id": full["id"]}),
                            ("quiz", {"file_id": full["id"], "dimension": "functions", "mode": "function"})]:
            task = enqueue(client, headers, pid, {"commit": commit, "kind": kind, **extra})
            code_worker(provider=Provider)
            finished = status(client, headers, path, task)
            if kind == "quiz":
                quiz_id = finished["result_id"]
        task = enqueue(client, headers, pid, {"commit": commit, "kind": "grade",
            "quiz_id": quiz_id, "answer": "队列按先进先出取出最早入队的元素，空队列时返回 undefined。"})
        code_worker(provider=Provider)
        status(client, headers, path, task)
        reports[-1] = {**reports[-1], "architecture": client.get(path + "/architecture", headers=headers).json(),
                       "explanation": client.get(path + "/explanations", headers=headers).json(),
                       "quiz": client.get(path + "/quizzes", headers=headers).json(),
                       "mastery": client.get(path + "/mastery-report", headers=headers).json()}
    directory = os.getenv("CAREER_PROJECT_REPORT_DIR")
    if directory:
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        (output / "public-project-acceptance.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.skipif(os.getenv("CAREER_LIVE_MENTOR_REVIEW") != "1", reason="Reuses the public queue snapshot from live acceptance")
def test_live_mentor_review(client, bearer_headers):
    from sqlalchemy import select
    from app.models.code_project import CodeProject, ProjectFile, ProjectSnapshot
    from app.models.user import User

    with session_factory().begin() as db:
        case = db.execute(select(CodeProject, ProjectSnapshot, ProjectFile, User.email).join(
            ProjectSnapshot, ProjectSnapshot.project_id == CodeProject.id).join(
            ProjectFile, ProjectFile.snapshot_id == ProjectSnapshot.id).join(
            User, User.id == CodeProject.user_id).where(
            CodeProject.slug == "sindresorhus/yocto-queue", ProjectFile.path == "index.js",
            ProjectFile.content.is_not(None), User.email.like("test-%@example.com"))
            .order_by(CodeProject.id.desc()).limit(1)).one()
        project, snapshot, source, email = case
        project_id, commit, file_id = project.id, snapshot.commit_sha, source.id
        original = source.content
    headers = bearer_headers(email)
    path = f"{PREFIX}/{project_id}"
    task = enqueue(client, headers, project_id, {"commit": commit, "kind": "explain",
                                                "file_id": file_id, "symbol": "Queue.dequeue"})
    code_worker(provider=Provider)
    finished = status(client, headers, path, task)
    result = client.get(path + "/explanations", headers=headers, params={"commit": commit}).json()
    result = next(item for item in result if item["id"] == finished["result_id"])
    assert result["sections"] and result["evidence"]
    for ref in result["evidence"]:
        assert ref["code"] == "\n".join(original.split("\n")[ref["start"] - 1:ref["end"]])
    directory = os.getenv("CAREER_PROJECT_REPORT_DIR")
    if directory:
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        (output / "focused-code-explanation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
