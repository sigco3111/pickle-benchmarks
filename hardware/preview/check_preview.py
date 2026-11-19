#!/usr/bin/env python3
"""Static checks for the single-file Three.js preview.

The build environment had no GPU browser, so the preview is verified here
without executing WebGL:

1. both copies (preview/index.html and ../1-controller-3d.html) are identical
2. the HTML parses and every required control is present
3. the module script is valid JavaScript (parsed by quickjs, imports stripped)
4. the embedded dimensions equal enclosure/params.json
5. the CDN URLs the page needs are reachable and the pinned version matches

What this cannot prove: that the scene draws correctly in a browser. That has
to be looked at (see HARDWARE_VERIFICATION.md).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.request
from html.parser import HTMLParser

HERE = pathlib.Path(__file__).resolve().parent
HW = HERE.parent
COPIES = [HERE / "index.html", HW.parent / "1-controller-3d.html"]
THREE_VERSION = "0.170.0"

problems: list[str] = []
notes: list[str] = []


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.scripts: list[tuple[str, str]] = []
        self._in_script = False
        self._attrs: dict[str, str] = {}
        self._buf: list[str] = []
        self.tag_counts: dict[str, int] = {}

    def handle_starttag(self, tag, attrs):
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        a = dict(attrs)
        if "id" in a:
            if a["id"] in self.ids:
                problems.append(f"duplicate id: {a['id']}")
            self.ids.add(a["id"])
        if tag == "script":
            self._in_script = True
            self._attrs = a
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script:
            self.scripts.append((self._attrs.get("type", ""), "".join(self._buf)))
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self._buf.append(data)


def check_cdn() -> None:
    urls = [
        f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/build/three.module.js",
        f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/examples/jsm/controls/OrbitControls.js",
        f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}/examples/jsm/geometries/RoundedBoxGeometry.js",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=20) as resp:
                notes.append(f"CDN {resp.status} {url}")
                if resp.status != 200:
                    problems.append(f"CDN returned {resp.status}: {url}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"CDN unreachable: {url} ({exc})")


def main() -> int:
    if COPIES[0].read_bytes() != COPIES[1].read_bytes():
        problems.append("preview/index.html and 1-controller-3d.html differ")

    html = COPIES[0].read_text(encoding="utf-8")
    parser = Collector()
    parser.feed(html)

    required_ids = [
        "explode", "explodeLabel", "explodePlay", "explodeReset", "lidToggle", "lidPeek",
        "views", "btnRec", "btnPrev", "btnNext", "btnMute", "btnLink", "btnObs",
        "stLink", "stRec", "stTime", "stScene", "stCmd", "stLed", "log",
        "takedeck-dims", "takedeck-font",
    ]
    for rid in required_ids:
        if rid not in parser.ids:
            problems.append(f"missing element id: {rid}")

    for text in ["시뮬레이션", "SIMULATION"]:
        if text not in html:
            problems.append(f"missing simulation label: {text}")
    if f"three@{THREE_VERSION}" not in html:
        problems.append("Three.js version is not pinned to 0.170.0")
    if 'type="module"' not in html:
        problems.append("no ES module script")
    if "data-view=" not in html:
        problems.append("no camera view presets")

    # dimensions embedded in the page must equal params.json
    dims_json = None
    font_b64 = None
    for stype, body in parser.scripts:
        if stype == "application/json":
            dims_json = body
        elif stype == "text/plain":
            font_b64 = body.strip()
    params = json.loads((HW / "enclosure" / "params.json").read_text(encoding="utf-8"))
    if dims_json is None:
        problems.append("no embedded dimensions block")
    else:
        embedded = json.loads(dims_json)
        if embedded != params:
            problems.append("embedded dimensions differ from enclosure/params.json")
        else:
            notes.append("embedded dimensions match enclosure/params.json")
    if not font_b64 or len(font_b64) < 500:
        problems.append("font data missing")

    # JS syntax: strip the import statements (module-only) and parse the rest
    module = next((body for stype, body in parser.scripts if stype == "module"), None)
    if module is None:
        problems.append("module script not found")
    else:
        body = re.sub(r"^\s*import .*?;\s*$", "", module, flags=re.MULTILINE)
        try:
            import quickjs

            ctx = quickjs.Context()
            ctx.eval("var __src = " + json.dumps(body) + ";")
            ctx.eval("new Function(__src);")
            notes.append(f"module script parses ({len(body)} chars)")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"JavaScript syntax error: {exc}")

        for needle in ["applyExplode", "drawOled", "devicePress", "setLink", "OrbitControls"]:
            if needle not in module:
                problems.append(f"module is missing {needle}")

    check_cdn()

    print("preview checks")
    for note in notes:
        print("  ok   ", note)
    for problem in problems:
        print("  FAIL ", problem)
    print(f"\n{len(problems)} problem(s), {len(notes)} ok")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
