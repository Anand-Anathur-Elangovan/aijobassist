"""
human.py — Human-like browser interaction utilities.

Replaces rigid time.sleep / page.fill / page.click calls with
natural, randomised equivalents that mimic how a real person:
  • moves the mouse in curved paths (Bézier)
  • types at variable speed with occasional typo + correction
  • pauses to "read" content before interacting
  • randomly scrolls around while thinking
  • jitters the cursor during long waits
  • takes micro-breaks between rapid actions

Usage (in linkedin.py / naukri.py):
    from automation.human import (
        human_sleep, micro_pause, thinking_pause, reading_pause,
        human_mouse_move, human_click, human_type,
        human_scroll_down, idle_jiggle,
    )
"""

import math
import random
import time

from playwright.sync_api import Page, Locator


# ──────────────────────────────────────────────────────────────
# 1. Sleep helpers
# ──────────────────────────────────────────────────────────────

def human_sleep(min_s: float, max_s: float) -> None:
    """Sleep for a random duration in [min_s, max_s] using a slight Gaussian
    bias toward the middle, so it never feels perfectly uniform."""
    mid  = (min_s + max_s) / 2
    sd   = (max_s - min_s) / 6            # ±3σ fits in the range
    secs = random.gauss(mid, sd)
    secs = max(min_s, min(max_s, secs))   # clamp
    time.sleep(secs)


def micro_pause() -> None:
    """Very short keyboard-rhythm pause between key-presses (80–200 ms)."""
    time.sleep(random.uniform(0.08, 0.20))


def thinking_pause() -> None:
    """1.5–5 s pause — user is 'reading' or 'deciding'."""
    time.sleep(random.uniform(1.5, 5.0))


def reading_pause(char_count: int = 300) -> None:
    """
    Pause proportional to content length, simulating reading speed.
    Average reading speed ≈ 200–250 words/min ≈ 1000–1250 chars/min.
    So 300 chars ≈ 14–18 s.  We cap at 20 s and add ±20 % noise.
    """
    base = char_count / 1100.0            # seconds at ~1100 chars/min
    base = max(1.0, min(base, 20.0))      # clamp 1–20 s
    noise = random.uniform(0.8, 1.2)
    time.sleep(base * noise)


# ──────────────────────────────────────────────────────────────
# 2. Bézier mouse movement
# ──────────────────────────────────────────────────────────────

def _bezier_path(
    x0: float, y0: float,
    x1: float, y1: float,
    steps: int = 25,
) -> list[tuple[float, float]]:
    """
    Return `steps` points along a quadratic Bézier curve from (x0,y0) to (x1,y1).
    The control point is shifted randomly off the direct line to add a natural arc.
    """
    # Control point: midpoint + random perpendicular offset
    mx = (x0 + x1) / 2 + random.uniform(-120, 120)
    my = (y0 + y1) / 2 + random.uniform(-80,  80)

    pts: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t   = i / steps
        t2  = t * t
        mt  = 1 - t
        mt2 = mt * mt
        # Quadratic Bézier formula
        px = mt2 * x0 + 2 * mt * t * mx + t2 * x1
        py = mt2 * y0 + 2 * mt * t * my + t2 * y1
        pts.append((px, py))
    return pts


