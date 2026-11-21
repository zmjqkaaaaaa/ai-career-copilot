import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

from test_code_projects import code_worker


@pytest.mark.skipif(os.getenv("CAREER_PROJECT_BROWSER") != "1", reason="Requires an isolated browser and API server")
def test_code_project_browser():
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    email = f"mentor-browser-{uuid4().hex}@example.com"
    password = "CareerMentor-Browser42"
    with sync_playwright() as runner:
        channel = os.getenv("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page(viewport={"width": 1250, "height": 900})
        page.goto(f"{base}/project-workspace")
        expect(page).to_have_url(f"{base}/login")
        page.get_by_role("link", name="去注册").click()
        page.get_by_label("用户名").fill("合成代码学习")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/project-workspace")

        def send_and_finish(label):
            with page.expect_response(lambda res: res.status == 202 and "/api/v1/code-projects" in res.url):
                page.get_by_role("button", name=label, exact=True).click()
            code_worker()

        def study(label):
            page.get_by_role("button", name=label, exact=True).click()
            expect(page.get_by_role("heading", name="核对发送内容")).to_be_visible()
            send_and_finish("同意发送并执行")

        page.get_by_label("公开 GitHub 仓库地址").fill("https://github.com/school/course")
        send_and_finish("导入仓库")
        expect(page.get_by_role("heading", name="技术栈与静态索引")).to_be_visible()
        page.reload()
        expect(page.get_by_role("heading", name="技术栈与静态索引")).to_be_visible()
        page.get_by_role("button", name="代码阅读", exact=True).click()
        page.get_by_role("button", name="main.py 已读取").click()
        expect(page.get_by_label("带行号的源代码")).to_contain_text("def compute")
        page.get_by_label("选择函数或类").select_option("compute")
        study("预览代码解释")
        expect(page.get_by_text("调用说明 · 代码可见")).to_be_visible()
        page.get_by_role("button", name="知识库", exact=True).click()
        page.get_by_label("搜索文件、函数或模块").fill("twice")
        page.get_by_role("button", name="搜索当前版本").click()
        expect(page.get_by_text("[1] main.py", exact=False).first).to_be_visible()
        page.get_by_role("button", name="AI 导师", exact=True).click()
        page.get_by_label("我的问题").fill("compute 如何调用 twice？")
        study("预览导师提问")
        expect(page.get_by_role("heading", name="compute 如何调用 twice？")).to_be_visible()
        page.get_by_role("button", name="理解测试", exact=True).click()
        study("预览生成题目")
        expect(page.get_by_text("compute 为什么调用 twice？")).to_be_visible()
        expect(page.get_by_text("参考内容仅在评分后返回")).to_have_count(0)
        page.get_by_label("我的答案").fill("调用 twice 后返回。")
        study("预览提交答案")
        expect(page.get_by_text("本题得分 · 75 / 100")).to_be_visible()
        page.get_by_role("button", name="掌握报告", exact=True).click()
        expect(page.get_by_text("已通过本维度测验 · 最高 75 分")).to_be_visible()
        page.get_by_label("我的掌握情况").fill("会画函数调用顺序")
        page.get_by_role("button", name="保存自述").click()
        expect(page.get_by_text("用户自述 · 会画函数调用顺序")).to_be_visible()
        browser.close()
