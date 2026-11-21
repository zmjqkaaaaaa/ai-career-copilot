from unicodedata import normalize

COMMON = {"complete": "回答完整性", "logic": "逻辑结构", "accuracy": "专业准确性",
          "clarity": "表达清晰度", "experience": "实践经验", "evidence": "证据充分性"}
SPECIAL = {
    "product": {"user": "用户理解", "demand": "需求分析", "solution": "解决方案", "priority": "优先级",
                "value": "商业价值", "metrics": "评估指标"},
    "technical": {"concept": "概念准确性", "principle": "技术原理", "implementation": "实现逻辑",
                  "tradeoff": "技术取舍", "error_handling": "异常处理"},
    "project": {"business": "业务背景", "contribution": "个人贡献", "architecture": "架构理解",
                "delivery": "技术实现", "validation": "效果验证", "reflection": "复盘能力"},
    "behavior": {"situation": "情境", "task": "任务", "action": "行动", "result": "结果", "reflection": "反思"},
}
VERSION = "interview-rubric-v2"
ANCHORS = {0: "关键理解错误或有证据显示未回应核心", 1: "提及相关内容但关键步骤错误或不足",
           2: "基本方向正确，存在重要遗漏", 3: "准确清晰，缺少少量必要细节",
           4: "准确完整，满足所评维度并有清晰依据"}


def rules(kind):
    return [{"key": key, "label": label, "weight": total / len(group)}
            for group, total in ((COMMON, 40), (SPECIAL[kind], 60)) for key, label in group.items()]


def excerpt(quote, text):
    if not quote:
        return False
    needle = " ".join(normalize("NFKC", quote).strip().strip('“”‘’"').split()).casefold()
    return bool(needle and needle in " ".join(normalize("NFKC", text).split()).casefold())


def evaluate(kind, result, answer):
    proposed = {row.dimension: row for row in result.ratings}
    entries = []
    weighted = available = 0.0
    for rule in rules(kind):
        row = proposed.get(rule["key"]) or proposed.get(rule["label"])
        value = row.level if row and excerpt(row.quote, answer) else None
        if value is not None:
            available += rule["weight"]
            weighted += value * rule["weight"] / 4
        entries.append({**rule, "level": value, "score": value * 25 if value is not None else None,
                        "quote": row.quote if value is not None else None,
                        "reason": row.reason if value is not None else "证据不足"})
    return {**result.model_dump(exclude={"ratings", "next_question", "action", "followup_quote", "followup_reason"}),
            "ratings": entries, "score": round(100 * weighted / available, 2) if round(available, 2) >= 50 else None,
            "coverage": round(available, 2), "rubric_version": VERSION,
            "contribution_claim": result.contribution_claim if excerpt(result.contribution_claim, answer) else None}
