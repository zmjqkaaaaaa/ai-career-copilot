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
AI_AGENT_USE = re.compile(r"AI\s*Agent\s*类|AI\s*工具深度使用者|AI\s*编程工具", re.I)
CODING_TOOL = re.compile(r"(?<![a-z0-9])(?:codex|cursor|claude\s+code|qoderwork)(?![a-z0-9])", re.I)
FREQUENT_USE = re.compile(r"每天|每日|日常高频|高频使用|几乎每天|每周\s*[4-7四五六七]\s*天")
TOOL_REFLECTION = re.compile(r"体感|复盘|局限|误判|漏判|改进|口径不一致")
TOOL_IMPROVEMENT = re.compile(r"回归用例|验收用例|预期判定|对照测试|复查|迭代提示词|调整提示词|验证修复")
USER_EXPERIENCE = re.compile(r"用户体验|自身使用场景|痛点发现")
FIRST_HAND = re.compile(r"自己用|自己使用|本人|自测|试用|实际使用|观察用户|访谈用户")
DISCOVERED_PROBLEM = re.compile(r"发现|遇到|卡在|反映|反馈")
UX_CHANGE = re.compile(r"(?:提出|设计|推动|调整|移动|合并|简化|缩短|明确).{1,36}(?:入口|步骤|流程|页面|预览|确认|交互|提示)")
INITIATIVE = re.compile(r"自驱|自学|学习能力")
INITIATIVE_ACTION = re.compile(r"(?:主动|自学|自主).{0,14}(?:邀请|组织|开展|学习|研究|验证|试用|调研|整理|复查)")
CONCEPTS = tuple(re.compile(r"(?<![a-z0-9])" + term + r"(?![a-z0-9])", re.I) for term in (r"(?:ai\s*)?agent", "skills", "memory"))
CONCEPT_FAMILIARITY = re.compile(r"了解|熟悉|理解|认知|使用过")
DEMONSTRABLE_WORK = re.compile(r"可展示(?:的)?(?:作品|项目)|作品(?:展示|链接)")
WORK_ARTIFACT = re.compile(r"原型|可运行(?:版本|产品)|(?<![a-z0-9])demo(?![a-z0-9])|管理系统|应用上线|开源(?:项目|贡献)|测试报告|异步解析|匹配报告", re.I)
WORK_ACTION = re.compile(r"搭建|开发|实现|部署|上线|发布|复现|完成|制作|验证|交付|提交")


def evidence_clauses(source):
    # Keep original excerpts for the report. Normalize only for matching.
    return [clause for clause in re.split(r"[。；;！？]", source["quote"].replace("\n", ""))
            if not UNSUPPORTED.search(clause)]


def related_clauses(items, topic, action):
    matched = []
    for source in items:
        if any(topic.search(clause) and action.search(clause) for clause in evidence_clauses(source)):
            matched.append(source)
    return matched[:3]


def demonstrable_work(requirement, person):
    quote = requirement["quote"]
    if (requirement["kind"] not in {"skill", "experience"} or not DEMONSTRABLE_WORK.search(requirement["name"] + quote)
            or re.search(r"必须.{0,12}上线|独立完成|至少[一二两三四五六\d]", quote)):
        return []
    return related_clauses(person.get("practice", []), WORK_ARTIFACT, WORK_ACTION)


