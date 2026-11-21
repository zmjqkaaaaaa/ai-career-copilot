from app.ai.provider import Prompt

ADVICE_PROMPT = Prompt("job_application_advice", "job-advice-1", """
你是职业辅导助手。使用已经判定的要求状态、差距、岗位方向和本地投递判断生成具体行动。
硬性冲突单列，待验证表示需要补充证据。不要重算分数或改变状态，不要编造掌握的技能、经历、指标和招聘结果。
简历建议仅说该补什么证据。面试建议列出可练习的问题。项目建议明确为拟议实践。
""", '{"rationale":"先核对硬性要求","resume_focus":["补充可复核的 SQL 查询"],"interview_focus":["说明指标口径"],"projects":["数据看板练习"],"next_steps":["准备一个查询示例"]}')

PRACTICE = {
    "education": "核对招聘条件与可提供的教育或毕业时间材料",
    "product": "完成一页需求说明，记录用户、目标、流程和验收指标",
    "ai": "用合成输入做一个小型 AI 功能原型，记录失败样例和评估方法",
    "data": "选用公开或合成数据完成一个可复算的分析案例",
    "practice": "梳理一个项目的目标、个人贡献和可展示交付物",
    "industry": "整理一页行业场景与约束分析，并标明信息出处",
}

def enrich(row: dict) -> dict:
    importance, status, dimension = row["importance"], row["status"], row["dimension"]
    is_pending = status.startswith("pending")
    cost = "低" if is_pending else "较高" if dimension in {"education", "ai", "practice"} else "中"
    if importance == "required":
        priority = "高"
    elif importance == "preferred" or (importance == "optional" and dimension in {"product", "ai"} and cost == "低"):
        priority = "中"
    else:
        priority = "低"
    action = "查找已有作品、材料或向招聘方核对条件" if is_pending else f"围绕「{row['name']}」安排一次针对性练习"
    return {**row, "priority": priority, "estimated_cost": cost,
            "why": f"按该要求的重要性、当前证据以及预计补足成本排序，成本估计为{cost}。",
            "action": action,
            "practice": PRACTICE[dimension],
            "validation": "提交可复查的材料、操作记录或示例，并说明个人贡献和适用边界"}
