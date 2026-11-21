from app.ai.discovery_prompts import RESEARCH as PROMPT
from app.schemas.discovery import ResearchResult

def grounded_claim(claim, sources_by_id):
    if not claim:
        return None
    quote = " ".join((claim.evidence_excerpt or "").split()).casefold()
    if not quote:
        return None
    claim.sources = [source_id for source_id in sorted(set(claim.sources))
                     if source_id in sources_by_id and quote in " ".join(sources_by_id[source_id]["excerpt"].split()).casefold()]
    return claim.model_dump() if claim.sources else None

def analyze_competitors(provider, pain_title, sources):
    found = provider.generate(PROMPT, {"topic": pain_title, "sources": sources}, ResearchResult)
    valid = {item["id"]: item for item in sources}
    official = {item["id"] for item in sources if item["source_type"] == "official"}
    competitors = []
    for candidate in found.competitors:
        item = {"product_name": candidate.product_name,
                "official_source": candidate.official_source if candidate.official_source in official else None}
        for key in type(candidate).model_fields.keys() - {"product_name", "official_source"}:
            item[key] = grounded_claim(getattr(candidate, key), valid)
        if any(value for key, value in item.items() if key not in {"product_name", "official_source"}):
            competitors.append(item)
    return competitors, [item for claim in found.market_findings if (item := grounded_claim(claim, valid))]
