import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

from resume_fixtures import cases, write_case

@pytest.mark.skipif(os.environ.get("CAREER_LIVE_RESUME_E2E") != "1", reason="Opt in to live synthetic resume calls")
def test_live_ai_resume_flow(tmp_path):
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    path = write_case(cases()[1], tmp_path)
    email = f"resume-browser-{uuid4().hex}@example.com"
    password = "CareerResumeBrowser-42"
    with sync_playwright() as runner:
        options = {"channel": os.environ["CAREER_BROWSER_CHANNEL"]} if os.environ.get("CAREER_BROWSER_CHANNEL") else {}
        browser = runner.chromium.launch(**options)
        page = browser.new_page()
        page.goto(f"{base}/career-profile")
        expect(page).to_have_url(f"{base}/login")
        page.get_by_role("link", name="去注册").click()
        page.get_by_label("用户名").fill("合成简历验收")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/career-profile")
        expect(page.get_by_role("heading", name="AI 职业画像")).to_be_visible()
        page.get_by_label("选择简历").set_input_files(path)
        page.get_by_role("button", name="上传简历").click()
        page.get_by_role("button", name="本地解析", exact=True).click()
        expect(page.get_by_role("heading", name="核对将发送给模型的文字")).to_be_visible(timeout=15_000)
        expect(page.get_by_text("candidate@example.com", exact=False)).to_have_count(0)
        page.get_by_role("button", name="同意发送并提取").click()
        expect(page.get_by_role("heading", name="结构化简历")).to_be_visible(timeout=100_000)
        page.get_by_role("button", name="确认结构化简历").click()
        expect(page.get_by_text("已保存结构化简历。")).to_be_visible()
        page.get_by_role("button", name="职业画像", exact=True).click()
        page.get_by_role("button", name="生成职业画像").click()
        expect(page.get_by_role("heading", name="能力证据分布")).to_be_visible(timeout=110_000)
        expect(page.get_by_role("heading", name="SQL", exact=True)).to_be_visible()
        page.set_viewport_size({"width": 768, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth === document.documentElement.clientWidth")
        page.get_by_role("button", name="优化建议", exact=True).click()
        page.get_by_role("button", name="生成优化建议").click()
        save = page.get_by_role("button", name="确认并保存文本版本").first
        expect(save).to_be_visible(timeout=100_000)
        save.click()
        expect(page.get_by_text("已保存为独立文本版本。")).to_be_visible()
        page.get_by_role("button", name="简历管理", exact=True).click()
        page.get_by_role("button", name="删除简历", exact=True).click()
        page.get_by_role("button", name="确认删除", exact=True).click()
        expect(page.get_by_text("还没有上传简历。")).to_be_visible()
        browser.close()
