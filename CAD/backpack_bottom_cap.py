#!/usr/bin/env python
"""Backpack bottom-box cap -- concept A, rev 2: slide-back shroud with cable pass-throughs.

Frame (mm):  X = box width (left/right as seen from the open face)
             Y = depth, +Y goes INTO the box; the open face is at y=0 and faces -Y
             Z = up, z=0 is the top of the base plate (bottom of the box)

Rev 2, after a second look at the photo:
  * the two existing screws stand VERTICALLY on the shelf the heatsink hangs under, so the
    cap has a horizontal flange that slides back over that shelf; the screws enter rear-open
    slots in the flange and the nuts go on top
  * the power and data cables leave through three notches in the front plate; a scalloped
    clamp bar screwed over the bottom edge closes them into holes and pinches the cables
    (closed holes would be impossible to fit over cables that already carry connectors)

Every number in PARAMS is an ESTIMATE eyeballed from the photo. Measure, edit, re-run.

Usage:   CAD/.venv/Scripts/python CAD/backpack_bottom_cap.py [--show]
         --show   opens the interactive VTK window at the end
Outputs: CAD/out/  (STEP + STL of the cap and clamp bar, STEP + GLB of the mock assembly,
                    mesh JSON for the web viewer)
"""
import inspect
import json
import math
import sys
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# ------------------------------------------------------------------ PARAMS
# --- existing hardware (estimated from the photo) ---
BOX_W, BOX_D, BOX_H = 150.0, 100.0, 110.0   # bottom box outer size
BOX_WALL    = 4.0
SHELF_Z     = 78.0            # top surface of the shelf the heatsink hangs under
SHELF_T     = 4.0
STUD_PITCH  = 120.0           # X spacing of the two vertical screws standing on the shelf
STUD_Y      = 6.0             # how far behind the open face they stand
STUD_H      = 8.0             # thread showing above the shelf
STUD_D      = 3.0             # M3

# --- cap ---
T           = 2.4             # wall thickness
CLR         = 0.5             # cap-to-box gap
CHEEK_DEPTH = 20.0            # side flanges wrap this far back along the box sides
BOT_Z       = 3.0             # bottom edge above the base plate
CAP_TOP     = BOX_H - 2.0     # top edge, just under the top plate
RIB_D       = 16.0            # flange reach over the shelf, measured from the box face
SLOT_W      = 3.4             # M3 clearance
CORNER_R    = 3.0             # outer vertical corner radius
VENT_N, VENT_W, VENT_L, VENT_PITCH = 9, 3.0, 20.0, 8.0
VENT_TOP_Z  = SHELF_Z - 5.0   # vents sit in front of the heatsink

# cable pass-throughs in the front plate: (name, x centre, width, top of opening z).
# They are open to the bottom edge; the clamp bar closes them.
OPENINGS = [("power",   -48.0, 16.0, 34.0),
            ("loom",     -8.0, 22.0, 30.0),
            ("sensors",  38.0, 26.0, 26.0)]

# clamp bar over the bottom edge
BAR_H, BAR_CUT = 12.0, 7.0    # bar height; scallop depth from its top edge
BAR_X        = (-70.0, 64.0)  # bar span in X
BAR_SCREWS_X = (-64.0, 58.0)
BAR_SCREW_Z  = BOT_Z + BAR_H / 2
PAD_D        = 5.0            # captive-nut pad depth behind the plate
HOLE_BOT_Z   = BOT_Z + BAR_H - BAR_CUT   # where the closed holes bottom out

CAP_COLOR = (0.93, 0.48, 0.12)   # orange so the new parts stand out in renders
BAR_COLOR = (0.80, 0.36, 0.08)

# mock cables for context: (name, x, radius, color, path of (y, z) points)
_P_POWER = [(40, 20), (8, 22), (-6, 22), (-22, 14), (-40, 6), (-80, 5)]
_P_LOOM = [(40, 16), (8, 18), (-6, 18), (-22, 12), (-40, 8), (-80, 7)]
_P_SENS = [(40, 14), (8, 16), (-6, 16), (-22, 10), (-40, 6), (-80, 5)]
CABLES = [("cable_power_red", -52.0, 2.6, (0.85, 0.08, 0.08), _P_POWER),
          ("cable_power_blk", -44.0, 2.6, (0.05, 0.05, 0.05), _P_POWER),
          ("cable_loom",       -8.0, 4.5, (0.55, 0.55, 0.58), _P_LOOM),
          ("cable_sensor_1",   31.0, 2.0, (0.92, 0.92, 0.92), _P_SENS),
          ("cable_sensor_2",   38.0, 2.0, (0.92, 0.92, 0.92), _P_SENS),
          ("cable_sensor_3",   45.0, 2.0, (0.92, 0.92, 0.92), _P_SENS)]

