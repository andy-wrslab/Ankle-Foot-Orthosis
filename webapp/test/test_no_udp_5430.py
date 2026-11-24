"""UDP 5430 is gone (Nov 24): nothing in the model read it (16e: UDP Receive2 -> ControlParameters
-> Pot_h is read by nothing; every command comes in on 5431). No code path may open or send to
5430, and config has no param_port. Seconds, no browser, no target (sockets are faked).

    python test/test_no_udp_5430.py
"""
import ast
import glob
import inspect
import os
import socket
import sys
import tempfile
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def static():
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    check("config.yaml: no udp.param_port", "param_port" not in (cfg.get("udp") or {}), cfg.get("udp"))
    check("config.yaml: no 'commands' params block (params_used_by_model / param_echo_columns)",
          not (cfg.get("commands") or {}).get("params_used_by_model") and "param_echo_columns" not in (cfg.get("commands") or {}))

    def has_5430(v):
        if isinstance(v, dict):
            return any(has_5430(x) for x in v.values())
        if isinstance(v, list):
            return any(has_5430(x) for x in v)
        return v == 5430
    check("config.yaml: no value 5430 anywhere", not has_5430(cfg))
    lit = []
    for p in glob.glob(os.path.join(APP, "*.py")) + glob.glob(os.path.join(APP, "pages", "*.py")):
        for node in ast.walk(ast.parse(open(p, encoding="utf-8").read())):
            if isinstance(node, ast.Constant) and node.value == 5430:
                lit.append((os.path.basename(p), node.lineno))
    check("no integer 5430 in the app code", not lit, lit)
    js = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(APP, "assets", "*.js")))
    check("page: no UDP 5430 box (advNc / adv-nc)", "advNc" not in js and "adv-nc" not in js)
    import commands
    import constants
    import network
    check("network: no send_param_packet, constants: no PARAM_FMT", not hasattr(network, "send_param_packet")
          and not hasattr(constants, "PARAM_FMT"))
    sig = list(inspect.signature(commands.CommandState.__init__).parameters)
    check("CommandState: no send_params, no params / set_param / model_params",
          "send_params" not in sig and not hasattr(commands.CommandState, "set_param")
          and not hasattr(commands.CommandState, "model_params") and not hasattr(commands, "PARAMS"), sig)
    api = open(os.path.join(APP, "pages", "console_api.py"), encoding="utf-8").read()
    check("api: no param route / params_used_by_model", "params_used_by_model" not in api and "/api/console/param" not in api)


class FakeSock:
    ports = []

    def __init__(self, *a, **k):
        pass

    def sendto(self, data, addr):
        FakeSock.ports.append(("send", addr[1]))
        return len(data)

    def bind(self, addr):
        FakeSock.ports.append(("bind", addr[1]))

    def setsockopt(self, *a):
        pass

    def settimeout(self, *a):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def runtime():
    """Every page action that sends (5431 toggles / pulses, 5434 / 5435 / 5436 presses) with the
    real network senders and the production config ports, the sockets faked."""
    real = socket.socket
    socket.socket = FakeSock
    try:
        cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
        import network
        from commands import CommandState
        rb = {"cmd_motor": 0.0, "cmd_assist": 0.0, "cmd_k": 1.0}
        cs = CommandState(cfg, os.path.join(tempfile.mkdtemp(), "last.json"), network.send_control_packet, lambda: dict(rb))
        cs.press_toggle("motor")
        cs.press_toggle("k")
        for name in ("zero", "calibrate", "reset"):
            cs.pulse(name)
            time.sleep(0.3)
        import udp_settings as U
        from fake_run14 import ADV_DEFAULTS, ADV_FIELDS, GUARD_DEFAULTS, GUARD_FIELDS
        row = dict(side=0.0, bif_mass_kg=70.0, assist_mode=3.0, fixed_k_pct=5.0, gyro_cal_request=0.0, settings_seq=1.0,
                   adv_seq=1.0, guard_seq=1.0, standstill_fade_ms=200.0, **dict(zip(ADV_FIELDS, ADV_DEFAULTS)),
                   **dict(zip(GUARD_FIELDS, GUARD_DEFAULTS)))
        for cls, field, val in ((U.SettingsLink, "mass", 72.0), (U.AdvLink, "torque_p_gain", 0.5), (U.GuardLink, "jam_ms", 200)):
            lk = cls(cfg, lambda: (dict(row), 0.01, 45), start_thread=False)
            lk.tick()
            r = lk.press(field, val)
            assert r["ok"], (cls.__name__, r)
    finally:
        socket.socket = real
    ports = {p for _, p in FakeSock.ports}
    check("sends happened (5431 / 5434 / 5435 / 5436)", {5431, 5434, 5435, 5436} <= ports, sorted(ports))
    check("nothing opened or sent on 5430", 5430 not in ports, FakeSock.ports)


if __name__ == "__main__":
    static()
    runtime()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
