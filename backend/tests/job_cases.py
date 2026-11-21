"""Synthetic JDs and independently calculated reference outcomes."""
def requirement(name, category="data", importance="required", kind="skill", quote=None):
    return {"name": name, "category": category, "importance": importance, "kind": kind,
            "quote": quote or f"必须掌握 {name}"}

def skill(status, level="基础"):
    return {"status": status, "level": level, "sources": [{"quote": "合成证据"}]}

SQL = requirement("SQL")
RAG = requirement("RAG", "ai")
PRODUCT = requirement("产品思维", "product")
DEGREE = requirement("本科", "education", kind="degree", quote="本科及以上")
YEAR = requirement("毕业年份", "education", kind="graduation_year", quote="2027至2028年毕业")
PREFERRED = requirement("Python", importance="preferred", quote="了解 Python 者优先")

CASES = [
    ("01-covered", [SQL], {"skills": {"sql": skill("verified")}}, {}, (100, 100)),
    ("02-self", [SQL], {"skills": {"sql": skill("self_reported")}}, {}, (80, 100)),
    ("03-inferred", [RAG], {"skills": {"rag": skill("inferred")}}, {}, (50, 100)),
    ("04-unknown", [SQL], {}, {}, (None, 0)),
    ("05-preferred", [SQL, PREFERRED], {"skills": {"sql": skill("verified")}}, {}, (100, 100)),
    ("06-year-conflict", [SQL, YEAR], {"skills": {"sql": skill("verified")}, "graduation_year": 2029}, {}, (60, 100)),
    ("07-degree", [DEGREE], {"degrees": ["本科"]}, {}, (80, 100)),
    ("08-mixed", [PRODUCT, SQL, RAG], {"skills": {"产品思维": skill("verified"), "sql": skill("self_reported")}}, {}, (92.5, 61.54)),
    ("09-explicit-lack", [SQL], {}, {0: "not_capable"}, (0, 100)),
    ("10-no-proof", [SQL, PREFERRED], {"skills": {"sql": skill("verified")}}, {0: "no_evidence"}, (None, 0)),
]
