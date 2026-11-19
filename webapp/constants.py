# Colour-blind-safe palette (Okabe-Ito, with a darker yellow and grey for
# contrast on white). Index order is the channel order of each plot.
COLOR_CYCLE = [
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # bluish green
    "#D55E00",  # vermillion
    "#56B4E9",  # sky blue
    "#CC79A7",  # reddish purple
    "#8C7A00",  # dark yellow
    "#4D4D4D",  # grey
]

CONFIG_FILE = "config.yaml"
CONTROL_FMT = "<6f"
UPDATE_MS = 10
N_WINDOW_SEC = 10
# The Speedgoat streams at 1024 Hz (model dt = 1/1024 s, measured 2026-11-19).
SAMPLE_RATE_HZ = 1024
# Width of the min/max display bins, anchored to absolute model time.
BIN_WIDTH_SEC = 0.02
PARAM_FMT = "<5f"
