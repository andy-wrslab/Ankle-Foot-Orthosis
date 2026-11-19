"""Offline tests for teensy_tools (no Teensy, no arduino-cli). Run: python -m pytest test/test_teensy_tools.py"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import teensy_tools as tt  # noqa: E402


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def repos(tmp_path):
    """origin with main + fix branch; a clone ('firmware repo') still on old main."""
    origin = str(tmp_path / "origin")
    os.makedirs(os.path.join(origin, "DAQ"))
    git(origin, "init", "-q", "-b", "main")
    git(origin, "config", "user.email", "t@t"); git(origin, "config", "user.name", "t")
    open(os.path.join(origin, "DAQ", "DAQ.ino"), "w").write("// v1\n")
    open(os.path.join(origin, "DAQ", "IMU.h"), "w").write("// imu v1\n")
    git(origin, "add", "."); git(origin, "commit", "-qm", "v1")
    clone = str(tmp_path / "fw")
    subprocess.run(["git", "clone", "-q", origin, clone], check=True)
    git(origin, "switch", "-qc", "imu-fix")
    open(os.path.join(origin, "DAQ", "IMU.h"), "w").write("// imu v2 yeiBadPackets\n")
    git(origin, "commit", "-qam", "fix imu")
    git(origin, "switch", "-q", "main")
    os.makedirs(os.path.join(origin, "webapp"))
    open(os.path.join(origin, "webapp", "app.py"), "w").write("x=1\n")
    git(origin, "add", "."); git(origin, "commit", "-qm", "webapp only")
    cfg = {"paths": {"firmware_repo": clone, "arduino_cli": "", "cache_dir": str(tmp_path / "cache"),
                     "log_dir": str(tmp_path / "logs")}}
    tt._sources_cache.clear()
    return cfg, origin, clone


def test_fetch_then_newest_without_checkout(repos):
    cfg, origin, clone = repos
    before = git(clone, "rev-parse", "HEAD")
    assert tt.fetch(cfg)["error"] is None
    s = tt.sources(cfg)
    names = [b["name"] for b in s["branches"]]
    assert s["newest"] == "imu-fix" and set(names) == {"imu-fix", "main"}
    main = next(b for b in s["branches"] if b["name"] == "main")
    assert main["subject"] == "webapp only"            # GitHub's newer main, not the stale local one
    assert git(clone, "rev-parse", "HEAD") == before    # working tree untouched
    assert "yeiBadPackets" in tt.read_daq_file(cfg, "imu-fix", "IMU.h")
    assert "imu v1" in open(os.path.join(clone, "DAQ", "IMU.h")).read()
    assert "fix imu" in tt.changes_vs_main(cfg, "imu-fix")
    assert "same firmware" in tt.changes_vs_main(cfg, "main")
    d = tt.export_source(cfg, tt.resolve(cfg, "imu-fix"))
    assert "yeiBadPackets" in open(os.path.join(d, "IMU.h")).read() and d.endswith("DAQ")


def test_unpushed_local_commit_wins(repos):
    cfg, origin, clone = repos
    tt.fetch(cfg)
    git(clone, "config", "user.email", "t@t"); git(clone, "config", "user.name", "t")
    git(clone, "switch", "-q", "main"); git(clone, "merge", "-q", "--ff-only", "origin/main")
    open(os.path.join(clone, "DAQ", "DAQ.ino"), "w").write("// v3 local\n")
    git(clone, "commit", "-qam", "local tweak")
    r = tt.resolve(cfg, "main")
    assert r["subject"] == "local tweak" and "not pushed" in r["note"]


def test_worktree_source_cannot_flash(repos):
    cfg, origin, clone = repos
    open(os.path.join(clone, "DAQ", "DAQ.ino"), "a").write("// edit\n")
    tt._sources_cache.clear()
    s = tt.sources(cfg)
    assert s["worktree"]["dirty"]
    src = tt.resolve(cfg, tt.WORKTREE)
    assert "edit" in tt.read_daq_file(cfg, tt.WORKTREE, "DAQ.ino")
    assert "uncommitted" in tt.flash_block_reason({"ok": True}, src, tt.board_settings(cfg))


def test_flash_needs_matching_build(repos):
    cfg, *_ = repos
    tt.fetch(cfg)
    src, board = tt.resolve(cfg, "imu-fix"), tt.board_settings(cfg)
    assert "Build" in tt.flash_block_reason(None, src, board)
    other = tt.resolve(cfg, "main")
    assert "Build" in tt.flash_block_reason({"ok": True, "sha": other["sha"], "fqbn": board["fqbn"]}, src, board)
    assert "Build" in tt.flash_block_reason({"ok": True, "sha": src["sha"], "fqbn": BOARD_OTHER}, src, board)
    assert tt.flash_block_reason({"ok": False, "sha": src["sha"], "fqbn": board["fqbn"]}, src, board)
    assert tt.flash_block_reason({"ok": True, "sha": src["sha"], "fqbn": board["fqbn"]}, src, board) == ""


BOARD_OTHER = "teensy:avr:teensy41:usb=serial,speed=816,opt=o2std,keys=en-us"


def test_board_settings():
    d = tt.board_settings({})
    assert not d["pinned"] and d["fqbn"] == "teensy:avr:teensy41:usb=serial,speed=600,opt=o2std,keys=en-us"
    p = tt.board_settings({"teensy": {"fqbn": "teensy:avr:teensy41:speed=816,opt=o3std"}})
    assert p["pinned"] and p["options"] == {"usb": "serial", "speed": "816", "opt": "o3std", "keys": "en-us"}
    assert "CPU Speed 816 MHz" in p["summary"] and "Optimize Fastest" in p["summary"]


def test_parse_board_list_serial_and_bootloader():
    serial = {"detected_ports": [
        {"port": {"address": "COM5", "label": "COM5", "protocol": "serial",
                  "properties": {"vid": "0x16C0", "pid": "0x0483", "serialNumber": "155"}},
         "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]},
        {"port": {"address": "usb:0/140000/0/7", "label": "COM5 (Teensy 4.1) Serial", "protocol": "teensy",
                  "properties": {"vid": "0x16C0", "serialNumber": "155"}},
         "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]},
        {"port": {"address": "COM3", "label": "COM3", "protocol": "serial", "properties": {}}}]}
    ports = tt.parse_board_list(json.dumps(serial))
    assert len(ports) == 2 and ports[0]["teensy"] and not ports[1]["teensy"]
    t = ports[0]
    assert (t["port"], t["monitor_address"], t["monitor_protocol"]) == ("COM5", "COM5", "serial")
    assert (t["upload_address"], t["upload_protocol"]) == ("usb:0/140000/0/7", "teensy")
    boot = [{"port": {"address": "usb:0/1/0/7", "label": "hid#vid_16c0&pid_0478 Bootloader", "protocol": "teensy",
                      "properties": {"vid": "0x16C0"}}, "matching_boards": []}]  # 0.x list format
    b = tt.parse_board_list(json.dumps(boot))[0]
    assert b["teensy"] and b["mode"] == "Bootloader" and "no COM port" in b["label"]
    assert tt.parse_board_list('{"detected_ports": []}') == []


def test_last_flash_reads_log(tmp_path):
    cfg = {"paths": {"log_dir": str(tmp_path)}}
    with open(tmp_path / "flash_log.csv", "w") as fp:
        fp.write("time,branch,commit,port,dry_run,result,build_dir\n")
        fp.write("2026-11-19 12:00:00,main,06a2177,COM5,False,ok,x\n")
        fp.write("2026-11-19 12:05:00,imu,6f5fa6c,COM5,True,dry-run,x,fq\n")
    assert tt.last_flash(cfg)["commit"] == "06a2177"
