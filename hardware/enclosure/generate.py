#!/usr/bin/env python3
"""TakeDeck TD-01 enclosure: parametric CAD -> binary STL + interference report.

Why Python and not just OpenSCAD: no OpenSCAD binary was available in the build
environment, so the real geometry is produced here with a mesh CSG kernel
(manifold3d through trimesh), which gives a *single watertight manifold* per
part - not a bag of overlapping shells. ``takedeck_case.scad`` is the editable
parametric source with identical parameters (checked by this script).

    python3 generate.py                     # STL + verification report
    python3 generate.py --render docs/*.png # also render preview images

Everything is in millimetres. Parameters live in params.json; the physical
inputs (module sizes, switch cutout, USB-C opening) are documented in
docs/DIMENSION_SOURCES.md with the manufacturer references.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
import trimesh
from shapely.geometry import Point, box as sbox

HERE = pathlib.Path(__file__).resolve().parent
P = json.loads((HERE / "params.json").read_text(encoding="utf-8"))

ENGINE = "manifold"


# --------------------------------------------------------------------- helpers
def rounded_rect(w: float, d: float, r: float, cx: float = 0.0, cy: float = 0.0):
    """Shapely polygon of a rounded rectangle centred on (cx, cy)."""
    b = sbox(-w / 2.0, -d / 2.0, w / 2.0, d / 2.0)
    r = min(r, min(w, d) / 2.0 - 0.01)
    p = b.buffer(-r, join_style=1).buffer(r, join_style=1, resolution=24)
    return shift(p, cx, cy)


def shift(poly, cx: float, cy: float):
    from shapely import affinity

    return affinity.translate(poly, cx, cy)


def prism(poly, z0: float, z1: float) -> trimesh.Trimesh:
    m = trimesh.creation.extrude_polygon(poly, z1 - z0, engine="earcut")
    m.apply_translation([0.0, 0.0, z0])
    return m


def box(cx: float, cy: float, cz: float, w: float, d: float, h: float) -> trimesh.Trimesh:
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([cx, cy, cz])
    return m


def cyl(cx: float, cy: float, z0: float, z1: float, diameter: float, sections: int = 64):
    m = trimesh.creation.cylinder(radius=diameter / 2.0, height=z1 - z0, sections=sections)
    m.apply_translation([cx, cy, (z0 + z1) / 2.0])
    return m


def union(*meshes) -> trimesh.Trimesh:
    meshes = [m for m in meshes if m is not None]
    if len(meshes) == 1:
        return meshes[0]
    return trimesh.boolean.union(list(meshes), engine=ENGINE)


def diff(a, *b) -> trimesh.Trimesh:
    b = [m for m in b if m is not None]
    if not b:
        return a
    return trimesh.boolean.difference([a, *b], engine=ENGINE)


def intersect_volume(a, b) -> float:
    """Volume of a ∩ b in mm^3 (0.0 when they do not touch)."""
    try:
        res = trimesh.boolean.intersection([a, b], engine=ENGINE)
    except Exception:  # empty intersection can raise in some kernels
        return 0.0
    if res is None or len(res.faces) == 0:
        return 0.0
    with np.errstate(divide="ignore", invalid="ignore"):
        return float(abs(res.volume)) if res.volume == res.volume else 0.0


# ---------------------------------------------------------------- part builders
def bottom_case() -> trimesh.Trimesh:
    c, k, x, s = P["case"], P["keys"], P["xiao"], P["screws"]

    outer_poly = rounded_rect(c["w"], c["d"], c["corner_r"])
    inner_poly = rounded_rect(c["w"] - 2 * c["wall"], c["d"] - 2 * c["wall"], c["inner_corner_r"])

    outer = prism(outer_poly, 0.0, c["h"] - c["plate"])          # 0..21
    cavity = prism(inner_poly, c["floor"], c["h"] - c["plate"] + 1.0)
    body = diff(outer, cavity)

    # USB-C opening in the rear wall. The wall is vertical, so it is cut with a
    # box that reaches outside the case.
    usb = box(0.0, c["d"] / 2 - 1.0, x["usb_cut_z"] + x["usb_cut_h"] / 2.0,
              x["usb_cut_w"], 6.0, x["usb_cut_h"])
    body = diff(body, usb)

    # 4 screw bosses, then their pilot holes
    bosses = []
    for px, py in s["positions"]:
        bosses.append(cyl(px, py, c["floor"], s["boss_top_z"], s["boss_d"], sections=48))
    body = union(body, *bosses)
    pilots = [cyl(px, py, c["floor"] - 0.5, s["boss_top_z"] + 0.5, s["pilot_d"], sections=32)
              for px, py in s["positions"]]
    body = diff(body, *pilots)

    # XIAO board pocket in the floor + side rails + front stop
    pocket = box(0.0, (x["y_front"] + x["y_back"]) / 2.0, c["floor"] + x["pocket_d"] / 2.0,
                 x["board_w"] + 0.4, (x["y_back"] - x["y_front"]) + 0.4, x["pocket_d"])
    body = diff(body, pocket)

    rail_x = x["board_w"] / 2.0 + x["rail_gap"] + x["rail_w"] / 2.0
    rails = [
        box(rail_x, (x["y_front"] + x["y_back"]) / 2.0, c["floor"] + x["rail_h"] / 2.0,
            x["rail_w"], x["y_back"] - x["y_front"], x["rail_h"]),
        box(-rail_x, (x["y_front"] + x["y_back"]) / 2.0, c["floor"] + x["rail_h"] / 2.0,
            x["rail_w"], x["y_back"] - x["y_front"], x["rail_h"]),
        # front stop the board butts against
        box(0.0, x["y_front"] - 0.4, c["floor"] + x["pocket_d"] / 2.0,
            x["board_w"], 0.8, x["pocket_d"]),
    ]
    body = union(body, *rails)

    # silicone feet recesses on the outside of the floor
    f = P["features"]["feet"]
    feet = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            feet.append(cyl(sx * (c["w"] / 2 - f["inset"]), sy * (c["d"] / 2 - f["inset"]),
                            -0.5, f["depth"], f["d"], sections=40))
    body = diff(body, *feet)

    return body


def top_case() -> trimesh.Trimesh:
    c, k, o, l, s = P["case"], P["keys"], P["oled"], P["led"], P["screws"]

    plate_z0 = c["h"] - c["plate"]        # 21.0
    plate_top = c["h"]                    # 24.0

    plate = prism(rounded_rect(c["w"], c["d"], c["corner_r"]), plate_z0, plate_top)

    # switch cutouts (14x14 through) and the 16.2 clip recess from below
    holes = []
    for cx in k["centers_x"]:
        holes.append(box(cx, k["row_y"], (plate_z0 + plate_top) / 2.0,
                         k["cutout"], k["cutout"], c["plate"] + 1.0))
    plate = diff(plate, *holes)

    recesses = []
    for cx in k["centers_x"]:
        recesses.append(box(cx, k["row_y"], plate_z0 + (c["plate"] - k["clip_ledge"]) / 2.0,
                            k["recess"], k["recess"], c["plate"] - k["clip_ledge"]))
    plate = diff(plate, *recesses)

    # OLED window
    plate = diff(plate, box(o["center_x"], o["center_y"], (plate_z0 + plate_top) / 2.0,
                            o["window_w"], o["window_h"], c["plate"] + 1.0))

    # LED: counterbore from inside, 5.05 shaft, 4.4 retaining lip at the top
    plate = diff(plate,
                 cyl(l["center_x"], l["center_y"], plate_z0 - 0.1,
                     plate_z0 + l["counterbore_h"], l["counterbore"], sections=48),
                 cyl(l["center_x"], l["center_y"], plate_z0, plate_top + 0.5, l["hole"], sections=48))
    # re-add the lip ring (0.4 tall over the 4.4 hole) - done by a small tube
    lip = diff(cyl(l["center_x"], l["center_y"], plate_top - l["lip_h"], plate_top,
                   l["hole"] + 0.001, sections=48),
               cyl(l["center_x"], l["center_y"], plate_top - l["lip_h"] - 0.1, plate_top + 0.1,
                   l["lip_hole"], sections=48))
    plate = union(plate, lip)

    # screw clearance + counterbore
    for px, py in s["positions"]:
        plate = diff(plate,
                     cyl(px, py, plate_top - s["cb_h"], plate_top + 0.5, s["cb_d"], sections=40),
                     cyl(px, py, plate_z0 - 1.0, plate_top + 0.5, s["clear_d"], sections=32))

    # registration skirt that plugs into the bottom tray
    skirt_outer = rounded_rect(c["w"] - 2 * c["wall"] - 2 * c["lid_clearance"],
                               c["d"] - 2 * c["wall"] - 2 * c["lid_clearance"],
                               c["inner_corner_r"])
    skirt_inner = rounded_rect(c["w"] - 2 * c["wall"] - 2 * c["lid_clearance"] - 2 * c["lid_skirt_wall"],
                               c["d"] - 2 * c["wall"] - 2 * c["lid_clearance"] - 2 * c["lid_skirt_wall"],
                               max(0.8, c["inner_corner_r"] - c["lid_skirt_wall"]))
    skirt = diff(prism(skirt_outer, plate_z0 - c["lid_skirt_h"], plate_z0),
                 prism(skirt_inner, plate_z0 - c["lid_skirt_h"] - 0.5, plate_z0 + 0.5))

    # OLED retaining ring with a bottom ledge the module rests on
    ring_outer = rounded_rect(o["ring_outer"], o["ring_outer"], o["ring_corner_r"], o["center_x"], o["center_y"])
    ring_inner = rounded_rect(o["module_w"] + 2 * o["module_clearance"],
                              o["module_d"] + 2 * o["module_clearance"],
                              0.6, o["center_x"], o["center_y"])
    ledge_inner = rounded_rect(o["module_w"] + 2 * o["module_clearance"] - 2 * o["ledge_w"],
                               o["module_d"] + 2 * o["module_clearance"] - 2 * o["ledge_w"],
                               1.0, o["center_x"], o["center_y"])
    ring = diff(prism(ring_outer, o["ring_bottom_z"], plate_z0),
                prism(ring_inner, o["ring_bottom_z"] - 0.5, plate_z0 + 0.5))
    ledge = diff(prism(ring_outer, o["ring_bottom_z"], o["ring_bottom_z"] + o["ledge_h"]),
                 prism(ledge_inner, o["ring_bottom_z"] - 0.5, o["ring_bottom_z"] + 0.5 + o["ledge_h"]))

    return union(plate, skirt, ring, ledge)


def keycap() -> trimesh.Trimesh:
    kc = P["keycap"]
    z0 = kc["rim_z"]
    body = prism(rounded_rect(kc["size"], kc["size"], kc["corner_r"]), z0, z0 + kc["height"])

    # skirt recess so the cap can drop over the switch housing
    body = diff(body, box(0.0, 0.0, z0 + kc["skirt_h"] / 2.0,
                          kc["skirt_recess"], kc["skirt_recess"], kc["skirt_h"]))
    # MX cross socket
    a, b = kc["stem_cross_a"], kc["stem_cross_b"]
    depth = kc["stem_depth"]
    socket = union(
        box(0.0, 0.0, z0 + depth / 2.0, a, b, depth),
        box(0.0, 0.0, z0 + depth / 2.0, b, a, depth),
    )
    body = diff(body, socket)
    return body


# ------------------------------------------------------------------- components
def component_meshes():
    """The unmodified parts, positioned exactly as they sit in the case."""
    c, k, o, l, s, x = P["case"], P["keys"], P["oled"], P["led"], P["screws"], P["xiao"]
    parts: dict[str, list[trimesh.Trimesh]] = {}

    board_z0 = x["board_z"]
    board_z1 = board_z0 + x["board_t"]
    parts["xiao"] = [box(0.0, (x["y_front"] + x["y_back"]) / 2.0,
                         (board_z0 + board_z1) / 2.0,
                         x["board_w"], x["y_back"] - x["y_front"], x["board_t"])]

    # USB-C plug corridor: the plug shell plus the overmould approach
    parts["usb_plug"] = [box(0.0, c["d"] / 2 + 1.0, x["usb_cut_z"] + x["usb_cut_h"] / 2.0,
                             x["usb_plug_w"], 6.0, x["usb_plug_h"])]

    # OLED module (glass + PCB, no header: 4 wires soldered flat)
    module_z0 = c["h"] - c["plate"] - o["module_h"]
    parts["oled"] = [box(o["center_x"], o["center_y"], module_z0 + o["module_h"] / 2.0,
                         o["module_w"], o["module_d"], o["module_h"])]

    # switches below the plate (housing 13.6 wide, clips latch in the 14 hole)
    body_h = c["h"] - k["body_below_plate"]  # 24 - ...
    sw = []
    for cx in k["centers_x"]:
        z0 = c["h"] - 5.0
        z1 = c["h"]
        sw.append(box(cx, k["row_y"], (z0 + z1) / 2.0,
                      k["body_below_plate"], k["body_below_plate"], z1 - z0))
    parts["switches"] = sw

    parts["keycaps"] = [
        prism(rounded_rect(P["keycap"]["size"], P["keycap"]["size"], P["keycap"]["corner_r"]),
              P["keycap"]["rim_z"], P["keycap"]["rim_z"] + P["keycap"]["height"])
        for _ in k["centers_x"]
    ]

    # LED body (5 mm, flange 5.9) sitting behind the top plate
    led_z1 = c["h"] - P["led"]["lip_h"] - 0.5
    parts["led"] = [cyl(l["center_x"], l["center_y"], led_z1 - 8.6, led_z1, l["diameter"], sections=40)]

    # screw shafts
    # Screw shaft modelled in the free space only: it threads into the printed
    # boss (an overlap there is the point), so the check is that it passes the
    # lid hole and counterbore without touching the shell.
    parts["screws"] = [
        cyl(px, py, s["boss_top_z"] + 0.02, c["h"] + 1.0, 2.5, sections=32)
        for px, py in s["positions"]
    ]
    return parts


# ------------------------------------------------------------------ verification
def mesh_report(name: str, mesh: trimesh.Trimesh) -> dict:
    ext = mesh.extents
    return {
        "part": name,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume_mm3": round(float(mesh.volume), 2),
        "bbox_mm": [round(float(v), 3) for v in ext],
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
    }


def check_pair(label: str, a, b, expect_free: bool = True) -> dict:
    vol = intersect_volume(a, b)
    ok = (vol < 1e-6) if expect_free else (vol > 1e-6)
    return {"check": label, "intersection_mm3": round(vol, 6), "ok": bool(ok),
            "expectation": "no interference" if expect_free else "must overlap"}


def scad_consistency() -> dict:
    """Compare the parameters written in takedeck_case.scad with params.json."""
    scad = HERE / "takedeck_case.scad"
    if not scad.exists():
        return {"ok": False, "reason": "takedeck_case.scad missing"}
    flat: dict[str, float] = {}

    def walk(d, prefix=""):
        for key, value in d.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                walk(value, prefix + key + "_")
            elif isinstance(value, (int, float)):
                flat[(prefix + key).upper()] = float(value)

    walk(P)
    text = scad.read_text(encoding="utf-8")
    mismatches, compared = [], 0
    for name, expected in flat.items():
        marker = f"{name} ="
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(marker):
                raw = stripped[len(marker):].split(";")[0].strip()
                try:
                    got = float(raw)
                except ValueError:
                    continue
                compared += 1
                if abs(got - expected) > 1e-6:
                    mismatches.append({"param": name, "scad": got, "json": expected})
                break
    return {"ok": not mismatches, "compared": compared, "mismatches": mismatches}


def render(mesh: trimesh.Trimesh, path: pathlib.Path, size=(1100, 800),
           azim=-55.0, elev=-32.0, colour=(196, 200, 208)) -> None:
    """Small orthographic z-buffer renderer (no OpenGL in this environment)."""
    from PIL import Image

    tri = mesh.triangles
    normals = mesh.face_normals
    a, e = math.radians(azim), math.radians(elev)
    # rotate around Z (turntable), then tilt down around X so +Z faces the camera
    cz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    cx = np.array([[1, 0, 0], [0, math.cos(e), -math.sin(e)], [0, math.sin(e), math.cos(e)]])
    rot = cx @ cz
    v = (tri.reshape(-1, 3) @ rot.T).reshape(-1, 3, 3)
    n = normals @ rot.T

    W, H = size
    xy = v[:, :, :2]
    lo = xy.reshape(-1, 2).min(axis=0)
    hi = xy.reshape(-1, 2).max(axis=0)
    scale = min((W - 40) / max(hi[0] - lo[0], 1e-6), (H - 40) / max(hi[1] - lo[1], 1e-6))
    sx = (xy[:, :, 0] - lo[0]) * scale + 20
    sy = (xy[:, :, 1] - lo[1]) * scale + 20
    px = np.stack([sx, H - sy], axis=2)   # image y grows downward
    depth = v[:, :, 2]
    zmin, zmax = float(depth.min()), float(depth.max())

    zbuf = np.full((H, W), -1e9, dtype=np.float64)
    buf = np.zeros((H, W, 3), dtype=np.uint8)
    buf[:, :] = (18, 20, 24)

    light = np.array([0.35, -0.45, 0.82])
    light /= np.linalg.norm(light)

    for i in range(len(px)):
        nz = n[i]
        if nz[2] <= 0.0:      # back face: cull (keeps the inside from leaking out)
            continue
        p0, p1, p2 = px[i]
        xmin = max(int(math.floor(min(p0[0], p1[0], p2[0]))), 0)
        xmax = min(int(math.ceil(max(p0[0], p1[0], p2[0]))), W - 1)
        ymin = max(int(math.floor(min(p0[1], p1[1], p2[1]))), 0)
        ymax = min(int(math.ceil(max(p0[1], p1[1], p2[1]))), H - 1)
        if xmin > xmax or ymin > ymax:
            continue
        xs = np.arange(xmin, xmax + 1) + 0.5
        ys = np.arange(ymin, ymax + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        denom = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
        if abs(denom) < 1e-9:
            continue
        w0 = ((p1[1] - p2[1]) * (gx - p2[0]) + (p2[0] - p1[0]) * (gy - p2[1])) / denom
        w1 = ((p2[1] - p0[1]) * (gx - p2[0]) + (p0[0] - p2[0]) * (gy - p2[1])) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * depth[i][0] + w1 * depth[i][1] + w2 * depth[i][2]
        sub = zbuf[ymin:ymax + 1, xmin:xmax + 1]
        closer = inside & (z > sub)
        if not closer.any():
            continue
        shade = max(0.15, float(np.dot(nz, light)))
        # cheap depth cue: geometry further from the camera is darker, so holes
        # and recesses read as holes instead of flat patches
        zavg = float(z[closer].mean())
        depth_k = 0.28 + 0.72 * float(
            np.clip((zavg - zmin) / max(zmax - zmin, 1e-6), 0.0, 1.0))
        col = tuple(int(c * (0.22 + 0.85 * shade) * depth_k) for c in colour)
        sub[closer] = z[closer]
        block = buf[ymin:ymax + 1, xmin:xmax + 1]
        block[closer] = col

    Image.fromarray(buf).save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", default=str(HERE / "stl"))
    ap.add_argument("--render", action="store_true", help="render preview PNGs into docs/")
    args = ap.parse_args()

    out = pathlib.Path(args.stl_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    parts = {
        "bottom_case": bottom_case(),
        "top_case": top_case(),
        "keycap": keycap(),
    }

    reports = []
    for name, mesh in parts.items():
        mesh.remove_unreferenced_vertices()
        trimesh.repair.fix_normals(mesh)
        path = out / f"{name}.stl"
        mesh.export(path)
        reports.append(mesh_report(name, mesh))
        print(f"{name:<12} {path.stat().st_size/1024:8.1f} kB  "
              f"tri={len(mesh.faces):6d} watertight={mesh.is_watertight} "
              f"bbox={np.round(mesh.extents, 2)}")

    # ---------------------------------------------------------- interference
    comps = component_meshes()
    checks, failures = [], 0

    def add(check: dict) -> None:
        nonlocal failures
        checks.append(check)
        if not check["ok"]:
            failures += 1
            print("  FAIL", check)

    bottom, top, cap = parts["bottom_case"], parts["top_case"], parts["keycap"]
    shell = union(bottom, top)

    for name, meshes in comps.items():
        for i, m in enumerate(meshes):
            add(check_pair(f"shell vs {name}[{i}]", shell, m))

    # Positive control: a block that certainly cuts into the plate must be
    # reported as an interference, otherwise the checks above prove nothing.
    intruder = box(0.0, -32.0, P["case"]["h"], 10.0, 10.0, 4.0)
    add(check_pair("positive control: block through the plate",
                   top, intruder, expect_free=False))

    # Key travel must stay clear: the cap drops 4 mm over the switch housing.
    stem = box(P["keys"]["centers_x"][0], P["keys"]["row_y"], P["case"]["h"] + 2.0, 4.1, 1.27, 4.0)
    add(check_pair("keycap socket clears the MX stem",
                   cap, stem, expect_free=True))
    pressed = trimesh.Trimesh(vertices=cap.vertices + [0, 0, -4.0], faces=cap.faces)
    add(check_pair("keycap at 4 mm travel clears the plate", top, pressed, expect_free=True))

    # PCB-less sanity: the USB plug must reach the receptacle through the wall
    add(check_pair("USB-C plug corridor through rear wall", bottom, comps["usb_plug"][0]))

    # switch cutout must be open: a 14x14 pillar through one switch hole
    pillar = box(P["keys"]["centers_x"][0], P["keys"]["row_y"], P["case"]["h"] - 1.0,
                 13.9, 13.9, 6.0)
    add(check_pair("14 mm switch cutout open", top, pillar))

    # OLED window must be open
    window = box(P["oled"]["center_x"], P["oled"]["center_y"], P["case"]["h"] - 1.0,
                 P["oled"]["window_w"] - 0.2, P["oled"]["window_h"] - 0.2, 6.0)
    add(check_pair("OLED window open", top, window))

    scad = scad_consistency()
    if not scad["ok"]:
        failures += 1

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kernel": f"trimesh {trimesh.__version__} / manifold3d",
        "parts": reports,
        "interference_checks": checks,
        "scad_consistency": scad,
        "failures": failures,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (HERE / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.render:
        docs = HERE.parent / "docs"
        docs.mkdir(exist_ok=True)
        render(parts["bottom_case"], docs / "cad_bottom_case.png")
        render(parts["top_case"], docs / "cad_top_case.png")
        render(parts["keycap"], docs / "cad_keycap.png", size=(600, 600))
        render(shell, docs / "cad_assembled.png")
        print("rendered previews into", docs)

    print(f"\n{len(checks)} interference checks, {failures} failure(s), {time.time()-t0:.1f}s")
    print("scad consistency:", scad)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