def human_mouse_move(page: Page, target_x: float, target_y: float) -> None:
    """
    Move the mouse from its current position to (target_x, target_y) along
    a Bézier curve, with variable speed (faster in the middle, slower at ends).
    """
    try:
        # Get current mouse pos via JS (Playwright doesn't expose it directly)
        # Use a conservative default if we can't get it
        try:
            pos = page.evaluate(
                "() => ({ x: window._mouseX || window.innerWidth/2,"
                "          y: window._mouseY || window.innerHeight/2 })"
            )
            cur_x, cur_y = pos.get("x", 400), pos.get("y", 300)
        except Exception:
            cur_x, cur_y = 400, 300

        steps = random.randint(18, 35)
        path  = _bezier_path(cur_x, cur_y, target_x, target_y, steps)

        for i, (px, py) in enumerate(path):
            page.mouse.move(px, py)
            # Slow at start/end, fast in middle
            t = i / len(path)
            speed_factor = 4 * t * (1 - t)          # parabola, peaks at t=0.5
            delay = random.uniform(0.005, 0.025) * (1.5 - speed_factor)
            time.sleep(delay)

        # Track position in JS for next call
        page.evaluate(
            f"() => {{ window._mouseX = {target_x}; window._mouseY = {target_y}; }}"
        )
    except Exception:
        # Never block the bot — silently fall back to instant move
        try:
            page.mouse.move(target_x, target_y)
        except Exception:
            pass


def _element_center(el: Locator) -> tuple[float, float] | None:
    """Return the centre coordinates of a visible element, or None."""
    try:
        bb = el.bounding_box()
        if bb:
            return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    except Exception:
        pass
    return None


def human_click(
    page: Page,
    selector: str | None = None,
    *,
    locator: Locator | None = None,
    timeout: int = 5000,
) -> bool:
    """
    Move the mouse to a visible element along a Bézier curve, pause briefly,
    then click. Falls back to direct .click() if the move fails.

    Usage:
        human_click(page, "button[type='submit']")
        human_click(page, locator=page.locator(".apply-btn").first)
    """
    try:
        el = locator if locator is not None else page.locator(selector).first
        if not el.is_visible(timeout=timeout):
            return False

        center = _element_center(el)
        if center:
            # Add tiny random offset within the element (not always dead-centre)
            try:
                bb      = el.bounding_box()
                off_x   = random.uniform(-bb["width"]  * 0.25, bb["width"]  * 0.25)
                off_y   = random.uniform(-bb["height"] * 0.25, bb["height"] * 0.25)
                cx, cy  = center[0] + off_x, center[1] + off_y
            except Exception:
                cx, cy = center
            human_mouse_move(page, cx, cy)
            time.sleep(random.uniform(0.1, 0.35))   # small pre-click pause

        el.click(timeout=timeout)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# 3. Human-like typing
# ──────────────────────────────────────────────────────────────

# Characters that make plausible "fat-finger" typos for each key
_TYPO_NEIGHBOURS: dict[str, str] = {
    "a": "sq", "b": "vn", "c": "xv", "d": "sf", "e": "wr",
    "f": "dg", "g": "fh", "h": "gj", "i": "uo", "j": "hk",
    "k": "jl", "l": "k;", "m": "n,", "n": "bm", "o": "ip",
    "p": "o[", "q": "wa", "r": "et", "s": "ad", "t": "ry",
    "u": "yi", "v": "cb", "w": "qe", "x": "zc", "y": "ut",
    "z": "x",  " ": "  ",
}


