import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import select

from app.db.session import session_factory
from app.models.user import User
from app.models.user_profile import UserProfile
from test_discovery import worker


@pytest.mark.skipif(os.getenv("CAREER_DISCOVERY_BROWSER") != "1", reason="Requires isolated Vite and API servers")
def test_discovery_browser(tmp_path):
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    email = f"discovery-browser-{uuid4().hex}@example.com"
    password = "CareerBrowser-Discovery42"
    with sync_playwright() as runner:
        channel = os.environ.get("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page(accept_downloads=True)
        page.goto(f"{base}/interest-exploration")
        page.get_by_role("link", name="去注册").click()
        page.get_by_label("用户名").fill("合成探索验收")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        with session_factory().begin() as db:
            user = db.scalar(select(User).where(User.email == email))
            db.add(UserProfile(user_id=user.id, undergraduate_major="信息管理",
                               interested_industries=[], skills=["SQL"],
                               internship_experience=[], project_experience=[]))
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/interest-exploration")
        page.get_by_label("新会话名称").fill("合成探索会话")
        page.get_by_role("button", name="创建探索会话").click()

        def execute(label):
            page.get_by_role("button", name=label, exact=True).click()
            expect(page.get_by_role("heading", name="核对发送内容")).to_be_visible()
            with page.expect_response(lambda response: response.status == 202 and response.request.method == "POST"):
                page.get_by_role("button", name="同意发送并执行").click()
            worker()

        page.get_by_label("我的回答").fill("我在合成练习中用表格整理了三小时的巡检日志。")
        execute("预览并发送本轮")
        expect(page.get_by_text("当时用了哪些工具？")).to_be_visible()
        page.reload()
        expect(page.get_by_text("当时用了哪些工具？")).to_be_visible()
        page.get_by_role("button", name="痛点工作台").click()
        execute("从对话提取痛点")
        expect(page.get_by_role("heading", name="痛点证据与访谈")).to_be_visible()
        page.get_by_role("button", name="市场研究", exact=True).click()
        page.get_by_text("补录公开资料（0）").click()
        page.get_by_label("来源网址").fill("https://example.com/synthetic")
        page.get_by_label("来源标题").fill("合成市场资料")
        page.get_by_label("相关原文").fill("支持记录检索")
        page.get_by_label("资料类型").select_option("official")
        page.get_by_role("button", name="添加资料").click()
        execute("预览并分析补录资料")
        expect(page.get_by_text("合成竞品", exact=False).first).to_be_visible()
        page.get_by_role("button", name="机会评估", exact=True).click()
        execute("预览机会评估")
        expect(page.get_by_text("证据覆盖率 15%", exact=False)).to_be_visible()
        page.get_by_role("link", name="进入项目推荐").click()
        execute("预览项目推荐")
        expect(page.get_by_role("button", name="选定项目", exact=True)).to_have_count(3)
        page.get_by_role("button", name="比较当前方案").click()
        expect(page.get_by_role("table")).to_be_visible()
        page.get_by_role("button", name="选定项目", exact=True).first.click()
        execute("预览 PRD 生成")
        prd = page.get_by_label("PRD 正文")
        expect(prd).to_be_visible()
        prd.fill(prd.input_value() + "\n\n浏览器保存验收。")
        page.get_by_role("button", name="保存新版本").click()
        expect(page.get_by_label("PRD 历史版本").locator("option").first).to_contain_text("第 2 版")
        with page.expect_download() as download:
            page.get_by_role("button", name="导出 Markdown").click()
        exported = tmp_path / "export.md"
        download.value.save_as(exported)
        assert "浏览器保存验收。" in exported.read_text(encoding="utf-8")
        browser.close()
