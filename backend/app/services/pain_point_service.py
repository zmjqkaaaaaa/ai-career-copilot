from app.ai.evidence import redact_text

def validate_pains(result, messages):
    sources = {item["id"]: item["text"] for item in messages if item["role"] == "user"}
    for pain in result.pain_points:
        pain.validation_status = "hypothesis"
        pain.evidence = [item for item in pain.evidence
                         if item.kind != "market_inference" and item.detail in sources.get(item.message_id, "")]
        if not pain.evidence:
            pain.confidence = "low"
    return result

def evidence_entries(pain: dict) -> dict:
    entries = {}
    for index, item in enumerate(pain.get("evidence", []), 1):
        entries[f"pain:{index}"] = {**item, "detail": redact_text(item["detail"])}
    return entries
