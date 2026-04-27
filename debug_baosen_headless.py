import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

from logistics_query import load_env


load_env()

BAOSEN_URL = os.environ.get(
    "BAOSEN_URL",
    "https://www.baosencloud.com/orderManage/eCommerce/firstTransportDetails?type=2",
)
BAOSEN_USERNAME = os.environ["BAOSEN_USERNAME"]
BAOSEN_PASSWORD = os.environ["BAOSEN_PASSWORD"]
CHROME_BIN = os.environ.get("LOCAL_CDP_BROWSER_BIN") or "/usr/bin/google-chrome"
OUT_DIR = Path("/tmp/baosen-headless-debug")


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        responses: list[dict[str, object]] = []
        browser = await playwright.chromium.launch(
            executable_path=CHROME_BIN,
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "response",
            lambda response: responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "ok": response.ok,
                }
            ),
        )
        await page.goto(BAOSEN_URL, wait_until="networkidle")
        await page.screenshot(path=str(OUT_DIR / "01-open.png"), full_page=True)

        username_input = page.locator('input[placeholder="请输入账号"]').first
        password_input = page.locator('input[placeholder="请输入密码"]').first
        remember_checkbox = page.locator("span.el-checkbox__inner").first
        login_button = page.get_by_role("button", name="登录").first

        result: dict[str, object] = {
            "url_before": page.url,
            "title": await page.title(),
            "username_input_count": await page.locator('input[placeholder="请输入账号"]').count(),
            "password_input_count": await page.locator('input[placeholder="请输入密码"]').count(),
        }

        if await username_input.count() > 0:
            await username_input.fill(BAOSEN_USERNAME)
            await password_input.fill(BAOSEN_PASSWORD)
            if await remember_checkbox.count() > 0:
                await remember_checkbox.click()

            await page.screenshot(path=str(OUT_DIR / "02-filled.png"), full_page=True)
            result["login_button_text"] = (await login_button.inner_text()).strip()
            result["login_button_enabled"] = await login_button.is_enabled()
            result["login_button_visible"] = await login_button.is_visible()
            try:
                await login_button.click(timeout=5000)
                result["click_result"] = "normal_click_ok"
            except Exception as exc:
                result["click_result"] = f"normal_click_failed: {exc}"
                try:
                    await login_button.click(force=True, timeout=5000)
                    result["click_result"] = "force_click_ok"
                except Exception as force_exc:
                    result["force_click_result"] = f"force_click_failed: {force_exc}"
                    await login_button.evaluate("(node) => node.click()")
                    result["click_result"] = "dom_click_ok"

            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(OUT_DIR / "03-after-click.png"), full_page=True)

            result["url_after"] = page.url
            result["body_excerpt"] = (await page.locator("body").inner_text())[:4000]
            result["responses"] = [
                item
                for item in responses
                if "baosencloud.com" in str(item["url"]) or "login" in str(item["url"])
            ][-20:]

            errors: list[dict[str, object]] = []
            for selector in [
                ".el-message",
                ".el-form-item__error",
                ".el-message-box__wrapper",
                ".el-notification",
                '[role="alert"]',
            ]:
                locator = page.locator(selector)
                count = await locator.count()
                texts: list[str] = []
                for index in range(min(count, 5)):
                    try:
                        text = (await locator.nth(index).inner_text()).strip()
                    except Exception:
                        text = ""
                    if text:
                        texts.append(text)
                if texts:
                    errors.append({"selector": selector, "texts": texts})
            result["errors"] = errors

        print(json.dumps(result, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