def human_type(
    page: Page,
    text: str,
    selector: str | None = None,
    *,
    locator: Locator | None = None,
    clear_first: bool = True,
    typo_rate: float = 0.025,
) -> None:
    """
    Type `text` into a field character-by-character at variable human speed.

    - Variable inter-key delay (50–180 ms, bursts of fast typing then slow)
    - Occasional fat-finger typo (neighbour key) + immediate Backspace correction
    - Random "hesitation" pause mid-word (as if thinking)
    - Slower at the start of the field, faster once in a rhythm

    Args:
        page        : Playwright Page
        text        : string to type
        selector    : CSS selector (if locator not provided)
        locator     : pre-built Playwright Locator (takes priority)
        clear_first : triple-click + Delete before typing (default True)
        typo_rate   : probability of a typo per character (default 2.5 %)
    """
    el = locator if locator is not None else page.locator(selector).first

    try:
        if not el.is_visible(timeout=3000):
            return

        # Move to field naturally before clicking
        center = _element_center(el)
        if center:
            human_mouse_move(page, *center)
            time.sleep(random.uniform(0.05, 0.15))

        el.click()
        time.sleep(random.uniform(0.15, 0.4))  # settling pause after click

        if clear_first:
            try:
                el.click(click_count=3)
                time.sleep(random.uniform(0.1, 0.2))
                page.keyboard.press("Delete")
                time.sleep(random.uniform(0.05, 0.15))
            except Exception:
                pass

        in_burst = False                       # True = currently in a fast burst
        burst_remaining = 0

        for i, char in enumerate(text):
            # ── Decide typing speed regime ────────────────────────────
            if burst_remaining > 0:
                burst_remaining -= 1
                delay = random.uniform(0.04, 0.10)   # fast burst
            else:
                # 20 % chance to start a new fast burst
                if random.random() < 0.20:
                    burst_remaining = random.randint(3, 8)
                    delay = random.uniform(0.04, 0.10)
                else:
                    delay = random.uniform(0.06, 0.18)   # normal speed

            # ── Occasional hesitation pause (1.5 % chance) ───────────
            if random.random() < 0.015:
                time.sleep(random.uniform(0.4, 1.2))

            # ── Typo: type wrong neighbour key then backspace ─────────
            if char.isalpha() and random.random() < typo_rate:
                wrong = random.choice(_TYPO_NEIGHBOURS.get(char.lower(), char))
                if wrong and wrong != " ":
                    page.keyboard.type(wrong)
                    time.sleep(random.uniform(0.08, 0.25))   # brief "realise mistake" pause
                    page.keyboard.press("Backspace")
                    time.sleep(random.uniform(0.05, 0.18))

            # ── Type the actual character ─────────────────────────────
            page.keyboard.type(char)
            time.sleep(delay)

        # Final settling pause after finishing the field
        time.sleep(random.uniform(0.2, 0.5))

    except Exception as exc:
        # Never crash the bot — fall back to instant fill
        try:
            if selector:
                page.fill(selector, text)
            else:
                el.fill(text)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────
# 4. Scrolling
# ──────────────────────────────────────────────────────────────

def human_scroll_down(page: Page, steps: int | None = None) -> None:
    """
    Scroll the page down smoothly in small random increments (simulates wheel
    scrolling while reading).  `steps` controls how far to scroll overall.
    """
    if steps is None:
        steps = random.randint(3, 7)

    for _ in range(steps):
        amount = random.randint(80, 280)    # px per step
        try:
            page.evaluate(f"window.scrollBy(0, {amount})")
        except Exception:
            break
        time.sleep(random.uniform(0.08, 0.22))

    # Tiny pause after scroll settle
    time.sleep(random.uniform(0.3, 0.8))


def human_scroll_up(page: Page, steps: int | None = None) -> None:
    """Scroll up smoothly."""
    if steps is None:
        steps = random.randint(2, 5)
    for _ in range(steps):
        amount = random.randint(80, 220)
        try:
            page.evaluate(f"window.scrollBy(0, -{amount})")
        except Exception:
            break
        time.sleep(random.uniform(0.08, 0.20))
    time.sleep(random.uniform(0.2, 0.6))


def human_scroll_to_element(page: Page, selector: str) -> None:
    """
    Scroll an element into view naturally (section-by-section, not instant jump).
    """
    try:
        el = page.locator(selector).first
        if el.count() == 0:
            return
        bb = el.bounding_box()
        if not bb:
            el.scroll_into_view_if_needed()
            return

        vp_height = page.evaluate("window.innerHeight") or 800
        current_scroll = page.evaluate("window.scrollY") or 0
        target_scroll  = bb["y"] - vp_height * 0.35   # land element ~35 % from top

        distance = target_scroll - current_scroll
        steps    = max(3, int(abs(distance) / 150))
        per_step = distance / steps

        for _ in range(steps):
            try:
                page.evaluate(f"window.scrollBy(0, {per_step:.1f})")
            except Exception:
                break
            time.sleep(random.uniform(0.06, 0.18))
        time.sleep(random.uniform(0.3, 0.7))
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# 5. Idle cursor jiggle (during long waits)
# ──────────────────────────────────────────────────────────────