# sanity: the named XZ plane must have local-y == +Z for the cutters below
assert abs(cq.Plane.named("XZ").yDir.z - 1.0) < 1e-9, "XZ plane orientation changed"

YI, YO = -CLR, -CLR - T                       # inner / outer face of the front plate


def params_dict() -> dict:
    """Key numbers, for the web viewer's dimension table (mm)."""
    return {
        "box_w": BOX_W, "box_d": BOX_D, "box_h": BOX_H,
        "cap_w": BOX_W + 2 * (CLR + T), "cap_h": CAP_TOP - BOT_Z, "cap_depth": CHEEK_DEPTH + CLR + T,
        "wall": T, "clearance": CLR, "rib_d": RIB_D, "slot_w": SLOT_W, "corner_r": CORNER_R,
        "shelf_z": SHELF_Z, "stud_pitch": STUD_PITCH, "stud_y": STUD_Y, "stud_h": STUD_H,
        "openings": [{"name": n, "x": x, "w": w, "top": zt, "bottom": HOLE_BOT_Z} for n, x, w, zt in OPENINGS],
        "bar_h": BAR_H, "vents": f"{VENT_N} x {VENT_W}x{VENT_L}",
    }


def _xz(y: float) -> cq.Workplane:
    """Workplane parallel to the front plate at depth y (local x = X, local y = Z)."""
    return cq.Workplane("XZ", origin=(0, y, 0))


# ------------------------------------------------------------------ CAP
def build_cap() -> cq.Workplane:
    plate_w = BOX_W + 2 * (CLR + T)
    plate = (cq.Workplane("XY").box(plate_w, T, CAP_TOP - BOT_Z, centered=(True, False, False))
             .translate((0, YO, BOT_Z)))
    cheek_r = (cq.Workplane("XY").box(T, CHEEK_DEPTH + CLR + T, CAP_TOP - BOT_Z, centered=(False, False, False))
               .translate((BOX_W / 2 + CLR, YO, BOT_Z)))
    cheek_l = cheek_r.mirror("YZ")
    # horizontal flange that rides over the shelf and hooks the vertical screws
    rib_w = BOX_W - 2 * BOX_WALL - 2 * CLR
    rib = (cq.Workplane("XY").box(rib_w, RIB_D + CLR + T, T, centered=(True, False, False))
           .translate((0, YO, SHELF_Z)))
    cap = plate.union(cheek_r).union(cheek_l).union(rib)

    try:
        cap = cap.edges("|Z").edges("<Y").fillet(CORNER_R)
    except Exception as e:  # noqa: BLE001
        print("corner fillet skipped:", e)

    # captive-nut pads behind the plate for the clamp-bar screws
    for bx in BAR_SCREWS_X:
        pad = (cq.Workplane("XY").box(10, PAD_D + T, 11, centered=(True, False, False))
               .translate((bx, YO, BAR_SCREW_Z - 4.5)))
        cap = cap.union(pad)

    # rear-open slots in the flange: cap slides back until the screws bottom out in them
    slot_end = RIB_D + 5
    slot_len = slot_end - (STUD_Y - SLOT_W / 2)
    slots = (cq.Workplane("XY", origin=(0, 0, SHELF_Z + T / 2))
             .pushPoints([(-STUD_PITCH / 2, (slot_end + STUD_Y - SLOT_W / 2) / 2),
                          (STUD_PITCH / 2, (slot_end + STUD_Y - SLOT_W / 2) / 2)])
             .slot2D(slot_len, SLOT_W, angle=90).extrude(T, both=True))
    cap = cap.cut(slots)

    mid = _xz(YO + T / 2)

    # vent slots in front of the heatsink
    vents = (mid.center(0, VENT_TOP_Z - VENT_L / 2)
             .rarray(VENT_PITCH, 1, VENT_N, 1)
             .slot2D(VENT_L, VENT_W, angle=90).extrude(T, both=True))
    cap = cap.cut(vents)

    # cable notches, open to the bottom edge
    for _name, x, w, ztop in OPENINGS:
        zlow = BOT_Z - 5
        notch = (mid.center(x, (ztop + zlow) / 2).slot2D(ztop - zlow, w, angle=90)
                 .extrude(T, both=True))
        cap = cap.cut(notch)

    # clamp-bar screw holes + hex pockets for captive M3 nuts (from the back of the pads)
    pts = [(bx, BAR_SCREW_Z) for bx in BAR_SCREWS_X]
    holes = _xz(YI + PAD_D + 1).pushPoints(pts).circle(1.7).extrude(PAD_D + T + 3)
    pockets = _xz(YI + PAD_D + 1).pushPoints(pts).polygon(6, 6.6).extrude(1 + 2.8)
    cap = cap.cut(holes).cut(pockets)
    return cap


