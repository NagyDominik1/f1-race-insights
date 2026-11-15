"""Capture the README screenshots of the demo weekend into docs/screenshots/.

Run from the project root:  python scripts/take_screenshots.py

Starts the app on a free local port, opens each page in a headless browser
(Playwright, a dev dependency) and saves one PNG per page. Uses Playwright's
own Chromium if installed (`playwright install chromium`), else the Edge or
Chrome already on the machine.
"""

import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Browser, Frame, Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
MAX_BYTES = 500_000
SCALES = [2, 1.5, 1.25, 1]  # device pixel ratios, tried in order until the PNG fits MAX_BYTES
WIDTH = 1440


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_app(port: int) -> subprocess.Popen:
    """Start Streamlit and wait until it answers its health check."""
    command = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
               "--server.port", str(port), "--browser.gatherUsageStats", "false"]
    app = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1):
                return app
        except OSError:
            time.sleep(0.5)
    app.terminate()
    raise SystemExit("The app did not start within 30 seconds.")


def launch(playwright: Playwright) -> Browser:
    """Playwright's Chromium, or a browser that is already installed."""
    for channel in (None, "msedge", "chrome"):
        try:
            return playwright.chromium.launch(channel=channel)
        except Exception:  # noqa: BLE001 - any launch failure means: try the next browser
            continue
    raise SystemExit("No browser found. Run: playwright install chromium")


def component(page: Page, selector: str) -> Frame:
    """The iframe of an HTML component, found by an element inside it."""
    for _ in range(40):
        for frame in page.frames:
            if frame != page.main_frame and frame.locator(selector).count():
                return frame
        page.wait_for_timeout(250)
    raise SystemExit(f"Component with {selector} not found on {page.url}")


def replay_mid_race(page: Page) -> None:
    """Pause the replay on lap 18, following the first selected driver through the pit stops."""
    frame = component(page, "#view")
    frame.locator("#play").click()
    frame.evaluate("() => { const s = document.getElementById('time'); s.value = 1505; s.dispatchEvent(new Event('input')); }")
    frame.locator(".row.sel").first.click()
    page.wait_for_timeout(2500)


def ghost_mid_lap(page: Page) -> None:
    """Let both cars drive a third of the lap at x4, then pause."""
    frame = component(page, "#view")
    frame.locator("#speeds button", has_text="×4").click()
    page.wait_for_timeout(7000)
    frame.locator("#play").click()
    page.wait_for_timeout(400)


# name, url path, viewport height, seconds to wait after load, optional interaction
SHOTS: list[tuple[str, str, int, float, Callable[[Page], None] | None]] = [
    ("landing", "", 900, 9, None),
    ("overview", "overview", 1040, 4, None),
    ("pace", "pace", 900, 4, None),
    ("strategy", "strategy", 1560, 4, None),
    ("head_to_head", "head-to-head", 980, 4, None),
    ("replay", "replay", 1000, 4, replay_mid_race),
    ("ghost", "ghost-lap", 920, 4, ghost_mid_lap),
]


def capture(browser: Browser, base_url: str, name: str, path: str, height: int, wait: float,
            interact: Callable[[Page], None] | None) -> None:
    """Save one page as PNG, lowering the pixel ratio until the file is under MAX_BYTES."""
    target = OUT / f"{name}.png"
    for scale in SCALES:
        page = browser.new_page(viewport={"width": WIDTH, "height": height}, device_scale_factor=scale)
        page.goto(f"{base_url}/{path}", wait_until="networkidle")
        page.wait_for_timeout(wait * 1000)
        if interact:
            interact(page)
        if page.locator('[data-testid="stException"]').count():
            raise SystemExit(f"{name}: the page shows an error")
        page.screenshot(path=str(target))
        page.close()
        if target.stat().st_size <= MAX_BYTES:
            break
    print(f"{target.relative_to(ROOT)}: {target.stat().st_size / 1024:.0f} kB at {scale}x")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    app = start_app(port)
    try:
        with sync_playwright() as playwright:
            browser = launch(playwright)
            for shot in SHOTS:
                capture(browser, f"http://127.0.0.1:{port}", *shot)
            browser.close()
    finally:
        app.terminate()


if __name__ == "__main__":
    main()