def contextual_evidence(requirement, person):
    name, quote = requirement["name"], requirement["quote"]
    practice = person.get("practice", [])
    if requirement["kind"] in {"skill", "experience"} and AI_AGENT_USE.search(name + quote):
        named = {re.sub(r"\s+", " ", tool[0].lower()) for tool in CODING_TOOL.finditer(quote)}
        tool_clue = CODING_TOOL
        if named:
            variants = "|".join(re.escape(tool).replace(r"\ ", r"\s+") for tool in sorted(named))
            tool_clue = re.compile(r"(?<![a-z0-9])(?:" + variants + r")(?![a-z0-9])", re.I)
        if sources := related_clauses(practice, tool_clue, AI_APPLICATION):
            detailed = []
            for source in sources:
                clauses = evidence_clauses(source)
                if (any(tool_clue.search(clause) and FREQUENT_USE.search(clause) and AI_APPLICATION.search(clause) for clause in clauses)
                        and any(TOOL_REFLECTION.search(clause) for clause in clauses)
                        and any(TOOL_IMPROVEMENT.search(clause) for clause in clauses)):
                    detailed.append(source)
            if detailed and not re.search(r"至少.{0,12}(?:个月|小时)|必须同时使用|精通", quote):
                return detailed, "同一项目原文写明工具使用频率、实际任务和发现问题后的改进与验证。", "matched"
            return sources, "简历有 AI 编程工具的项目使用记录。使用频率、深度和改进思路可再补一例。", "partial"
    if requirement["kind"] == "skill":
        if USER_EXPERIENCE.search(name + quote):
            sources = [source for source in practice
                       if any(FIRST_HAND.search(clause) and DISCOVERED_PROBLEM.search(clause) for clause in evidence_clauses(source))
                       and any(UX_CHANGE.search(clause) for clause in evidence_clauses(source))]
            if sources:
                return sources[:3], "项目记录描述了本人在使用或试用中发现的问题，以及提出的具体交互调整。", "matched"
        if INITIATIVE.search(name) and (sources := related_clauses(practice, INITIATIVE_ACTION, PAST_DELIVERY_ACTION)):
            return sources, "原文记录了主动开展的试用或学习行动，可用于面试举例。", "partial"
        concepts = [concept for concept in CONCEPTS if concept.search(name + quote)]
        if len(concepts) >= 2 and CONCEPT_FAMILIARITY.search(quote) and not re.search(r"精通|熟练|部署|开发", quote):
            sources = [source for source in person.get("reviewed_evidence", [])
                       if any(CONCEPT_FAMILIARITY.search(clause) and not re.search(r"不了解|没用过|未接触|未掌握", clause)
                              and all(concept.search(clause) for concept in concepts)
                              for clause in evidence_clauses(source))]
            if sources:
                return sources[:3], "简历明确陈述了对这些概念的基础认知或使用经历。", "matched"
        if requirement["category"] == "ai" and AI_TOPIC.search(name + quote):
            if AI_INTEREST.search(name) or re.fullmatch(r"(?:ai|人工智能|大模型|机器学习|llm)\s*(?:技术|应用)?\s*(?:理解|基础|认知)", name, re.I):
                practical = related_clauses(practice, AI_TOPIC, AI_APPLICATION)
                academic = related_clauses(person.get("academic_evidence", []), AI_TOPIC, AI_STUDY)
                if sources := [*practical, *academic][:4]:
                    return sources, "相关学习或实践有原文依据。具体技术深度或投入动机可在面试中进一步核实。", "partial"
        for label, clue in BEHAVIOUR_INDICATORS:
            if label.search(name) and (sources := related_clauses(practice, clue, PAST_DELIVERY_ACTION)):
                return sources, "找到可用于举例的工作行为。建议用面试案例核实个人贡献和结果。", "partial"
    if requirement["kind"] == "experience" and "实习" in quote and AI_TOPIC.search(quote):
        if not re.search(r"至少|以上|[0-9一二三四五六七八九十]+[个年月周]", quote):
            internships = person.get("internship_evidence", [])
            if sources := related_clauses(internships, AI_TOPIC, AI_APPLICATION):
                return sources, "简历有相关方向的实习和具体工作。岗位所需的实践深度仍可结合项目核实。", "partial"
    return [], None, None


def needs_interview_evidence(requirement) -> bool:
    return requirement["kind"] == "skill" and bool(INTERVIEW_TRAITS.search(requirement["name"]))
