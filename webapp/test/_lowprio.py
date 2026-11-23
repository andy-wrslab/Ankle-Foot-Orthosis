"""Imported by every test / soak tool: run below normal priority so a test never
starves the live app (:8050) on the same PC. Child processes (test apps, Chrome)
inherit it, and their receivers then stay low too (utils.raise_priority)."""
import os

try:
    import psutil
    if os.name == "nt":
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    else:
        os.nice(5)
except Exception:
    pass
