"""Top bar never overflows (harness: at 1280 / 1440 px "Drive fault (STO)" and "Model time"
ran past the right edge with a long side chip). Static check of the CSS / JS (no browser):
side chip ellipsis with its full text in the title, status button never shrinks, Model time
gives way first.

    python test/test_topbar_fit.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name, flush=True)
    if not cond:
        FAILS.append(name)


css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
check("side chip: max-width + ellipsis + no wrap + may shrink",
      ".topbar .side-chip { display: inline-block; max-width: 220px; min-width: 0; flex: 0 1 auto; overflow: hidden;" in css
      and "text-overflow: ellipsis" in css)
check("side chip: full text in its title", "chip.title = sd.chip + ' · ' +" in js)
check("status button never shrinks", ".topbar .status-btn { flex: none; }" in css)
check("Model time gives way first (shrinks to nothing before anything else)",
      ".topbar .meta > span:first-child { flex: 0 100 auto; min-width: 0; overflow: hidden; white-space: nowrap; }" in css
      and ".topbar .meta { min-width: 0; flex: 0 1 auto; }" in css)
check("Model time label hidden below 1600 px", "@media (max-width: 1600px) { .topbar .meta .mt-label { display: none; } }" in css)
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
