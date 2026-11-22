import os

import pytest
from playwright.sync_api import expect, sync_playwright

from conftest import PASSWORD

API = "/api/v1/dashboard"


def test_dashboard_requires_login_and_distinguishes_empty_records(client, bearer_headers):
    assert client.get(API).status_code == 401
    headers = bearer_headers()
    invalid = client.get(API, headers=headers, params={"day": "2026-02-30"})
    assert invalid.status_code == 422
    response = client.get(API, headers=headers, params={"day": "2026-11-21"})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert data["day"] == "2026-11-21"
    assert data["target_position"] is None and not data["profile_complete"]
    assert data["match"] is None and data["interview"] is None
    assert data["tasks"] == data["projects"] == [] and data["applications"] == {}
    assert data["skills"]["verified"] == 0 and data["skills"]["unknown"] > 0
    assert data["next_action"]["kind"] == "profile"


@pytest.mark.skipif(not os.getenv("CAREER_SPRINT6_BROWSER"), reason="Requires isolated browser servers")
def test_dashboard_error_recovery_and_mobile_navigation(register_account):
    email, _ = register_account("移动端验收")
    base = os.environ["CAREER_SPRINT6_BROWSER"].rstrip("/")
    with sync_playwright() as runner:
        channel = os.getenv("CAREER_BROWSER_CHANNEL")
        browser = runner.chromium.launch(**({"channel": channel} if channel else {}))
        page = browser.new_page(viewport={"width": 360, "height": 780})
        page.goto(base + "/")
        expect(page.get_by_role("link", name="登录查看我的进展")).to_be_visible()
        expect(page.get_by_text("演示数据")).to_have_count(0)
        page.get_by_role("link", name="登录查看我的进展").click()
        page.get_by_label("邮箱").fill(email)
        page.get_by_label("密码").fill(PASSWORD)
        page.route("**/api/v1/dashboard?*", lambda route: route.fulfill(
            status=503, json={"error": {"code": "TEST_UNAVAILABLE", "message": "测试连接中断"}}
        ))
        page.get_by_role("button", name="登录", exact=True).click()
        expect(page.get_by_role("alert")).to_have_text("测试连接中断")
        page.unroute("**/api/v1/dashboard?*")
        page.get_by_role("button", name="重试", exact=True).click()
        expect(page.get_by_text("暂无已完成的模拟面试报告。")).to_be_visible()
        expect(page.get_by_text("暂无投递记录。", exact=False)).to_be_visible()
        for width in (360, 390, 820, 1280):
            page.set_viewport_size({"width": width, "height": 780})
            assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth"), width
        page.set_viewport_size({"width": 360, "height": 780})
        page.get_by_role("button", name="打开导航").click()
        nav = page.get_by_role("navigation", name="主导航")
        expect(nav.get_by_role("link", name="求职驾驶舱")).to_be_focused()
        page.keyboard.press("Escape")
        expect(page.get_by_role("button", name="打开导航")).to_be_focused()
        page.get_by_role("button", name="打开导航").click()
        nav.get_by_role("link", name="成长中心").click()
        expect(page).to_have_url(base + "/growth")
        expect(page.get_by_role("button", name="打开导航")).to_have_attribute("aria-expanded", "false")
        page.get_by_role("button", name="打开导航").click()
        expect(nav.get_by_role("link", name="成长中心")).to_have_attribute("aria-current", "page")
        page.keyboard.press("Escape")
        page.goto(base + "/")
        expect(page.get_by_role("heading", name="你好，移动端验收 AI Career Copilot")).to_be_visible()
        page.reload()
        expect(page.get_by_text("暂无投递记录。", exact=False)).to_be_visible()
        browser.close()
