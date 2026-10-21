"""Render PNG views of the bottom-box cap mock assembly with CadQuery's built-in VTK viewer.

Usage: CAD/.venv/Scripts/python CAD/render_views.py
Writes CAD/out/view_*.png
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cadquery.vis import show  # noqa: E402

import backpack_bottom_cap as m  # noqa: E402

cap, nuts, bar, screws = m.build_cap(), m.build_nuts(), m.build_bar(), m.build_bar_screws()
ctx = m.build_context()
installed = m.make_assembly(cap, nuts, bar, screws, ctx)
exploded = m.make_assembly(cap, nuts, bar, screws, ctx, exploded=45.0)
cap_only = m.make_assembly(cap, nuts, bar, screws, {})
no_bar = m.make_assembly(cap, nuts, bar.translate((0, -60, 0)), screws.translate((0, -60, 0)), ctx)

FOCUS = (0, 15, 55)
VIEWS = {
    "view_iso_front":     (installed, (-260, -330, 230), FOCUS),
    "view_iso_front_R":   (installed, (300, -300, 190), FOCUS),
    "view_front":         (installed, (0, -470, 60), FOCUS),
    "view_iso_exploded":  (exploded, (-260, -380, 240), FOCUS),
    "view_cables":        (no_bar, (-120, -230, 110), (-5, 0, 22)),
    "view_cap_only_back": (cap_only, (230, 320, 200), FOCUS),
}

for name, (obj, pos, focus) in VIEWS.items():
    out = m.OUT / f"{name}.png"
    try:
        show(obj, screenshot=str(out), interact=False, edges=False, roll=0, elevation=0, azimuth=0,
             position=pos, focus=focus, viewup=(0, 0, 1),
             width=1400, height=1000, trihedron=True, fxaa=True)
        print("wrote", out, out.stat().st_size if out.exists() else "MISSING")
    except Exception as e:  # noqa: BLE001
        print("FAILED", name, repr(e))