def idle_jiggle(page: Page, duration: float = 3.0) -> None:
    """
    Move the mouse in small random paths for `duration` seconds,
    simulating a human who is waiting but not doing anything.
    """
    end_time = time.time() + duration
    try:
        vp       = page.evaluate(
            "() => ({ w: window.innerWidth, h: window.innerHeight })"
        )
        vw = vp.get("w", 1280)
        vh = vp.get("h", 800)
    except Exception:
        vw, vh = 1280, 800

    # Start from somewhere mid-screen
    cx = random.randint(int(vw * 0.3), int(vw * 0.7))
    cy = random.randint(int(vh * 0.3), int(vh * 0.7))

    try:
        page.mouse.move(cx, cy)
    except Exception:
        return

    while time.time() < end_time:
        # Small random drift (± 30–120 px)
        nx = cx + random.randint(-120, 120)
        ny = cy + random.randint(-80,   80)
        # Keep within viewport
        nx = max(50, min(vw - 50, nx))
        ny = max(50, min(vh - 50, ny))

        try:
            human_mouse_move(page, nx, ny)
        except Exception:
            break

        cx, cy = nx, ny
        # Sometimes pause (looking at something), sometimes move quickly
        if random.random() < 0.3:
            time.sleep(random.uniform(0.6, 1.8))
        else:
            time.sleep(random.uniform(0.1, 0.5))


# ──────────────────────────────────────────────────────────────
# 6. Convenience wrappers
# ──────────────────────────────────────────────────────────────

def human_select(page: Page, selector: str, value: str) -> bool:
    """
    Select a <select> option with a small pre-interaction pause.
    Returns True on success.
    """
    try:
        el = page.locator(selector).first
        if not el.is_visible(timeout=2000):
            return False
        center = _element_center(el)
        if center:
            human_mouse_move(page, *center)
            time.sleep(random.uniform(0.15, 0.4))
        el.select_option(value)
        time.sleep(random.uniform(0.2, 0.5))
        return True
    except Exception:
        return False


def human_checkbox(page: Page, selector: str) -> bool:
    """Click a checkbox with human-like pre-pause."""
    return human_click(page, selector)


def natural_wait_for_selector(
    page: Page,
    selector: str,
    timeout: int = 10_000,
    jiggle: bool = True,
) -> bool:
    """
    Wait for a selector to appear while optionally jiggling the cursor.
    Breaks the wait into 500 ms intervals so jiggle runs concurrently.
    Returns True if found within timeout.
    """
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=500):
                return True
        except Exception:
            pass
        if jiggle:
            idle_jiggle(page, duration=0.5)
        else:
            time.sleep(0.5)
    return False


# ──────────────────────────────────────────────────────────────
# 7. Stealth browser launch helpers
# ──────────────────────────────────────────────────────────────

# Rotate through common real-world Chrome user agents
# Use Chrome 125 to match the Playwright 1.44 bundled Chromium version
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.112 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.207 Safari/537.36",
]

# Realistic viewport sizes (not the telltale 1280×720 automation default)
_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 800},
]

