import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

from test_interviews import seed, worker


@pytest.mark.skipif(os.getenv("CAREER_INTERVIEW_BROWSER") != "1", reason="Requires isolated browser and API servers")
def test_interview_browser():
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    email = f"interview-browser-{uuid4().hex}@example.com"
    password = "CareerInterview-Browser42"
    with sync_playwright() as runner:
        channel = os.getenv("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{base}/interview-practice")
        expect(page).to_have_url(f"{base}/login")
        page.get_by_role("link", name="去注册").click()
        page.get_by_label("用户名").fill("合成面试验收")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        seed(email, "信息管理", "SQL", "在合成练习中分析数据")
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/interview-practice")
        page.get_by_role("button", name="核对面试准备").click()
        page.get_by_role("button", name="创建面试", exact=True).click()

        def step(label):
            page.get_by_role("button", name=label, exact=True).click()
            expect(page.get_by_role("heading", name="核对发送内容")).to_be_visible()
            with page.expect_response(lambda response: response.status == 202 and "/interviews/" in response.url):
                page.get_by_role("button", name="同意发送并执行").click()
            worker()

        step("预览并开始面试")
        expect(page.get_by_role("heading", name="当前问题")).to_be_visible()
        expect(page.get_by_text("教学提示 · 先说一个具体例子")).to_have_count(0)
        page.get_by_label("我的回答").fill("我先确认输入的字段，再做测试。")
        step("预览并提交回答")
        expect(page.get_by_role("heading", name="动态追问")).to_be_visible()
        page.reload()
        expect(page.get_by_role("heading", name="动态追问")).to_be_visible()
        expect(page.get_by_text("辅助练习参考分", exact=False)).to_have_count(0)
        page.get_by_role("button", name="结束面试", exact=True).click()
        page.get_by_role("button", name="确认结束并查看报告").click()
        expect(page.get_by_role("heading", name="面试复盘", exact=False)).to_be_visible()
        expect(page.get_by_text("辅助练习参考分 · 75 / 100", exact=False)).to_be_visible()
        page.get_by_role("button", name="面试历史", exact=True).click()
        page.get_by_role("button", name="查看历史报告").click()
        expect(page.get_by_role("heading", name="逐题复盘")).to_be_visible()
        page.get_by_role("button", name="训练中心", exact=True).click()
        page.get_by_role("button", name="标记完成").click()
        expect(page.get_by_text("已完成 1 / 1 项")).to_be_visible()
        browser.close()
