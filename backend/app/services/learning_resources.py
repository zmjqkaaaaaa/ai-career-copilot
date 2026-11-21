from app.services.learning_catalog import TOPICS

OFFICIAL = {
    "python": ("Python 官方教程", "https://docs.python.org/3/tutorial/"),
    "sql": ("MySQL SELECT 官方参考", "https://dev.mysql.com/doc/refman/8.0/en/select.html"),
    "api": ("FastAPI 官方教程", "https://fastapi.tiangolo.com/tutorial/"),
    "prompt": ("Pydantic 模型文档", "https://docs.pydantic.dev/latest/concepts/models/"),
    "llm": ("阿里云百炼模型服务", "https://help.aliyun.com/zh/model-studio/"),
    "rag": ("Microsoft Azure AI Search 检索增强生成概述", "https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview"),
    "agent": ("GitHub Actions 工作流语法", "https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions"),
}
CATALOG = [{"id": None, "topic": key, "title": title, "url": url, "kind": "official", "source": "官方文档",
            "credibility": "人工维护的官方来源"} for key, (title, url) in OFFICIAL.items()]
CATALOG += [{"id": None, "topic": key, "title": spec["title"] + " · 项目练习", "url": None,
             "kind": "project", "text": spec["exercise"], "source": "项目课程目录",
             "credibility": "项目内维护的练习说明"} for key, spec in TOPICS.items() if key not in OFFICIAL]

