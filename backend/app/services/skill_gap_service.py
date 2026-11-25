from app.ai.provider import Prompt

ADVICE_PROMPT_V1 = Prompt("job_application_advice", "job-advice-1", """
你是职业辅导助手。使用已经判定的要求状态、差距、岗位方向和本地投递判断生成具体行动。
硬性冲突单列，待验证表示需要补充证据。不要重算分数或改变状态，不要编造掌握的技能、经历、指标和招聘结果。
简历建议仅说该补什么证据。面试建议列出可练习的问题。项目建议明确为拟议实践。
""", '{"rationale":"先核对硬性要求","resume_focus":["补充可复核的 SQL 查询"],"interview_focus":["说明指标口径"],"projects":["数据看板练习"],"next_steps":["准备一个查询示例"]}')

ADVICE_PROMPT = Prompt("job_application_advice", "job-advice-2", """
你是职业辅导助手。根据输入的逐条岗位要求、状态和本地投递判断，优先选出最多三项值得处理的差距。
只输出一个 JSON 对象，恰好包含 rationale、resume_focus、interview_focus、projects、next_steps 五个字段。
rationale 是一句非空字符串，其余字段均为字符串数组，每个数组至多三项。没有建议的字段用空数组 []。不要输出其他字段、空字符串、编号对象或 Markdown。
硬性冲突优先说明。待验证表示需要核对或补充证据。写清具体行动，不重算分数，不改变匹配状态，不编造用户经历或实际招聘结果。简历建议只针对可复查的真实材料，项目建议必须是拟议实践。
""", ADVICE_PROMPT_V1.example)

ADVICE_FORMAT_ERRORS = {"MODEL_OUTPUT_INVALID", "MODEL_OUTPUT_INCOMPLETE"}

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
    missing = "、".join(check["name"] for check in row.get("checks", []) if not check["sources"])
    if len(row.get("checks", [])) > 1 and missing and status != "unmet":
        action = f"优先补充「{missing}」对应的个人行动、可出示的交付物和验证方式。"
    elif status == "pending_interview":
        action = f"选一段能体现「{row['name']}」的真实经历，说明当时的限制、你的行动和结果。"
    elif row["kind"] == "availability":
        action = "逐项核对可到岗日期、每周天数和能连续实习的时长，再决定是否投递。"
    else:
        action = "查找已有作品、材料或向招聘方核对条件" if is_pending else f"围绕「{row['name']}」安排一次针对性练习"
    return {**row, "priority": priority, "estimated_cost": cost,
            "why": f"按该要求的重要性、当前证据以及预计补足成本排序，成本估计为{cost}。",
            "action": action,
            "practice": PRACTICE[dimension],
            "validation": "提交可复查的材料、操作记录或示例，并说明个人贡献和适用边界"}


def fallback_advice(report: dict) -> dict:
    ranking = {"required": 0, "preferred": 1, "optional": 2, "unknown": 3}
    gaps = sorted(
        (row for row in report["requirements"] if row["status"] != "matched" or row["evidence_status"] == "inferred"),
        key=lambda row: (ranking[row["importance"]], row["status"] != "unmet", row["ordinal"]),
    )[:3]
    skills = [row for row in gaps if row["kind"] in {"skill", "experience"} and row["status"] != "unmet"]
    return {
        "generation_method": "local_fallback",
        "rationale": "根据匹配报告，先核对以下差距。" if gaps else "当前报告没有列出待处理差距，可回看证据后再决定是否投递。",
        "resume_focus": [f"「{row['name']}」：补充可以证明个人行动和结果的真实材料。" for row in skills],
        "interview_focus": [f"准备说明「{row['name']}」的相关经历、个人贡献和验证方式。" for row in skills],
        "projects": [enrich(row)["practice"] for row in skills[:1]],
        "next_steps": [f"「{row['name']}」：{enrich(row)['action']}" for row in gaps],
    }
