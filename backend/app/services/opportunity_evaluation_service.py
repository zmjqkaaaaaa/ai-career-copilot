WEIGHTS = {
    "demand": 15, "frequency": 10, "current_cost": 10, "competitive_gap": 10,
    "differentiation": 10, "feasibility": 10, "personal_fit": 10, "portfolio": 10, "role_fit": 15,
}
LABELS = {
    "demand": "用户需求强度", "frequency": "问题频率", "current_cost": "现有解决成本",
    "competitive_gap": "竞品覆盖缺口", "differentiation": "差异化空间", "feasibility": "技术可行性",
    "personal_fit": "开发能力适配", "portfolio": "项目展示价值", "role_fit": "岗位相关性",
}
VERSION = "opportunity-v1"
DIRECT = {"experience", "observation"}
EVIDENCE_FOR = {
    "demand": DIRECT, "frequency": DIRECT, "current_cost": DIRECT,
    "competitive_gap": {"market_source"}, "differentiation": {"market_source"},
    "feasibility": {"market_source", "ability"}, "personal_fit": {"ability"},
    "portfolio": {"ability", "job_match"}, "role_fit": {"job_match"},
}

def evaluate(opportunity, evidence: dict) -> dict:
    records = {}
    for item in opportunity.ratings:
        records.setdefault(item.dimension, item)
    total, score, rows = 0, 0.0, []
    for key, weight in WEIGHTS.items():
        row = records[key].model_dump() if key in records else {
            "dimension": key, "rating": None, "basis": "unknown", "reason": "缺少可用资料", "references": [],
        }
        row["references"] = [reference for reference in row["references"] if reference in evidence]
        reason_types = {evidence[reference].get("kind") for reference in row["references"]}
        if row["basis"] == "evidence" and not reason_types & EVIDENCE_FOR[key]:
            row["basis"] = "unknown"
        if row["basis"] == "unknown":
            row["rating"] = None
        if row["basis"] == "evidence" and row["rating"] is not None:
            total += weight
            score += weight * row["rating"] / 4
        rows.append({**row, "weight": weight, "label": LABELS[key]})
    return {**opportunity.model_dump(exclude={"ratings"}), "ratings": rows,
            "score": round(100 * score / total, 2) if total else None, "coverage": total,
            "version": VERSION, "evidence": evidence}
