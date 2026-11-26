import re

from app.services.job_parser import normalize_text

PRACTICE_TERMS = {
    "产品思维": ("需求拆解", "业务流程设计", "梳理业务流程", "拆解角色场景"),
    "需求分析": ("需求拆解", "需求梳理", "梳理需求", "拆解需求"),
    "用户研究": ("用户访谈", "访谈用户", "用户调研", "可用性测试"),
    "竞品分析": ("竞品对比", "对比竞品"),
    "prd": ("产品需求文档",),
    "流程设计": ("业务流程图", "业务流转图"),
    "原型设计": ("设计原型", "页面原型", "交互原型", "搭建原型"),
    "效果评估": ("验收标准", "评测指标", "评估效果", "测试用例", "质量评估", "评测样本"),
    "提示词工程": ("prompt", "提示词设计", "编写提示词", "prompt engineering"),
    "prompt engineering": ("prompt", "提示词迭代", "提示词工程"),
    "数据分析": ("分组聚合", "数据核验", "数据处理", "分析数据", "统计分类准确率"),
    "llm": ("大模型", "大语言模型"),
    "ai 技术理解": ("大模型应用", "提示词迭代", "结构化输出", "模型评测"),
    "rag": ("检索增强生成",),
    "sql": ("结构化查询语言",),
}
ACTION = re.compile(
    r"参与|协助|负责|设计|分析|使用|利用|通过|访谈|梳理|拆解|编写|撰写|输出|整理|"
    r"验证|核对|完成|搭建|开发|构建|评估|开展|绘制|实现|维护|对比|形成|导入|制作|调研|建立|采集|迭代|统计|"
    r"\b(?:used|built|wrote|designed|analyzed|tested|conducted)\b", re.I,
)
HYPOTHETICAL = re.compile(
    r"计划|拟用|拟开展|希望|待补|待学习|尚未|未曾|没有|未掌握|未完成|未使用|未用|未参与|"
    r"未接触|不会|由.*?负责|他人|队友|同事负责|\b(?:planned|will|not|didn.t)\b", re.I,
)


def term_pattern(term: str):
    literal = re.escape(term)
    return re.compile(r"(?<![a-z0-9])" + literal + r"(?![a-z0-9])" if term.isascii() else literal)


def find_practice(name: str, items: list[dict], aliases=()) -> list[dict]:
    name = normalize_text(name)
    terms = {name, *aliases, *PRACTICE_TERMS.get(name, ())}
    patterns = [term_pattern(term) for term in sorted(terms) if len(term) > 1]
    sources = []
    for item in items:
        for clause in re.split(r"[。；;！!？?\n]", item["quote"]):
            clause = normalize_text(clause)
            if ACTION.search(clause) and not HYPOTHETICAL.search(clause) and any(pattern.search(clause) for pattern in patterns):
                if item not in sources:
                    sources.append(item)
                break
        if len(sources) == 3:
            break
    return sources
