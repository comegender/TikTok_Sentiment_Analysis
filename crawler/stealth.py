"""Fingerprint spoofing and anti-detection measures.

Applies playwright-stealth plus additional evasions specific to Douyin.
"""

from playwright.sync_api import Page


def apply_stealth(page: Page):
    """Apply all anti-detection measures to a page."""
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        pass
    _inject_evasions(page)


def _inject_evasions(page: Page):
    page.add_init_script("""
    // ── navigator properties ──
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

    // ── chrome object ──
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {}
    };

    // ── permissions ──
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );

    // ── remove automation flags ──
    delete Object.getPrototypeOf(navigator).webdriver;

    // ── mock plugins array properly ──
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
            ];
            plugins.item = (i) => plugins[i];
            plugins.namedItem = (name) => plugins.find(p => p.name === name);
            plugins.refresh = () => {};
            Object.setPrototypeOf(plugins, PluginArray.prototype);
            return plugins;
        }
    });

    // ── WebGL vendor spoof ──
    const getParameterProxies = {
        WebGLRenderingContext: new Proxy(WebGLRenderingContext.prototype.getParameter, {
            apply(target, self, args) {
                const param = args[0];
                // UNMASKED_VENDOR_WEBGL
                if (param === 37445) return 'Intel Inc.';
                // UNMASKED_RENDERER_WEBGL
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return Reflect.apply(target, self, args);
            }
        }),
        WebGL2RenderingContext: new Proxy(WebGL2RenderingContext.prototype.getParameter, {
            apply(target, self, args) {
                const param = args[0];
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return Reflect.apply(target, self, args);
            }
        })
    };
    """)