def build_bar() -> cq.Workplane:
    """Scalloped clamp bar: closes the notches into holes and pinches the cables."""
    x0, x1 = BAR_X
    y0 = YO - T
    bar = (cq.Workplane("XY").box(x1 - x0, T, BAR_H, centered=(False, False, False))
           .translate((x0, y0, BOT_Z)))
    mid = _xz(y0 + T / 2)
    for _name, x, w, _ztop in OPENINGS:
        top = BOT_Z + BAR_H + 5
        cut = mid.center(x, (top + HOLE_BOT_Z) / 2).slot2D(top - HOLE_BOT_Z, w, angle=90).extrude(T, both=True)
        bar = bar.cut(cut)
    holes = mid.pushPoints([(bx, BAR_SCREW_Z) for bx in BAR_SCREWS_X]).circle(1.7).extrude(T, both=True)
    bar = bar.cut(holes)
    try:
        bar = bar.edges("|Y").edges("<Z").fillet(0.8)
    except Exception as e:  # noqa: BLE001
        print("bar fillet skipped:", e)
    return bar


def build_nuts() -> cq.Workplane:
    """M3 nuts on the vertical screws, bearing on top of the flange."""
    return (cq.Workplane("XY", origin=(0, 0, SHELF_Z + T + 0.1))
            .pushPoints([(-STUD_PITCH / 2, STUD_Y), (STUD_PITCH / 2, STUD_Y)])
            .polygon(6, 6.35).extrude(2.4))


def build_bar_screws() -> cq.Workplane:
    """M3 button heads in front of the clamp bar."""
    return (_xz(YO - T - 0.1).pushPoints([(bx, BAR_SCREW_Z) for bx in BAR_SCREWS_X])
            .circle(2.75).extrude(2.6))


# ------------------------------------------------------------------ CONTEXT (mock of what exists)
def _cable(x: float, r: float, pts) -> cq.Workplane:
    path = cq.Workplane("YZ", origin=(x, 0, 0)).spline(pts)
    prof = cq.Workplane("XZ", origin=(x, pts[0][0], pts[0][1])).circle(r)
    return prof.sweep(path, isFrenet=True)


def build_context() -> dict:
    ctx = {}
    ctx["base_plate"] = (cq.Workplane("XY").box(220, 180, 6, centered=(True, False, False))
                         .translate((0, -80, -6)), (0.16, 0.16, 0.17))

    outer = cq.Workplane("XY").box(BOX_W, BOX_D, BOX_H, centered=(True, False, False))
    cavity = (cq.Workplane("XY")
              .box(BOX_W - 2 * BOX_WALL, BOX_D - BOX_WALL + 1, BOX_H - 2 * BOX_WALL, centered=(True, False, False))
              .translate((0, -1, BOX_WALL)))
    shelf = (cq.Workplane("XY").box(BOX_W - 2 * BOX_WALL, BOX_D - BOX_WALL, SHELF_T, centered=(True, False, False))
             .translate((0, 0, SHELF_Z - SHELF_T)))
    ctx["bottom_box"] = (outer.cut(cavity).union(shelf), (0.09, 0.09, 0.09))

    ctx["top_plate"] = (cq.Workplane("XY").box(BOX_W + 20, BOX_D + 10, 6, centered=(True, False, False))
                        .translate((0, -5, BOX_H)), (0.78, 0.79, 0.80))

    hs_top = SHELF_Z - SHELF_T
    hs_base = (cq.Workplane("XY").box(120, 55, 4, centered=(True, False, False))
               .translate((0, 4, hs_top - 4)))
    fins = (cq.Workplane("XY").rarray(5, 1, 24, 1)
            .box(1.5, 55, 18, centered=(True, False, False))
            .translate((0, 4, hs_top - 22)))
    ctx["heatsink"] = (hs_base.union(fins), (0.12, 0.42, 0.85))

    ctx["carrier_pcb"] = (cq.Workplane("XY").box(110, 80, 1.6, centered=(True, False, False))
                          .translate((0, 10, 12)), (0.10, 0.45, 0.20))
    ctx["easycat"] = (cq.Workplane("XY").box(53, 68, 1.6, centered=(False, False, False))
                      .translate((-8, 12, 26)), (0.75, 0.10, 0.12))
    ctx["teensy"] = (cq.Workplane("XY").box(18, 62, 1.6, centered=(False, False, False))
                     .translate((-50, 12, 26)), (0.10, 0.50, 0.25))

    # the two existing screws: vertical, standing on the shelf near its front corners
    ctx["studs"] = (cq.Workplane("XY", origin=(0, 0, SHELF_Z))
                    .pushPoints([(-STUD_PITCH / 2, STUD_Y), (STUD_PITCH / 2, STUD_Y)])
                    .circle(STUD_D / 2).extrude(STUD_H), (0.75, 0.75, 0.75))

    for name, x, r, col, path in CABLES:
        try:
            ctx[name] = (_cable(x, r, path), col)
        except Exception as e:  # noqa: BLE001
            print(f"{name} sweep skipped:", e)
    return ctx


