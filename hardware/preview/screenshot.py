#!/usr/bin/env python3
"""Run the preview in a real (headless) browser and take screenshots.

    python3 screenshot.py [--out ../docs]

Serves the hardware/ folder over localhost, drives the page with Playwright and
reports every console error / page exception. The screenshots are used in the
documentation; the console report is the evidence that the page actually runs.

Needs ``playwright`` plus a Chromium build (the CI container used a downloaded
Chrome for Testing headless shell with LD_LIBRARY_PATH pointing at the few
missing at-spi libraries).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import pathlib
import socketserver
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent  # serve hardware/ so both preview/ and ../1-controller-3d.html work


def serve() -> tuple[socketserver.TCPServer, int]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    httpd.allow_reuse_address = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs"))
    ap.add_argument("--page", default="/preview/index.html")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    httpd, port = serve()
    url = f"http://127.0.0.1:{port}{args.page}"
    problems: list[str] = []
    console: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--enable-unsafe-swiftshader",
                "--use-angle=swiftshader",
            ],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=1)
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: problems.append(f"requestfailed: {r.url} {r.failure}"))

        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_timeout(3500)

        def shot(name: str) -> None:
            page.screenshot(path=str(out / name))
            print("shot", out / name)

        # 1. assembled
        shot("preview_assembled.png")

        # 2. REC pressed -> red LED, OLED running
        page.click("#btnRec")
        page.wait_for_timeout(1800)
        shot("preview_recording.png")
        state = page.evaluate("() => ({led: document.getElementById('stLed').textContent,"
                              " rec: document.getElementById('stRec').textContent,"
                              " time: document.getElementById('stTime').textContent})")
        print("after REC:", state)
        if "점등" not in state["led"] or "녹화" not in state["rec"]:
            problems.append(f"REC did not turn the LED on: {state}")
        if state["time"] == "00:00:00":
            problems.append(f"elapsed time did not advance: {state}")

        # 3. scene change + OBS-side start (LED follows OBS, not the button)
        page.click("#btnNext")
        page.wait_for_timeout(400)
        page.click("#btnObs")
        page.wait_for_timeout(900)
        shot("preview_obs_side.png")

        # 4. link lost -> blinking LED, OLED says LINK LOST
        page.click("#btnLink")
        page.wait_for_timeout(1200)
        shot("preview_link_lost.png")
        lost = page.evaluate("() => ({led: document.getElementById('stLed').textContent,"
                             " rec: document.getElementById('stRec').textContent,"
                             " link: document.getElementById('stLink').textContent})")
        print("after link loss:", lost)
        if "점멸" not in lost["led"] or "끊김" not in lost["link"]:
            problems.append(f"link loss not reflected in the UI: {lost}")
        page.click("#btnLink")  # recover
        page.wait_for_timeout(1200)
        back = page.evaluate("() => document.getElementById('stLink').textContent")
        print("after reconnect:", back)
        if "정상" not in back:
            problems.append(f"reconnect not reflected in the UI: {back}")

        # 5. case open
        page.click("#lidToggle")
        page.wait_for_timeout(1200)
        shot("preview_case_open.png")
        page.click("#lidToggle")
        page.wait_for_timeout(600)

        # 6. exploded view at t = 12 s
        page.eval_on_selector("#explode", "el => { el.value = 12; el.dispatchEvent(new Event('input')); }")
        page.wait_for_timeout(1500)
        shot("preview_exploded.png")

        # 7. front view with the keys level with the camera (checks legends)
        page.eval_on_selector("#explode", "el => { el.value = 0; el.dispatchEvent(new Event('input')); }")
        page.click('#views button[data-view="oled"]')
        page.wait_for_timeout(1500)
        shot("preview_oled_closeup.png")

        # 8. top view at 6 s
        page.eval_on_selector("#explode", "el => { el.value = 6; el.dispatchEvent(new Event('input')); }")
        page.click('#views button[data-view="top"]')
        page.wait_for_timeout(1500)
        shot("preview_top.png")

        # read back the simulated state the page reports
        state = page.evaluate(
            """() => ({
                led: document.getElementById('stLed').textContent,
                rec: document.getElementById('stRec').textContent,
                link: document.getElementById('stLink').textContent,
                time: document.getElementById('stTime').textContent,
                fps: document.getElementById('fps').textContent,
                logLines: document.getElementById('log').children.length,
                canvas: !!document.querySelector('canvas'),
            })"""
        )
        print("page state:", state)
        if not state["canvas"]:
            problems.append("no canvas element - three.js did not start")
        if state["logLines"] < 4:
            problems.append("protocol log empty")
        browser.close()

    httpd.shutdown()

    errors = [c for c in console if c.startswith("error")]
    for line in errors:
        print("console error:", line)
    for line in problems:
        print("PROBLEM:", line)
    print(f"\n{len(problems)} problem(s), {len(errors)} console error(s)")
    for c in console[:15]:
        print("  console:", c)
    return 0 if not problems and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
