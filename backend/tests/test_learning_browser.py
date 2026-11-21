import os
from uuid import uuid4

import pytest
from playwright.sync_api import expect, sync_playwright

from test_learning import process


@pytest.mark.skipif(os.getenv("CAREER_LEARNING_BROWSER") != "1", reason="Requires isolated browser and API servers")
def test_learning_browser():
    base = os.environ["CAREER_E2E_URL"].rstrip("/")
    email = f"learning-browser-{uuid4().hex}@example.com"
    password = "CareerLearning-Browser42"
    with sync_playwright() as runner:
        channel = os.getenv("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{base}/growth")
        expect(page).to_have_url(f"{base}/login")
        page.get_by_role("link", name="去注册").click()
        page.get_by_label("用户名").fill("成长导师验收")
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="注册账户", exact=True).click()
        expect(page.get_by_text("注册成功，请登录。")).to_be_visible()
        page.get_by_label("密码").fill(password)
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page).to_have_url(f"{base}/growth")
        page.get_by_role("button", name="制定学习路线").click()
        page.get_by_label("学习目标或兴趣").fill("Python")
        page.get_by_role("button", name="生成学习路线", exact=True).click()
        expect(page.get_by_label("路线版本")).to_be_visible()
        page.get_by_role("button", name="每日任务", exact=True).click()
        page.get_by_role("button", name="开始任务", exact=True).click()
        page.get_by_label("实际学习时间（分钟）").fill("10")
        page.get_by_role("button", name="记录完成", exact=True).click()
        expect(page.get_by_role("heading", name="Python 基础与数据处理 · 已完成")).to_be_visible()
        page.get_by_role("button", name="AI 导师", exact=True).click()
        page.get_by_role("button", name="新建教学会话").click()
        page.get_by_label("给导师的话").fill("我先根据岗位分组。")
        page.get_by_role("button", name="预览教学对话").click()
        expect(page.get_by_role("heading", name="核对发送内容")).to_be_visible()
        with page.expect_response(lambda response: response.status == 202 and "/learning/" in response.url):
            page.get_by_role("button", name="同意发送并执行").click()
        process()
        expect(page.get_by_text("哪一列用于分组？", exact=False)).to_be_visible()
        page.reload()
        expect(page.get_by_text("哪一列用于分组？", exact=False)).to_be_visible()
        page.get_by_role("button", name="保存为学习笔记").click()
        expect(page.get_by_role("heading", name="Python 基础与数据处理 · 导师笔记")).to_be_visible()
        page.get_by_role("button", name="作业中心", exact=True).click()
        page.get_by_label("提交内容").fill("先根据岗位分组，说明输入。")
        page.get_by_role("button", name="保存作业版本").click()
        page.get_by_role("button", name="预览 AI 作业评估").click()
        with page.expect_response(lambda response: response.status == 202 and "/learning/" in response.url):
            page.get_by_role("button", name="同意发送并执行").click()
        process()
        expect(page.get_by_text("缺少缺失值用例", exact=False)).to_be_visible()
        page.get_by_role("button", name="阶段测评", exact=True).click()
        page.get_by_role("button", name="开始或恢复测评").click()
        page.get_by_role("radio", name="row.get('score', 0)", exact=True).check()
        page.get_by_role("radio", name="value is None", exact=True).check()
        page.get_by_role("button", name="提交测评").click()
        expect(page.get_by_text("测评结果 · 100 分 · 首次测评")).to_be_visible()
        page.get_by_role("button", name="成长报告", exact=True).click()
        expect(page.get_by_text("学习时长 10 分钟", exact=False)).to_be_visible()
        expect(page.get_by_text("已通过阶段测评", exact=False).first).to_be_visible()
        browser.close()

