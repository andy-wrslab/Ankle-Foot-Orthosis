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
check("no Model time in the top bar (Andy 14:57)", 'id="mtime"' not in js and "mt-label" not in js)
check("status area never shrinks; the session bar (side chip) gives way", ".topbar .meta { flex: none; }" in css
      and ".topbar .session-bar { min-width: 0; }" in css)
check("entries centred: ID, Mass, K %, Advanced", "#sPart, #sMass, #kPct, .k-field .input, .adv-sec .input, .adv-grid .input, .adv-in { text-align: center; }" in css)
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
