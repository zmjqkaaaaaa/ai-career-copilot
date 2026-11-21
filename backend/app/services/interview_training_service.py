from datetime import timedelta

from sqlalchemy import select

from app.models.interview import InterviewReport, InterviewSession, InterviewTrainingTask
from app.services.resumes import utc_now


def make_tasks(db, session, report, turns):
    previous = db.scalars(select(InterviewReport).join(InterviewSession).where(
        InterviewSession.user_id == session.user_id, InterviewSession.target == session.target,
        InterviewSession.id != session.id).order_by(InterviewReport.id.desc()).limit(5))
    repeated = {item.get("knowledge_point") for prior in previous for item in prior.data.get("weaknesses", [])}
    needs = [row for row in turns if row["score"] is None or row["score"] < 80 or row["coverage"] < 50]
    ranked = sorted(needs or turns, key=lambda row: (row["knowledge_point"] not in repeated,
                                                   row["score"] if row["score"] is not None else -1))
    seen = set()
    for turn in ranked:
        topic = turn["knowledge_point"]
        if topic in seen:
            continue
        seen.add(topic)
        db.add(InterviewTrainingTask(report_id=report.id, due_at=utc_now() + timedelta(days=len(seen) + 1),
              data={"title": f"复练 · {topic}", "knowledge_point": topic, "target": session.target,
                    "priority": "high" if topic in repeated or (turn["score"] or 0) < 60 else "normal",
                    "description": turn["exercise"], "acceptance": turn["acceptance"], "review_question": turn["question"],
                    "next_goal": f"下次面试能用一个可核对的例子说明「{topic}」"}))
        if len(seen) == 4:
            break
    if not seen:
        db.add(InterviewTrainingTask(report_id=report.id, due_at=utc_now() + timedelta(days=2),
              data={"title": "完成一次完整作答", "knowledge_point": "面试准备", "target": session.target,
                    "priority": "normal", "description": "选择一个岗位并用文字回答至少一道相关问题",
                    "acceptance": "复盘中出现一条已完成作答记录", "review_question": "你会怎样介绍自己和目标岗位的关系？",
                    "next_goal": "建立一条可用于比较的面试记录"}))
