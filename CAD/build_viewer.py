"""Inject CAD/out/bottom_box_mesh.json into viewer_template.html -> CAD/out/viewer.html

Usage: CAD/.venv/Scripts/python CAD/build_viewer.py   (run backpack_bottom_cap.py first)
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = (HERE / "out" / "bottom_box_mesh.json").read_text().replace("</", "<\\/")
html = (HERE / "viewer_template.html").read_text(encoding="utf-8").replace("__DATA__", data)
out = HERE / "out" / "viewer.html"
out.write_text(html, encoding="utf-8")
print("wrote", out, f"{out.stat().st_size/1e6:.2f} MB")