# JS injected into every new page to hide automation signals
_STEALTH_SCRIPT = """
(() => {
// ── 1. webdriver flag (biggest bot signal) ────────────────────────────────
Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });

// ── 2. Plugins — real Chrome has 4 built-in plugins ──────────────────────
const _pluginData = [
    {name:'Chrome PDF Plugin',         filename:'internal-pdf-viewer',             description:'Portable Document Format'},
    {name:'Chrome PDF Viewer',         filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
    {name:'Native Client',             filename:'internal-nacl-plugin',             description:''},
    {name:'Widevine Content Decryption Module', filename:'widevinecdmadapter.dll',  description:'Enables Widevine licenses for encrypted media playback'},
];
Object.defineProperty(navigator, 'plugins', {
    get: () => { const a = [..._pluginData]; a[Symbol.iterator] = Array.prototype[Symbol.iterator]; return a; },
    configurable: true,
});
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => { const a = []; a[Symbol.iterator] = Array.prototype[Symbol.iterator]; return a; },
    configurable: true,
});

// ── 3. Languages ──────────────────────────────────────────────────────────
Object.defineProperty(navigator, 'languages', { get: () => ['en-IN','en-US','en','hi'], configurable: true });

// ── 4. Hardware — realistic mid-range laptop ──────────────────────────────
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8, configurable: true });
Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8, configurable: true });

// ── 5. Platform ───────────────────────────────────────────────────────────
Object.defineProperty(navigator, 'platform', { get: () => 'Win32', configurable: true });

// ── 6. window.chrome — missing in Playwright headless by default ──────────
if (!window.chrome || !window.chrome.runtime) {
    const _chrome = {
        app:     { isInstalled: false, InstallState: { DISABLED:'disabled', INSTALLED:'installed', NOT_INSTALLED:'not_installed' }, RunningState: { CANNOT_RUN:'cannot_run', READY_TO_RUN:'ready_to_run', RUNNING:'running' } },
        runtime: {
            PlatformOs:   { MAC:'mac', WIN:'win', ANDROID:'android', CROS:'cros', LINUX:'linux', OPENBSD:'openbsd' },
            PlatformArch: { ARM:'arm', X86_32:'x86-32', X86_64:'x86-64' },
            RequestUpdateCheckStatus: { THROTTLED:'throttled', NO_UPDATE:'no_update', UPDATE_AVAILABLE:'update_available' },
            OnInstalledReason: { INSTALL:'install', UPDATE:'update', CHROME_UPDATE:'chrome_update', SHARED_MODULE_UPDATE:'shared_module_update' },
            OnRestartRequiredReason: { APP_UPDATE:'app_update', OS_UPDATE:'os_update', PERIODIC:'periodic' },
        },
        loadTimes: function() {
            return { requestTime: performance.timing.navigationStart/1000, startLoadTime: performance.timing.navigationStart/1000, commitLoadTime: performance.timing.responseStart/1000, finishDocumentLoadTime: performance.timing.domContentLoadedEventEnd/1000, finishLoadTime: performance.timing.loadEventEnd/1000, firstPaintTime: 0, firstPaintAfterLoadTime: 0, navigationType: 'Other', wasFetchedViaSpdy: false, wasNpnNegotiated: false, npnNegotiatedProtocol: '', wasAlternateProtocolAvailable: false, connectionInfo: 'http/1.1' };
        },
        csi: function() {
            return { startE: performance.timing.navigationStart, onloadT: performance.timing.loadEventEnd, pageT: performance.now(), tran: 15 };
        },
    };
    try { Object.defineProperty(window, 'chrome', { value: _chrome, writable: true, enumerable: true, configurable: true }); } catch(e) {}
}

// ── 7. Canvas fingerprint — add imperceptible noise to defeat exact-match ──
const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {
    const ctx = this.getContext('2d');
    if (ctx) {
        const img = ctx.getImageData(0, 0, this.width || 1, this.height || 1);
        if (img.data.length > 0) {
            img.data[0] ^= 1;  // flip one invisible bit
            ctx.putImageData(img, 0, 0);
        }
    }
    return _origToDataURL.call(this, type, ...args);
};
const _origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData = function(...args) {
    const d = _origGetImageData.apply(this, args);
    if (d.data.length > 3) d.data[3] ^= 1;
    return d;
};

// ── 8. WebGL — spoof renderer/vendor to look like real GPU ───────────────
const _getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
    if (param === 37446) return 'Intel Iris OpenGL Engine';  // UNMASKED_RENDERER_WEBGL
    return _getParam.call(this, param);
};
try {
    const _getParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Inc.';
        if (param === 37446) return 'Intel Iris OpenGL Engine';
        return _getParam2.call(this, param);
    };
} catch(e) {}

// ── 9. Permissions — prevent notification-permission detection ────────────
const _origQuery = window.navigator.permissions.query.bind(navigator.permissions);
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission, onchange: null })
        : _origQuery(p);

// ── 10. User-Agent data (Client Hints API) ────────────────────────────────
if (navigator.userAgentData) {
    try {
        Object.defineProperty(navigator, 'userAgentData', {
            get: () => ({
                brands: [
                    { brand: 'Google Chrome',  version: '125' },
                    { brand: 'Chromium',        version: '125' },
                    { brand: 'Not/A)Brand',     version: '99'  },
                ],
                mobile:    false,
                platform:  'Windows',
                getHighEntropyValues: () => Promise.resolve({}),
            }),
            configurable: true,
        });
    } catch(e) {}
}
})();
"""


