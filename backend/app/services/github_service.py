import base64
from binascii import Error
import json
import re
from urllib.parse import urlsplit

import httpx2

from app.core.errors import ApiError

MAX_REPO_KIB = 20 * 1024
MAX_TREE = 2000
MAX_FILE = 128 * 1024
MAX_READ_FILES = 40
MAX_READ_BYTES = 3 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}")


def normalize_repo(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        raise ApiError(422, "GITHUB_URL_INVALID", "请输入公开 GitHub 仓库首页的 HTTPS 地址") from None
    path = parts.path.strip("/").split("/")
    if (parts.scheme != "https" or parts.netloc.lower() != "github.com" or parts.query or parts.fragment
            or not re.fullmatch(r"/[^/]+/[^/]+/?", parts.path)
            or len(path) != 2 or not OWNER.fullmatch(path[0]) or not REPO.fullmatch(path[1])
            or path[1].removesuffix(".git") in {"", ".", ".."}):
        raise ApiError(422, "GITHUB_URL_INVALID", "请输入公开 GitHub 仓库首页的 HTTPS 地址")
    return f"{path[0]}/{path[1].removesuffix('.git')}".lower()


class GitHub:
    def __init__(self, client=None):
        self.client = client or httpx2.Client(base_url="https://api.github.com", timeout=12, follow_redirects=False,
                                             trust_env=False, headers={"Accept": "application/vnd.github+json"})

    def close(self):
        self.client.close()

    def get(self, path, params=None, byte_limit=2_500_000):
        try:
            with self.client.stream("GET", path, params=params) as response:
                if response.status_code == 429 or (response.status_code == 403 and (
                        response.headers.get("X-RateLimit-Remaining") == "0" or response.headers.get("Retry-After"))):
                    hints = {}
                    for header in ("Retry-After", "X-RateLimit-Reset"):
                        value = response.headers.get(header, "")
                        if value.isascii() and value.isdecimal() and len(value) <= 12:
                            hints[header] = value
                    raise ApiError(429, "GITHUB_RATE_LIMIT", "GitHub 请求受限，请等待配额恢复", hints)
                if response.status_code in {403, 404, 451}:
                    raise ApiError(404, "GITHUB_PUBLIC_REPO_UNAVAILABLE", "公开仓库或其内容不可用")
                if response.status_code != 200:
                    raise ApiError(502, "GITHUB_UPSTREAM", "GitHub 未能提供仓库数据")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > byte_limit:
                        raise ApiError(422, "GITHUB_RESPONSE_TOO_LARGE", "GitHub 返回内容超过读取上限")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError
                return result
        except (httpx2.RequestError, ValueError):
            raise ApiError(502, "GITHUB_RESPONSE_INVALID", "GitHub 请求超时或响应无法读取") from None

    def head(self, slug):
        repo = self.get(f"/repos/{slug}")
        if repo.get("private") is not False or (repo.get("visibility") or "public") != "public":
            raise ApiError(404, "GITHUB_PUBLIC_REPO_UNAVAILABLE", "只能导入公开仓库")
        if not isinstance(repo.get("size"), int) or repo["size"] > MAX_REPO_KIB:
            raise ApiError(422, "GITHUB_REPO_TOO_LARGE", "仓库超过 20 MiB 的导入上限")
        commit = self.get(f"/repos/{slug}/commits/HEAD")
        sha = commit.get("sha", "")
        tree = commit.get("commit", {}).get("tree", {}).get("sha", "")
        if not SHA.fullmatch(sha) or not SHA.fullmatch(tree):
            raise ApiError(502, "GITHUB_COMMIT_INVALID", "无法确认仓库提交版本")
        return {key: repo.get(key) for key in ("description", "default_branch", "language", "stargazers_count",
                                               "created_at", "updated_at", "size", "license")}, sha, tree

    def tree(self, slug, tree_sha):
        result = self.get(f"/repos/{slug}/git/trees/{tree_sha}", params={"recursive": "1"})
        entries = result.get("tree", [])
        if result.get("truncated") or len(entries) > MAX_TREE:
            raise ApiError(422, "GITHUB_TREE_TOO_LARGE", "文件树超出读取上限或被 GitHub 截断")
        return entries

    def text(self, slug, blob_sha, size):
        if not SHA.fullmatch(blob_sha) or not 0 <= size <= MAX_FILE:
            raise ApiError(422, "GITHUB_FILE_TOO_LARGE", "文件超过读取上限")
        record = self.get(f"/repos/{slug}/git/blobs/{blob_sha}", byte_limit=MAX_FILE * 2 + 8192)
        try:
            if record.get("encoding") != "base64" or record.get("sha") != blob_sha:
                raise ValueError
            data = base64.b64decode("".join(record["content"].split()), validate=True)
            if len(data) != size or b"\x00" in data:
                raise ValueError
            return data.decode("utf-8-sig")
        except (ValueError, KeyError, TypeError, Error):
            raise ApiError(422, "GITHUB_FILE_UNREADABLE", "仅支持可解码的 UTF-8 文本文件") from None
