from app.core.errors import ApiError

def rank_projects(output, weekly_hours: int | None):
    projects = [item.model_dump() for item in output.projects]
    if len({item["direction"] for item in projects}) != len(projects) or len({item["name"].strip().casefold() for item in projects}) != len(projects):
        raise ApiError(502, "DISCOVERY_PROJECTS_TOO_SIMILAR", "项目方向重复，可重新生成")
    signatures = {(tuple(sorted(item["features"])), item["deliverable"]) for item in projects}
    if len(signatures) < len(projects):
        raise ApiError(502, "DISCOVERY_PROJECTS_TOO_SIMILAR", "项目功能和交付物重复，可重新生成")
    weeks = 4
    for item in projects:
        item["budget_fit"] = None if not weekly_hours else item["estimated_hours"] <= weeks * weekly_hours
        item["estimated_weeks"] = round(item["estimated_hours"] / weekly_hours, 1) if weekly_hours else None
    return sorted(projects, key=lambda item: (item["budget_fit"] is False, item["estimated_hours"]))
