from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx2
from app.core.errors import ApiError

SEARCH_HOST = "api.tavily.com"
SEARCH_URL = f"https://{SEARCH_HOST}/search"

def collect_sources(settings, queries: list[str], supplied: list[dict]) -> list[dict]:
    sources = [{**item, "method": "user_supplied"} for item in supplied]
    if queries:
        if not settings.tavily_api_key or not settings.tavily_api_key.get_secret_value().strip():
            raise ApiError(503, "DISCOVERY_SEARCH_NOT_CONFIGURED", "尚未配置 Tavily 搜索密钥")
        try:
            with httpx2.Client(timeout=20, follow_redirects=False) as client:
                for query in queries:
                    response = client.post(SEARCH_URL, headers={"Authorization": "Bearer " + settings.tavily_api_key.get_secret_value()},
                                           json={"query": query, "search_depth": "basic", "max_results": 5, "include_answer": False})
                    response.raise_for_status()
                    for item in response.json().get("results", []):
                        sources.append({"url": item.get("url"), "title": str(item.get("title") or "")[:180],
                                        "excerpt": str(item.get("content") or "")[:1200], "source_type": "unclassified",
                                        "method": "tavily"})
        except httpx2.HTTPStatusError as exc:
            code = {401: "DISCOVERY_SEARCH_AUTH_FAILED", 403: "DISCOVERY_SEARCH_AUTH_FAILED",
                    429: "DISCOVERY_SEARCH_LIMIT"}.get(exc.response.status_code, "DISCOVERY_SEARCH_FAILED")
            raise ApiError(502, code, "搜索服务无法完成请求") from None
        except (httpx2.RequestError, ValueError):
            raise ApiError(502, "DISCOVERY_SEARCH_FAILED", "搜索暂时不可用") from None
    accepted, known = [], set()
    for item in sources:
        url = item.get("url")
        if not isinstance(url, str) or len(url) > 2048:
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or not item["excerpt"]:
            continue
        identity = parsed._replace(fragment="").geturl()
        if identity in known:
            continue
        known.add(identity)
        accepted.append({**item, "id": len(accepted) + 1, "collected_at": datetime.now(UTC).isoformat()})
        if len(accepted) == 12:
            break
    return accepted
