#!/usr/bin/env python3
"""Generate firmware/include/font5x7.h from readable ASCII-art glyphs.

The controller only needs uppercase ASCII, digits and a few symbols. Keeping
the glyphs as pictures in this file makes them reviewable, and the generated
table is what the firmware uses (no runtime font library).

Run:  python3 tools/gen_font.py            # rewrites the header
      python3 tools/gen_font.py --png out.png   # also renders a sample
"""
from __future__ import annotations

import argparse
import pathlib

GLYPHS: dict[str, list[str]] = {
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["###..", "#..#.", "#...#", "#...#", "#...#", "#..#.", "###.."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    ":": [".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    ",": [".....", ".....", ".....", ".....", ".##..", "..#..", ".#..."],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "%": ["##..#", "##.#.", "..#..", ".#...", "#..##", "...#.", "..###"],
    "'": ["..#..", "..#..", ".....", ".....", ".....", ".....", "....."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    "(": ["...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."],
    ")": [".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."],
    "<": ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."],
    ">": [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."],
    "[": [".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."],
    "]": [".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."],
    "*": [".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."],
    "#": [".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
}


def glyph_columns(rows: list[str]) -> list[int]:
    cols = []
    for x in range(5):
        byte = 0
        for y in range(7):
            if rows[y][x] == "#":
                byte |= 1 << y
        cols.append(byte)
    return cols


def build_table() -> list[list[int]]:
    table = []
    for code in range(0x20, 0x7F):
        ch = chr(code)
        lookup = GLYPHS.get(ch) or GLYPHS.get(ch.upper())
        if lookup is None:
            table.append([0] * 5)
        else:
            if len(lookup) != 7 or any(len(r) != 5 for r in lookup):
                raise ValueError(f"glyph {ch!r} is not 7 rows of 5 columns")
            table.append(glyph_columns(lookup))
    return table


def write_header(path: pathlib.Path) -> None:
    table = build_table()
    lines = [
        "/* Generated by tools/gen_font.py - do not edit by hand.",
        " * 5x7 uppercase ASCII font, column major, bit 0 = top row.",
        " * Lowercase input is mapped to uppercase by the renderer.",
        " */",
        "#ifndef TD_FONT5X7_H",
        "#define TD_FONT5X7_H",
        "",
        "#include <stdint.h>",
        "",
        "#define TD_FONT_FIRST 0x20",
        "#define TD_FONT_LAST  0x7E",
        "#define TD_FONT_W 5",
        "#define TD_FONT_H 7",
        "",
        "static const uint8_t TD_FONT5X7[TD_FONT_LAST - TD_FONT_FIRST + 1][5] = {",
    ]
    for i, cols in enumerate(table):
        ch = chr(0x20 + i)
        comment = ch if 0x20 < 0x21 or ord(ch) > 0x20 else "space"
        comment = "space" if ch == " " else ("'\\''" if ch == "'" else ch)
        lines.append("    {%3d, %3d, %3d, %3d, %3d},  /* 0x%02X %s */" %
                     (cols[0], cols[1], cols[2], cols[3], cols[4], 0x20 + i, comment))
    lines += ["};", "", "#endif /* TD_FONT5X7_H */", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def render_png(path: pathlib.Path, text: str = "REC 00:01:23 TAKEDECK 0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ") -> None:
    from PIL import Image

    scale = 4
    cols = 5 * 6
    rows = 8 * (len(text) // (len(text) // 8 + 1) + 1)
    rows = 8 * ((len(text) // (128 // (6 * scale))) + 2) * 7
    width = 128 * scale
    height = max(64 * scale, 8 * 8 * scale)
    img = Image.new("L", (width, height), 0)
    px = img.load()
    x0, y0 = 2, 2
    for ch in text:
        if ch == "\n":
            x0 = 2
            y0 += 8 * scale
            continue
        idx = ord(ch.upper()) - 0x20
        if 0 <= idx < len(GLYPHS) + 0x20 - 0x20:
            rows_g = build_table()[idx]
            for x in range(5):
                for y in range(7):
                    if rows_g[x] >> y & 1:
                        for dx in range(scale):
                            for dy in range(scale):
                                px[x0 + x * scale + dx, y0 + y * scale + dy] = 255
        x0 += 6 * scale
        if x0 > width - 6 * scale:
            x0 = 2
            y0 += 8 * scale
    img.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", default=None, help="also render a sample image")
    ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parents[1] / "include" / "font5x7.h"))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    write_header(out)
    print("wrote", out, "glyphs:", len(build_table()))
    if args.png:
        render_png(pathlib.Path(args.png))
        print("wrote", args.png)


if __name__ == "__main__":
    main()
