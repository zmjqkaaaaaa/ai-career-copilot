"""Find relevant evidence without treating a resume as proof of a personal trait."""
import re

AI_TOPIC = re.compile(r"人工智能|大模型|机器学习|智能体|检索增强|文生(?:图|视频|ppt)|(?<![a-z0-9])(?:ai|rag|llm|agents?)(?![a-z0-9])", re.I)
AI_INTEREST = re.compile(r"热情|热爱|兴趣|探索|关注")
AI_APPLICATION = re.compile(r"搭建|开发|实现|接入|负责|调研|设计|评估|参与|学习|修读|研究|训练|验证|做过|使用|用.*完成")
AI_STUDY = re.compile(r"专业|课程|本科|学士|硕士|主修|修读|学习|方向")
BEHAVIOUR_INDICATORS = (
    (re.compile(r"团队协作|沟通协作|沟通能力|乐于沟通"), re.compile(r"研发统筹|统筹.*团队|组建.*团队|管理.*团队|协调.*(?:团队|部门|研发)|与.{1,24}(?:协作|共同)|跨部门")),
    (re.compile(r"交付意识|交付能力"), re.compile(r"交付|上线|落地|发布|验收|产出.*(?:文档|报告|原型)")),
    (re.compile(r"逻辑思维|逻辑分析"), re.compile(r"拆解|对照实验|对比实验|设计.*方案|实证分析|风险识别")),
)
INTERVIEW_TRAITS = re.compile(r"热情|热爱|兴趣|自驱|愿景|快节奏|学习能力|逻辑思维|团队协作|沟通协作|沟通能力|乐于沟通|交付意识")
UNSUPPORTED = re.compile(r"计划|希望|拟|尚未|未参与|未使用|没有|未完成|他人|队友|仅由|不熟悉")
PAST_DELIVERY_ACTION = re.compile(r"负责|参与|主持|完成|推进|推动|开发|搭建|实现|设计|统筹|协调|输出|交付|协助|组织")


def related_clauses(items, topic, action):
    matched = []
    for source in items:
        # PDF wrapping is a layout artifact. Keep the exact multiline quote for display.
        text = source["quote"].replace("\n", "")
        if any(topic.search(clause) and action.search(clause) and not UNSUPPORTED.search(clause)
               for clause in re.split(r"[。；;！？]", text)):
            matched.append(source)
    return matched[:3]


def contextual_evidence(requirement, person):
    name, quote = requirement["name"], requirement["quote"]
    practice = person.get("practice", [])
    if requirement["kind"] == "skill":
        if requirement["category"] == "ai" and AI_TOPIC.search(name + quote):
            if AI_INTEREST.search(name) or re.fullmatch(r"(?:ai|人工智能|大模型|机器学习|llm)\s*(?:技术|应用)?\s*(?:理解|基础|认知)", name, re.I):
                practical = related_clauses(practice, AI_TOPIC, AI_APPLICATION)
                academic = related_clauses(person.get("academic_evidence", []), AI_TOPIC, AI_STUDY)
                if sources := [*practical, *academic][:4]:
                    return sources, "相关学习或实践有原文依据。具体技术深度或投入动机可在面试中进一步核实。"
        for label, clue in BEHAVIOUR_INDICATORS:
            if label.search(name) and (sources := related_clauses(practice, clue, PAST_DELIVERY_ACTION)):
                return sources, "找到可用于举例的工作行为。建议用面试案例核实个人贡献和结果。"
    if requirement["kind"] == "experience" and "实习" in quote and AI_TOPIC.search(quote):
        if not re.search(r"至少|以上|[0-9一二三四五六七八九十]+[个年月周]", quote):
            internships = person.get("internship_evidence", [])
            if sources := related_clauses(internships, AI_TOPIC, AI_APPLICATION):
                return sources, "简历有相关方向的实习和具体工作。岗位所需的实践深度仍可结合项目核实。"
    return [], None


def needs_interview_evidence(requirement) -> bool:
    return requirement["kind"] == "skill" and bool(INTERVIEW_TRAITS.search(requirement["name"]))
