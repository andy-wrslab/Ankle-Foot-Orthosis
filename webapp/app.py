"""AFO web app: Home, Live, Trials, Run control and Teensy in one app.

Start with AFO_app.bat (conda base). Serves http://<this PC>:8050. The UDP
receiver, the MATLAB engine and long jobs run in supervised background
workers, so the Live page keeps updating whatever the other pages do.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time

from werkzeug.serving import make_server

APP_DIR = os.path.dirname(os.path.abspath(__file__))
_logger = logging.getLogger("afo.app")


class AppContext:
    def __init__(self, cfg) -> None:
        from workers import JobManager, LiveSupervisor, MatlabWorker, StatusPoller, TrainingSupervisor
        from teensy_tools import SerialMonitor
        from pages.trials import TrialStore
        from pages.runctl import RunControl

        self.app_dir = APP_DIR
        paths = cfg.setdefault("paths", {})
        for key in ("cache_dir", "log_dir"):
            p = paths.get(key, key.replace("_dir", "s" if key == "log_dir" else ""))
            paths[key] = p if os.path.isabs(p) else os.path.join(APP_DIR, p)
            os.makedirs(paths[key], exist_ok=True)
        mpaths = [p if os.path.isabs(p) else os.path.join(APP_DIR, p) for p in paths.get("matlab_paths", ["matlab"])]
        self.cfg = cfg
        self.stopping = threading.Event()
        self.jobs = JobManager()
        self.live = LiveSupervisor(cfg, paths["log_dir"])
        self.poller = StatusPoller(cfg)
        self.matlab = MatlabWorker(mpaths, paths["log_dir"])
        self.serial = SerialMonitor(cfg)
        self.trials = TrialStore(cfg, self.jobs, os.path.join(paths["cache_dir"], "trials"))
        self.runctl = RunControl(self)
        from commands import CommandState
        from network import send_control_packet
        self.training = TrainingSupervisor(cfg, APP_DIR, paths["log_dir"])

        def readback():
            # bus values (statusword, ...) from 5431; the commands latched in the
            # model (cmd_*) from the console packet on 5433
            rb = dict(self.training.latest())
            rb.update(self.live.readback())
            return rb

        self.commands = CommandState(cfg, os.path.join(paths["log_dir"], "last_command.json"),
                                     send_control_packet, readback)
        from session import SessionSetup
        self.session = SessionSetup(self)
        from imu_cal import ImuCal
        self.imu_cal = ImuCal(self)
        self.commands.guard = self.session.guard    # Motor/Assist blocked on a side problem
        # run 14: session settings over UDP 5434, confirmed by the 18-float 5433 echo
        from udp_settings import SettingsLink
        self.settings_link = SettingsLink(cfg, self.session.echo_for_link,
                                          view_only=bool((cfg.get("console") or {}).get("view_only", False)),
                                          on_status=self.session.link_status, on_adopt=self.session.link_adopted)
        # run 15: the 11 Advanced values over UDP 5435, confirmed by the 31-float 5433 echo
        from udp_settings import AdvLink
        self.adv_link = AdvLink(cfg, self.session.echo_for_link,
                                view_only=bool((cfg.get("console") or {}).get("view_only", False)),
                                on_status=self.session.adv_link_status, on_adopt=self.session.adv_link_adopted)
        # run 16: the torque guard over UDP 5436, confirmed by the 44-float 5433 echo
        from udp_settings import GuardLink
        self.guard_link = GuardLink(cfg, self.session.echo_for_link,
                                    view_only=bool((cfg.get("console") or {}).get("view_only", False)))
        self.commands.frozen = self.session.link_frozen
        self.commands.echo_expected = lambda: bool(self.session.profile().get("console_expected"))
        from filelog import FileLogRuns
        self.filelog = FileLogRuns(self)

    def trial_sources(self):
        return self.trials.sources()

    def trials_current(self):
        return self.trials.path

    def start(self) -> None:
        self.live.start()
        self.poller.start()
        self.training.start()

        def session_poll():
            while not self.stopping.wait(5.0):
                try:
                    self.session.refresh_readback()
                except Exception:
                    logging.getLogger("afo.session").exception("session readback failed")
        threading.Thread(target=session_poll, name="session-poll", daemon=True).start()

    def shutdown(self) -> None:
        self.stopping.set()
        self.serial.stop()
        self.live.shutdown()
        self.training.shutdown()
        self.matlab.shutdown()


def _setup_logging(log_dir: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, time.strftime("afo_app_%Y%m%d_%H%M%S.log"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(fh)
    return path


def main() -> None:
    from utils import load_config
    cfg = load_config()
    log_dir = cfg.get("paths", {}).get("log_dir", "logs")
    log_dir = log_dir if os.path.isabs(log_dir) else os.path.join(APP_DIR, log_dir)
    _logger.info("logging to %s", _setup_logging(log_dir))
    ctx = AppContext(cfg)
    ctx.start()
    from pages.shell import build_app
    app = build_app(ctx)
    dash_cfg = cfg.get("dash") or {}
    host, port = str(dash_cfg.get("host", "0.0.0.0")), int(dash_cfg.get("port", 8050))
    server = make_server(host, port, app.server, threaded=True)

    def _shutdown(*_a):
        if ctx.stopping.is_set():
            os._exit(1)
        _logger.info("shutting down")
        ctx.stopping.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)
    _logger.info("AFO app on http://%s:%d (live data on UDP %s)", host, port, cfg["udp"]["listen_port"])
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        ctx.shutdown()
        server.server_close()
        _logger.info("stopped")


if __name__ == "__main__":
    main()