def make_assembly(cap, nuts, bar, screws, ctx, exploded: float = 0.0) -> cq.Assembly:
    a = cq.Assembly(name="backpack_bottom_box")
    for name, (shape, color) in ctx.items():
        a.add(shape, name=name, color=cq.Color(*color))
    a.add(cap.translate((0, -exploded, 0)), name="cap", color=cq.Color(*CAP_COLOR))
    a.add(nuts.translate((0, -exploded, 0)), name="nuts", color=cq.Color(0.6, 0.6, 0.6))
    a.add(bar.translate((0, -1.6 * exploded, 0)), name="clamp_bar", color=cq.Color(*BAR_COLOR))
    a.add(screws.translate((0, -1.6 * exploded, 0)), name="bar_screws", color=cq.Color(0.35, 0.35, 0.37))
    return a


def mesh_json(parts) -> list:
    out = []
    for name, shape, color in parts:
        solid = shape.val() if isinstance(shape, cq.Workplane) else shape
        verts, tris = solid.tessellate(0.25, 0.3)
        out.append({"name": name, "color": color,
                    "v": [round(c, 2) for v in verts for c in v.toTuple()],
                    "i": [i for t in tris for i in t]})
    return out


# ------------------------------------------------------------------ MAIN
if __name__ == "__main__":
    cap, nuts, bar, screws = build_cap(), build_nuts(), build_bar(), build_bar_screws()
    ctx = build_context()

    bb = cap.val().BoundingBox()
    print(f"cap bbox: X {bb.xmin:.1f}..{bb.xmax:.1f}  Y {bb.ymin:.1f}..{bb.ymax:.1f}  "
          f"Z {bb.zmin:.1f}..{bb.zmax:.1f}   volume {cap.val().Volume()/1000:.1f} cm^3, "
          f"bar {bar.val().Volume()/1000:.1f} cm^3")

    cq.exporters.export(cap, str(OUT / "bottom_cap.step"))
    cq.exporters.export(cap, str(OUT / "bottom_cap.stl"), tolerance=0.05, angularTolerance=0.1)
    cq.exporters.export(bar, str(OUT / "clamp_bar.step"))
    cq.exporters.export(bar, str(OUT / "clamp_bar.stl"), tolerance=0.05, angularTolerance=0.1)

    assy = make_assembly(cap, nuts, bar, screws, ctx)
    assy.export(str(OUT / "bottom_box_assy.step"))
    assy.export(str(OUT / "bottom_box_assy.glb"))

    # web viewer data: swept cables are heavy, so ship their paths and let the viewer draw tubes
    parts = ([(n, s, c) for n, (s, c) in ctx.items() if not n.startswith("cable_")]
             + [("cap", cap, CAP_COLOR), ("nuts", nuts, (0.6, 0.6, 0.6)),
                ("clamp_bar", bar, BAR_COLOR), ("bar_screws", screws, (0.35, 0.35, 0.37))])
    data = {"params": params_dict(), "parts": mesh_json(parts),
            "cables": [{"name": n, "x": x, "r": r, "color": c, "path": p} for n, x, r, c, p in CABLES]}
    (OUT / "bottom_box_mesh.json").write_text(json.dumps(data))
    print("exports written to", OUT)

    if "--show" in sys.argv:
        from cadquery.vis import show
        show(assy)
