CATEGORIES = {
    "product": "产品能力", "coding": "编程能力", "ai": "AI 技术能力",
    "application": "AI 应用开发能力", "data": "数据分析能力", "career": "求职表达能力",
}
# Stable IDs are used in historical records and API URLs.
_ROWS = [
    ("research", "product", "用户研究与需求分析", [], "把一个需求改写成可验证假设，写三道非诱导访谈题", "案例分析", "用户研究,需求分析,访谈,用户画像"),
    ("mvp", "product", "竞品、PRD 与 MVP", ["research"], "为一个真实痛点给出用户流程、范围和验收标准", "产品文档", "竞品,prd,mvp,产品设计"),
    ("metrics", "data", "产品指标与效果评估", ["research"], "定义一个转化指标及分子、分母、时间窗口和反例", "案例分析", "产品指标,评估,商业模式,数据分析"),
    ("python", "coding", "Python 基础与数据处理", [], "编写一个处理缺失字段的函数，附正常与边界样例", "代码实践", "python,面向对象,函数"),
    ("sql", "data", "SQL 查询、关联与聚合", [], "用模拟岗位表计算各方向岗位数，解释重复行的影响", "代码实践", "sql,聚合,多表"),
    ("api", "application", "API、FastAPI 与数据库", ["python", "sql"], "画出请求到数据库再到响应的流程，说明一条错误路径", "项目实战", "fastapi,api,数据库,sqlalchemy"),
    ("llm", "ai", "LLM 基础与模型选择", [], "比较上下文、输出长度、成本及一次选型的验证方法", "理论学习", "llm,token,上下文,temperature,模型选型"),
    ("prompt", "ai", "提示词与结构化输出", ["llm"], "写一个结构化提取的提示词和失败校验方案", "知识问答", "prompt,结构化,提示词,pydantic,幻觉"),
    ("rag", "ai", "RAG 检索与评估", ["prompt"], "为公开课程笔记设计切分、检索、排序和质量评估", "项目实战", "rag,embedding,rerank,向量,检索"),
    ("agent", "ai", "Agent 工具调用与状态", ["prompt", "api"], "为学习提醒设计工具参数、状态迁移和人工确认", "项目实战", "agent,tool calling,工作流,状态"),
    ("project", "application", "AI 产品实践与测试", ["api", "prompt", "mvp"], "为一次模型调用设计测试、成本限制和降级路径", "项目实战", "项目实践,异常处理,测试,部署"),
    ("interview", "career", "简历、项目表达与面试", [], "用真实经历写一段项目介绍，并标出本人贡献及核对证据", "模拟面试", "简历,面试,表达,个人贡献,复盘"),
]
TOPICS = {key: {"id": key, "category": category, "title": title, "requires": prerequisites,
                "exercise": exercise, "type": kind, "terms": words.split(","), "minutes": 25 if not prerequisites else 40,
                "acceptance": "给出具体输入、关键步骤、结果和一种能复核结果的方式"}
          for key, category, title, prerequisites, exercise, kind, words in _ROWS}
MODES = {"concept": "概念讲解", "python": "Python 代码教学", "sql": "SQL 教学", "llm": "LLM 技术教学",
         "rag": "RAG 教学", "agent": "Agent 教学", "product": "产品案例分析", "socratic": "苏格拉底式提问",
         "mistake": "错题讲解", "project": "项目实战指导"}
PROJECT_EXAMPLES = {
    "python": ("app/services/learning_assessment.py", "exam"),
    "sql": ("app/api/v1/endpoints/learning.py", "progress"),
    "api": ("app/api/v1/endpoints/learning.py", "current_diagnosis"),
    "prompt": ("app/services/interview_evaluation_service.py", "evaluate"),
    "llm": ("app/ai/provider.py", "generate"),
    "agent": ("app/services/interview_engine.py", "next_stage"),
    "rag": ("app/services/project_knowledge_service.py", "citations"),
}
OPEN_FORMATS = {
    "research": "场景分析", "mvp": "产品设计", "metrics": "场景分析", "python": "代码理解",
    "sql": "代码理解", "api": "综合实战", "llm": "概念解释", "prompt": "概念解释",
    "rag": "综合实战", "agent": "综合实战", "project": "综合实战", "interview": "场景分析",
}
# These fixtures compare submitted outputs. They do not run the submitted program.
FIXTURES = {
    "python": {"labels": {"zero": "输入 score=0，保留有效零分", "missing": "输入无 score，用 -1 标记缺失"},
               "expected": {"zero": 0, "missing": -1}},
    "sql": {"labels": {"before": "P1 两条技能、P2 一条技能，关联后共有几行",
                       "distinct": "以上结果按岗位 ID 去重后有几个岗位"},
            "expected": {"before": 3, "distinct": 2}},
}