def stealth_launch_args() -> list:
    """
    Chromium launch args that reduce automation fingerprint.
    Pass as `args=stealth_launch_args()` inside `p.chromium.launch(...)`.
    """
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--start-maximized",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-breakpad",
        "--disable-component-extensions-with-background-pages",
        "--disable-features=TranslateUI,BlinkGenPropertyTrees",
        "--disable-ipc-flooding-protection",
        "--disable-renderer-backgrounding",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--mute-audio",
        "--safebrowsing-disable-auto-update",
        # ── Memory / OOM prevention (critical on Railway containers) ──
        "--disable-cache",
        "--disk-cache-size=1",
        "--media-cache-size=1",
        "--aggressive-cache-discard",
        "--disable-application-cache",
        "--renderer-process-limit=1",
        "--disable-logging",
        "--disable-hang-monitor",
        "--js-flags=--max-old-space-size=768",
        # ── Disable images to prevent OOM (Error code 9) on Railway containers ──
        "--blink-settings=imagesEnabled=false",
    ]


def stealth_context_options(user_id: str = None) -> dict:
    """
    Returns kwargs for browser context creation with realistic viewport,
    user-agent, locale, and timezone.

    When user_id is provided the values are DETERMINISTIC (derived from the
    user_id hash) so the same user always gets the same fingerprint across
    runs — critical for persistent browser profiles so LinkedIn never sees
    a fingerprint change between sessions.
    """
    if user_id:
        import hashlib as _hl
        _idx = int(_hl.md5(user_id.encode()).hexdigest()[:4], 16)
        ua  = _USER_AGENTS[_idx % len(_USER_AGENTS)]
        vp  = _VIEWPORTS [_idx % len(_VIEWPORTS)]
    else:
        ua  = random.choice(_USER_AGENTS)
        vp  = random.choice(_VIEWPORTS)
        # Slightly jitter viewport for non-persistent sessions
        vp = {"width": vp["width"] + random.randint(-10, 10), "height": vp["height"] + random.randint(-10, 10)}
    return {
        "user_agent":    ua,
        "viewport":      vp,
        "locale":        "en-IN",
        "timezone_id":   "Asia/Kolkata",
        "color_scheme":  "light",
        "device_scale_factor": 1.0 if user_id else random.choice([1.0, 1.25, 1.5]),
        "has_touch":     False,
        "is_mobile":     False,
        "java_script_enabled": True,
        "extra_http_headers": {
            "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8,hi;q=0.7",
        },
    }


def inject_stealth(page) -> None:
    """
    Inject the stealth JS payload into a Playwright page so it runs before
    every document load.  Call this immediately after `context.new_page()`.

    Usage:
        page = context.new_page()
        inject_stealth(page)
    """
    try:
        page.add_init_script(_STEALTH_SCRIPT)
    except Exception:
        pass  # Never block the bot
