from typing import Any


def clean_text(value: Any) -> str:
    return ' '.join(str(value).split()).strip()


async def apply_browser_stealth(context, page, platform: str = '', logger=None) -> None:
    normalized_platform = clean_text(platform).upper()

    try:
        await context.set_extra_http_headers(
            {
                'Accept-Language': 'en-US,en;q=0.9',
                'Upgrade-Insecure-Requests': '1',
                'Sec-CH-UA-Platform': '"Windows"',
                'Sec-CH-UA-Mobile': '?0',
            }
        )
    except Exception:
        pass

    try:
        await page.set_viewport_size({'width': 1440, 'height': 900})
    except Exception:
        pass

    try:
        from playwright_stealth import Stealth

        stealth = Stealth()
        apply_method = getattr(stealth, 'apply_stealth_async', None)
        if callable(apply_method):
            await apply_method(context)
    except Exception as exc:
        if logger is not None:
            logger.debug(
                "浏览器 Stealth 增强未启用: platform=%s error=%s",
                normalized_platform or 'UNKNOWN',
                exc,
            )

    try:
        await page.add_init_script(
            """
            (() => {
              const override = (obj, key, value) => {
                try {
                  Object.defineProperty(obj, key, { get: () => value, configurable: true });
                } catch (e) {}
              };
              override(navigator, 'webdriver', undefined);
              override(navigator, 'language', 'en-US');
              override(navigator, 'languages', ['en-US', 'en']);
              override(navigator, 'platform', 'Win32');
              override(navigator, 'hardwareConcurrency', 8);
              override(navigator, 'deviceMemory', 8);
              override(navigator, 'maxTouchPoints', 0);
              override(navigator, 'vendor', 'Google Inc.');
              override(screen, 'colorDepth', 24);
              override(screen, 'pixelDepth', 24);
              override(window, 'innerWidth', 1440);
              override(window, 'innerHeight', 900);
              override(window, 'outerWidth', 1440);
              override(window, 'outerHeight', 980);
              if (!window.chrome) {
                Object.defineProperty(window, 'chrome', {
                  value: { runtime: {}, app: {}, csi: () => {}, loadTimes: () => ({}) },
                  configurable: true,
                });
              }
              if (!navigator.plugins || navigator.plugins.length === 0) {
                Object.defineProperty(navigator, 'plugins', {
                  get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' },
                  ],
                  configurable: true,
                });
              }
              if (!navigator.mimeTypes || navigator.mimeTypes.length === 0) {
                Object.defineProperty(navigator, 'mimeTypes', {
                  get: () => [
                    { type: 'application/pdf' },
                    { type: 'text/pdf' },
                  ],
                  configurable: true,
                });
              }
              const originalQuery = navigator.permissions && navigator.permissions.query;
              if (originalQuery) {
                navigator.permissions.query = (parameters) => (
                  parameters && parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
                );
              }
            })();
            """
        )
    except Exception:
        pass
