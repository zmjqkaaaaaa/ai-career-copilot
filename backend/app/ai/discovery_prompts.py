import json
from app.ai.provider import Prompt
from app.schemas.discovery import PRD_FIELDS

TURN = Prompt("discovery_turn", "turn-1", """你是产品探索导师。先了解用户自己的判断，再指出缺少的信息，追问最近一次具体经历、现有替代方案及实际成本。每轮 questions 最多两条，reply 和 learning_note 不重复提问。引导模式先提问、简短讲知识，辅助模式可举例并明确是假设。避免问已知信息，暂不推荐项目。兴趣自述必须绑定真实用户消息 ID，AI 推断标为 inferred。""",
    '{"reply":"可以从你最近一次经历开始。","questions":["上一次具体发生了什么？"],"learning_note":"先记录发生过的行为。","interests":[]}')
PAIN = Prompt("discovery_pain", "pain-2", """从用户消息提取痛点。pain_point_name、target_user、scenario、user_problem 为必填文本；信息未知的目标用户或场景填写“待验证”，不足以描述具体问题时返回空列表。现有解决方法、频率、严重度未知可用 null。每条证据的 detail 逐字引用用户消息并提供 message_id，kind 只能是 experience（亲历）、observation（观察）、hearsay（转述）。结论一律使用 validation_status=hypothesis。提供中立访谈提纲，询问过去行为、现有方法、付出成本和改进尝试。""", '{"pain_points":[{"pain_point_name":"手工汇总耗时","target_user":"一线记录人员","scenario":"每日整理工作记录","user_problem":"多次转录相同内容","current_solution":"手工汇总","frequency":null,"severity":null,"validation_status":"hypothesis","confidence":"low","evidence":[{"kind":"experience","detail":"我昨天手动整理记录用了一小时","message_id":1}],"interview_target":"近期汇总过记录的人","interview_questions":["最近一次整理记录的过程是什么？"],"demand_signal":"观察实际投入的时间和为改善流程做过的尝试"}]}')
RESEARCH = Prompt("discovery_research", "research-2", """仅依据输入中带编号的公开来源归纳可检索的产品及替代方案。竞品功能、收费、用户评价、技术和其他事实逐项引用确实支持结论的来源 ID，evidence_excerpt 逐字摘录对应来源片段。保留未知，不推测用户规模、份额、营收。official_source 只用于确认为产品官网的编号，证据不足留空。差异化可作为待验证设想。""", '{"competitors":[{"product_name":"示例","features":{"text":"支持任务列表","sources":[1],"evidence_excerpt":"支持任务列表"}}],"market_findings":[]}')
OPPORTUNITY = Prompt("discovery_opportunity", "opportunity-1", """按输入维度评估，rating 是 0 至 4，方向统一为越高越有机会或越可行。提供理由和支持该判断的 evidence_ids，写入 references。资料不足标为 unknown 并将 rating 设为 null。自述假设和模型推断保留对应 basis。提出风险、差异化和可执行的验证方案。""",
    '{"ratings":[],"risks":[],"differentiation":"待核对替代方案","feasibility":"待验证","validation_plan":"访谈近期遇到问题的人"}')
RECOMMEND = Prompt("discovery_recommend", "recommend-1", """依据兴趣、时间、技能证据和岗位差距给出至少三个不同 direction 的方案。应有不同的核心流程、功能和产物。项目是拟议练习，未知需求和技术风险需标明。估算开发工时和难度，给出可复核的展示成果。""",
    '{"projects":[{"name":"需求访谈整理器","direction":"workflow","background":"访谈记录较难汇总","target_user":"访谈者","pain":"整理耗时","positioning":"轻量整理工具","features":["摘录引用"],"ai_use":"起草摘要","stack":["Python"],"difficulty":"入门","estimated_hours":12,"learning":["结构化提取"],"role_alignment":"产品调研","differentiation":"可回引原文","risks":["需要核对摘要"],"reason":"适合短期练习","deliverable":"访谈摘要样例"}]}')
PRD = Prompt("discovery_prd", "prd-2", """为已选择的项目生成待确认的 PRD 草稿。sections 按以下固定键写，内容用 Markdown，验收标准尽量可执行。市场、用户和竞品的事实只使用输入证据，保留原有来源 URL，并把拟议需求标为待验证假设。来源只支持其原文时，不得将技术能力推成行业成熟度或用户需求。设计功能范围、使用流程、AI 输入输出、失败兜底、数据和技术边界。
""" + ", ".join(f"{key}={value}" for key, value in PRD_FIELDS.items()), json.dumps({"title":"项目 PRD 草稿","sections":{k:"待核对" for k in PRD_FIELDS}}, ensure_ascii=False))
