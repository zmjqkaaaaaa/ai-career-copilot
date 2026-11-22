import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

@pytest.mark.skipif(not os.environ.get("CAREER_E2E_URL"), reason="Set CAREER_E2E_URL to the running test frontend")
def test_registration_dashboard_profile_refresh_and_logout():
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    email = f"browser-{uuid4().hex}@example.com"
    username = "浏览器验收用户"
    password = "CareerBrowserTest-42"
    with sync_playwright() as runner:
        kwargs = {"channel": os.environ["CAREER_BROWSER_CHANNEL"]} if os.environ.get("CAREER_BROWSER_CHANNEL") else {}
        browser = runner.chromium.launch(**kwargs)
        page = browser.new_page()
        page.goto(f"{base}/profile")
        expect(page.get_by_role("heading", name="登录", exact=True)).to_be_visible()
        page.goto(f"{base}/register")
        page.get_by_label("用户名").fill(username)
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        expect(page.get_by_label("邮箱")).to_have_value(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/")
        expect(page.get_by_role("heading", name=f"你好，{username} AI Career Copilot")).to_be_visible()
        expect(page.get_by_text("个人档案 · 待填写", exact=True)).to_be_visible()
        assert "career_access" not in page.evaluate("document.cookie")
        auth_cookie = next(cookie for cookie in page.context.cookies() if cookie["name"] == "career_access")
        assert auth_cookie["httpOnly"] and auth_cookie["path"] == "/api/v1"
        page.reload()
        expect(page.get_by_role("heading", name=f"你好，{username} AI Career Copilot")).to_be_visible()
        page.get_by_role("link", name="查看个人档案").click()
        expect(page.get_by_text("尚未创建档案。填写你想记录的信息即可保存。")).to_be_visible()
        page.get_by_label("目标岗位").fill("AI 产品经理")
        page.get_by_label("本科院校").fill("测试大学")
        page.get_by_label("技能", exact=True).fill("Python，SQL")
        page.get_by_role("button", name="添加项目经历").click()
        page.get_by_label("项目经历 1 名称").fill("求职助手演示")
        page.get_by_role("button", name="保存档案").click()
        expect(page.get_by_text("个人档案已保存。")).to_be_visible()
        page.reload()
        expect(page.get_by_label("本科院校")).to_have_value("测试大学")
        expect(page.get_by_label("项目经历 1 名称")).to_have_value("求职助手演示")
        page.get_by_label("目标岗位").fill("AI Agent 产品经理")
        page.get_by_role("button", name="保存档案").click()
        expect(page.get_by_text("个人档案已保存。")).to_be_visible()
        page.get_by_role("navigation", name="主导航").get_by_role("link", name="求职驾驶舱").click()
        expect(page.get_by_role("main").get_by_text("AI Agent 产品经理", exact=True)).to_be_visible()
        expect(page.get_by_text("个人档案 · 已创建", exact=True)).to_be_visible()
        expect(page.get_by_text("测评已验证 · 0 项", exact=True)).to_be_visible()
        expect(page.get_by_text("用户自述 · 2 项", exact=True)).to_be_visible()
        expect(page.get_by_text("今日暂无已安排任务。", exact=False)).to_be_visible()
        expect(page.get_by_text("演示任务", exact=True)).to_have_count(0)
        page.set_viewport_size({"width": 768, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth")
        page.get_by_role("button", name="打开导航").click()
        page.get_by_role("button", name="退出登录").click()
        expect(page).to_have_url(f"{base}/login")
        assert not any(cookie["name"] == "career_access" for cookie in page.context.cookies())
        page.goto(f"{base}/profile")
        expect(page).to_have_url(f"{base}/login")
        browser.close()
