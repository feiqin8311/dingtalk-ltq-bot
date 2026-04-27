import asyncio
import json
from pathlib import Path

from logistics_query import (
    clean_text,
    ensure_local_cdp_browser,
    get_local_cdp_endpoint,
)


OUT_DIR = Path("/tmp/track17-debug")


async def main(order_no: str) -> None:
    from playwright.async_api import async_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cdp_process = ensure_local_cdp_browser()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(get_local_cdp_endpoint())
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto("https://www.17track.net/zh-cn", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3500)
            await page.screenshot(path=str(OUT_DIR / "01-open.png"), full_page=True)

            textarea = page.locator("textarea#auto-size-textarea").first
            await textarea.wait_for(state="visible", timeout=30000)
            await textarea.click()
            await textarea.fill(clean_text(order_no))
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUT_DIR / "02-filled.png"), full_page=True)

            search_button = page.locator("div.batch_track_search-area__9BaOs").first
            await search_button.wait_for(state="visible", timeout=15000)
            await search_button.click()
            await page.wait_for_timeout(5000)
            await page.screenshot(path=str(OUT_DIR / "03-after-click.png"), full_page=True)

            body_text = await page.locator("body").inner_text()
            body_html = await page.locator("body").inner_html()
            debug_info = {
                "url": page.url,
                "title": await page.title(),
                "body_excerpt": body_text[:6000],
                "html_excerpt": body_html[:15000],
            }
            (OUT_DIR / "result.json").write_text(json.dumps(debug_info, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(debug_info, ensure_ascii=False, indent=2))
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            if cdp_process is not None:
                cdp_process.terminate()
                try:
                    cdp_process.wait(timeout=5)
                except Exception:
                    cdp_process.kill()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: debug_17track.py <tracking_no>")
    asyncio.run(main(sys.argv[1]))
