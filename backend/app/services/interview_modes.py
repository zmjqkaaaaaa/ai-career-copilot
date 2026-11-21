MODES = {
    "resume": ("简历深度", ["intro", "resume"]),
    "project": ("项目深度", ["project"]),
    "product": ("产品思维", ["product", "scenario"]),
    "technical": ("AI 技术", ["technical"]),
    "combined": ("综合模拟", ["intro", "resume", "project", "product", "technical", "scenario", "reverse"]),
}
STAGES = {
    "intro": "自我介绍", "resume": "简历经历", "project": "项目理解", "product": "产品思维",
    "technical": "AI 技术", "scenario": "场景设计", "reverse": "候选人反问",
}
STYLES = {"coach": "友好教学型", "hr": "专业 HR 型", "technical": "严格技术型"}
DIFFICULTIES = {"beginner": "初级", "intermediate": "中级", "advanced": "高级"}
QUESTION_TYPES = {"intro": "behavior", "resume": "behavior", "project": "project", "technical": "technical",
                  "product": "product", "scenario": "product", "reverse": "behavior"}
DEFAULT_QUESTIONS = {
    "intro": ("你会如何用一分钟介绍最相关的能力？请用一个具体例子。", "自我介绍"),
    "resume": ("请选一项你提到的经历，说明你的个人职责和成果验证方法。", "个人贡献"),
    "project": ("请选择一个项目场景，说明你会如何验证其中一条关键流程。", "项目验证"),
    "product": ("如果做 AI 求职助手，你如何验证用户愿意使用首版？", "需求验证"),
    "technical": ("假设模型连续返回结构错误，你会如何检测和处理？", "结构化输出"),
    "scenario": ("如果问答产品上线后满意度下降，你会优先核对哪一项证据？", "指标诊断"),
    "reverse": ("如果可以问团队一个问题，你会问什么来判断这个岗位是否适合你？", "岗位反问"),
}


def schedule(settings):
    stages = MODES[settings["mode"]][1]
    budget = max(len(stages), min(12, (settings["minutes"] + 2) // 3))
    default, remainder = divmod(budget, len(stages))
    custom = settings.get("stage_minutes", {})
    if not custom:
        minutes, rest = divmod(settings["minutes"], len(stages))
        return [{"stage": key, "questions": default + int(i < remainder),
                 "minutes": minutes + int(i < rest) if settings["mode"] == "combined" else None}
                for i, key in enumerate(stages)]
    return [{"stage": key, "questions": max(1, min(3, custom[key] // 4 + 1)), "minutes": custom[key]}
            for key in stages]
