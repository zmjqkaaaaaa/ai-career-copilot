import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

from test_jobs import JD, seed_candidate

@pytest.mark.skipif(os.environ.get("CAREER_LIVE_JOB_E2E") != "1", reason="Opt in to real model testing with synthetic job data")
def test_live_job_flow():
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    email = f"job-browser-{uuid4().hex}@example.com"
    password = "CareerJobBrowser-42"
    with sync_playwright() as runner:
        channel = os.environ.get("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page()
        page.goto(f"{base}/job-matching")
        expect(page).to_have_url(f"{base}/login")
        page.get_by_role("link", name="去注册").click()
        page.get_by_label("用户名").fill("合成岗位验收")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        seed_candidate(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/job-matching")
        page.get_by_label("岗位名称").fill("AI 产品实习生")
        page.get_by_label("公司名称").fill("星河科技")
        page.get_by_label("导入 JD 文件").set_input_files({"name":"job.txt","mimeType":"text/plain","buffer":JD.encode()})
        expect(page.get_by_label("JD 文本")).to_have_value(JD)
        page.get_by_role("button", name="保存岗位").click()
        page.get_by_role("button", name="解析 JD").click()
        expect(page.get_by_role("heading", name="核对发送内容")).to_be_visible()
        page.get_by_role("button", name="同意发送并执行").click()
        expect(page.get_by_text("负责用户访谈", exact=False).first).to_be_visible(timeout=90_000)
        page.get_by_role("button", name="确认岗位要求").click()
        page.get_by_role("button", name="计算匹配").click()
        expect(page.get_by_role("heading", name="匹配报告")).to_be_visible()
        expect(page.get_by_text("100 / 100")).to_be_visible()
        expect(page.get_by_role("heading", name="能力差距详情")).to_be_visible()
        advice = page.get_by_role("region", name="求职建议")
        advice.get_by_role("button", name="生成 AI 求职建议").click()
        expect(advice.get_by_role("heading", name="核对发送内容")).to_be_visible()
        advice.get_by_role("button", name="同意发送并执行").click()
        expect(advice.get_by_role("heading", name="下一步行动")).to_be_visible(timeout=90_000)
        page.get_by_role("button", name="历史匹配", exact=True).click()
        expect(page.get_by_role("heading", name="历史匹配记录")).to_be_visible()
        page.get_by_role("button", name="AI 产品实习生", exact=False).click()
        expect(page.get_by_role("heading", name="匹配报告")).to_be_visible()
        page.get_by_role("button", name="删除岗位", exact=True).click()
        page.get_by_role("button", name="确认删除岗位").click()
        expect(page.get_by_text("还没有岗位。")).to_be_visible()
        browser.close()
