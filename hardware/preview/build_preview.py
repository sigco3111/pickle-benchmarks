#!/usr/bin/env python3
"""Build the single-file Three.js preview.

    python3 build_preview.py

Renders ``preview.template.html`` into two byte-identical files:

    preview/index.html
    ../1-controller-3d.html

and injects two things that must not be maintained by hand:

* the enclosure parameters from ``../enclosure/params.json``
* the firmware's 5x7 font (``../firmware/include/font5x7.h``), so the simulated
  OLED draws the same glyphs as the real display.
"""
from __future__ import annotations

import base64
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
HW = HERE.parent
TEMPLATE = HERE / "preview.template.html"
OUTPUTS = [HERE / "index.html", HW.parent / "1-controller-3d.html"]


def font_b64() -> str:
    text = (HW / "firmware" / "include" / "font5x7.h").read_text(encoding="utf-8")
    rows = re.findall(r"\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\}", text)
    data = bytes(int(v) for row in rows for v in row)
    if len(rows) != 95 or len(data) != 475:
        raise SystemExit(f"unexpected font table: {len(rows)} glyphs, {len(data)} bytes")
    return base64.b64encode(data).decode("ascii")


def main() -> int:
    dims = json.loads((HW / "enclosure" / "params.json").read_text(encoding="utf-8"))
    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("__DIMS_JSON__", json.dumps(dims, separators=(",", ":")))
    html = html.replace("__FONT_B64__", font_b64())

    for path in OUTPUTS:
        path.write_text(html, encoding="utf-8")
        print(f"wrote {path} ({len(html)/1024:.1f} kB)")

    a, b = (p.read_text(encoding="utf-8") for p in OUTPUTS)
    if a != b:
        print("ERROR: the two preview copies differ", file=sys.stderr)
        return 1
    print("both copies identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
