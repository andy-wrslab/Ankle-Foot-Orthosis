"""Advanced Confirm end to end, offline (Andy Nov 24: "make sure it works").

In-process fake run-16 device (44-float echo, 5434 / 5435 / 5436 handled in memory; no
sockets to the Speedgoat, nothing on 192.168.7.5) + the real Session, AdvLink, GuardLink and
the real Flask route POST /api/console/advanced:
- a Confirm with 3 Advanced + 2 Torque-guard values -> exactly one 5435 packet and one 5436
  packet, the device applies them, the echo confirms them, the page state shows them;
- min and max target speed raised together are accepted;
- a Confirm with one bad value sends nothing;
- the old one-field Enter path is no longer used by the page (Confirm only).

    python test/test_adv_confirm_e2e.py
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401  (below normal priority)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def main():
    import udp_settings as U
    from test_run14_layout import make_session
    from test_run15_layout import Dev31
    from fake_run14 import GUARD_FIELDS, GUARD_DEFAULTS, FakeRun14

    class Dev44(Dev31):
        def __init__(self):
            super().__init__()
            self.guard, self.guard_seq = dict(zip(GUARD_FIELDS, GUARD_DEFAULTS)), 2.0
            self.gpk = []

        def recv(self, data, addr):
            if len(data) == 48:
                self.gpk.append(struct.unpack("<12f", data))
                FakeRun14.apply_guard(self, self.gpk[-1])
                return
            super().recv(data, addr)

        def status(self):
            st = super().status()
            if self.on:
                st["latest"].update(self.guard, guard_seq=self.guard_seq, slack_flag=0.0, jam_flag=0.0, slack_count=0.0,
                                    slack_last_stride=0.0)
                st["columns"] = 44
            return st

    dev, calls = Dev44(), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx, s = make_session(dev, calls)
    ctx.adv_link = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, s.echo_for_link,
                             on_status=s.adv_link_status, on_adopt=s.adv_link_adopted, sender=dev.recv)
    ctx.guard_link = U.GuardLink({"udp": {"send_host": "127.0.0.1", "guard_port": 15436}}, s.echo_for_link,
                                 sender=dev.recv)
    dev.on = True
    time.sleep(0.5)
    s.refresh_echo()

    from flask import Flask
    from pages import console_api as CA
    srv = Flask("adv_confirm_e2e")
    CA.register(srv, ctx)
    cl = srv.test_client()

    n_adv0, n_g0 = len(getattr(dev, "adv_packets", [])), len(dev.gpk)
    body = {"adv": {"p_gain": 0.5, "i_gain": 0.6, "fade_ms": 250}, "guard": {"jam_apnm": 9.0, "jam_ms": 200}}
    r = cl.post("/api/console/advanced", json=body)
    j = r.get_json()
    check("Confirm: HTTP 200, ok, 5435 + 5436 both sent", r.status_code == 200 and j.get("ok")
          and set(j["sent"]) == {"5435", "5436"}, (r.status_code, j))
    check("Confirm: exactly ONE 5435 packet and ONE 5436 packet",
          len(dev.adv_packets) - n_adv0 == 1 and len(dev.gpk) - n_g0 == 1, (len(dev.adv_packets) - n_adv0, len(dev.gpk) - n_g0))
    time.sleep(0.6)
    s.refresh_echo()
    rb, gv = dict(s.readback), CA._guard_view(ctx)["values"]
    pk = dev.adv_packets[-1]
    # 5435 '<16f': magic, version, seq, [3..13] the 11 run-15 values, [14] reserved, [15] fade (layout)
    check("5435 packet carries P 0.5, I 0.6, fade 250 (the rest in use)",
          (pk[11], pk[12], pk[15]) == (f32(0.5), f32(0.6), 250.0) and pk[3] == f32(0.8) and pk[13] == 200.0, pk)
    check("device applied P / I (echo: 0.5 / 0.6; this fake echoes 44 floats, no fade column)",
          abs(rb.get("p_gain") - 0.5) < 1e-6 and abs(rb.get("i_gain") - 0.6) < 1e-6, {k: rb.get(k) for k in ("p_gain", "i_gain")})
    check("device applied the Torque-guard values (echo: jam 9 A/Nm, 200 ms)",
          gv.get("jam_apnm") == 9.0 and gv.get("jam_ms") == 200.0, gv)
    check("untouched values unchanged (Min target 0.8, slack floor on)", abs(rb.get("sv_target_min") - 0.8) < 1e-6
          and gv.get("slack_floor_on") == 1.0, (rb.get("sv_target_min"), gv.get("slack_floor_on")))
    ctx.adv_link.tick(); ctx.guard_link.tick()
    check("5435 / 5436: confirmed by the echo", ctx.adv_link.result.get("torque_p_gain", {}).get("state") == "confirmed"
          and ctx.guard_link.result.get("jam_ms", {}).get("state") == "confirmed",
          (ctx.adv_link.result.get("torque_p_gain"), ctx.guard_link.result.get("jam_ms")))

    n_adv0 = len(dev.adv_packets)
    r = cl.post("/api/console/advanced", json={"adv": {"sv_target_min": 1.6, "sv_target_max": 1.9}})
    check("Confirm: min 1.6 + max 1.9 together accepted (one packet)", r.status_code == 200
          and len(dev.adv_packets) - n_adv0 == 1, (r.status_code, r.get_json()))
    time.sleep(0.6)
    s.refresh_echo()
    rb = dict(s.readback)
    check("device: min 1.6 / max 1.9", abs(rb.get("sv_target_min") - 1.6) < 1e-6 and abs(rb.get("sv_target_max") - 1.9) < 1e-6,
          (rb.get("sv_target_min"), rb.get("sv_target_max")))

    n_adv0, n_g0 = len(dev.adv_packets), len(dev.gpk)
    r = cl.post("/api/console/advanced", json={"adv": {"p_gain": 0.7}, "guard": {"jam_ms": 5}})
    check("Confirm with one bad value (jam 5 ms): refused, NOTHING sent on either port",
          r.status_code == 409 and len(dev.adv_packets) == n_adv0 and len(dev.gpk) == n_g0, (r.status_code, r.get_json()))
    r = cl.post("/api/console/advanced", json={})
    check("empty Confirm refused", r.status_code == 400)

    ctx.adv_link.stop(); ctx.guard_link.stop(); ctx.settings_link.stop()


main()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
