#!/usr/bin/env python3
"""
Last Z farm helper.

Drives BlueStacks instances over ADB, finds buttons by matching small
screenshot "templates" you capture yourself, and sends gather marches on a
randomized schedule. Nothing is injected into the game; it only reads the
screen and sends taps.

Commands:
  python3 farm_bot.py devices                  list ADB devices
  python3 farm_bot.py snap  -d 127.0.0.1:5555  save a full screenshot (to crop templates from)
  python3 farm_bot.py test  -d 127.0.0.1:5555 -t gather_button   check one template's match score
  python3 farm_bot.py once  -d 127.0.0.1:5555  run one gather cycle on one device, then stop
  python3 farm_bot.py run                      run forever on every device in config.yaml
"""

import argparse
import datetime as dt
import logging
import random
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("farm")


# --------------------------------------------------------------------------- #
# ADB device
# --------------------------------------------------------------------------- #
class Device:
    def __init__(self, serial: str, adb: str = "adb"):
        self.serial = serial
        self.adb = adb

    def _run(self, *args, timeout=20) -> bytes:
        cmd = [self.adb, "-s", self.serial, *map(str, args)]
        res = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if res.returncode != 0:
            raise RuntimeError(f"adb failed: {' '.join(cmd)}\n{res.stderr.decode(errors='ignore')}")
        return res.stdout

    def connect(self):
        if ":" in self.serial:  # network-style serial like 127.0.0.1:5555
            subprocess.run([self.adb, "connect", self.serial], capture_output=True, timeout=15)

    def screenshot(self) -> np.ndarray:
        data = self._run("exec-out", "screencap", "-p")
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Could not decode screenshot (is the instance running?)")
        return img

    def tap(self, x: int, y: int):
        # A zero-distance swipe with a random hold time looks more like a finger than `input tap`.
        hold = random.randint(45, 130)
        self._run("shell", "input", "swipe", x, y, x, y, hold)

    def back(self):
        self._run("shell", "input", "keyevent", 4)

    def swipe(self, x1, y1, x2, y2):
        dur = random.randint(350, 600)
        self._run("shell", "input", "swipe", x1, y1, x2, y2, dur)


# --------------------------------------------------------------------------- #
# Template matching
# --------------------------------------------------------------------------- #
class Templates:
    def __init__(self, folder: Path):
        self.folder = folder
        self._cache = {}

    def get(self, name: str) -> np.ndarray:
        if name not in self._cache:
            path = self.folder / f"{name}.png"
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise FileNotFoundError(f"Missing template: {path}")
            self._cache[name] = img
        return self._cache[name]

    def match(self, screen: np.ndarray, name: str):
        """Return (score, x, y, w, h) of the best match; x,y is top-left."""
        tpl = self.get(name)
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if screen.ndim == 3 else screen
        if gray.shape[0] < tpl.shape[0] or gray.shape[1] < tpl.shape[1]:
            raise ValueError(f"Template '{name}' is larger than the screen. Check resolution.")
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        h, w = tpl.shape
        return score, loc[0], loc[1], w, h


def jitter_point(x, y, w, h, spread=0.3):
    """Random point near the center of a box, so taps never land on the exact same pixel."""
    cx, cy = x + w / 2, y + h / 2
    jx = random.uniform(-w * spread / 2, w * spread / 2)
    jy = random.uniform(-h * spread / 2, h * spread / 2)
    return int(cx + jx), int(cy + jy)


def human_sleep(rng):
    lo, hi = rng if isinstance(rng, (list, tuple)) else (rng, rng)
    time.sleep(random.uniform(lo, hi))


# --------------------------------------------------------------------------- #
# Bot logic
# --------------------------------------------------------------------------- #
class FarmBot:
    def __init__(self, cfg: dict, device_cfg: dict):
        self.cfg = cfg
        self.name = device_cfg.get("name", device_cfg["serial"])
        self.dev = Device(device_cfg["serial"], cfg.get("adb_path", "adb"))
        self.tpl = Templates(ROOT / cfg.get("templates_dir", "templates"))
        self.threshold = cfg.get("match_threshold", 0.85)
        self.thresholds = cfg.get("thresholds", {}) or {}
        self.resources = device_cfg.get("resources") or cfg.get("resources", [])
        self.max_marches = device_cfg.get("max_marches", cfg.get("max_marches", 4))
        self.debug_dir = ROOT / "debug"
        self.rr = 0  # round-robin position in the resource list, kept between cycles

    # -- helpers ----------------------------------------------------------- #
    def wait_for(self, name, timeout, poll=(0.6, 1.1)):
        """Poll the screen until a template appears. Returns (screen, box) or (screen, None)."""
        end = time.time() + timeout
        screen = None
        while True:
            screen = self.dev.screenshot()
            score, x, y, w, h = self.tpl.match(screen, name)
            if score >= self.thresholds.get(name, self.threshold):
                log.debug("[%s] found %s (%.2f)", self.name, name, score)
                return screen, (x, y, w, h)
            if time.time() >= end:
                log.debug("[%s] did not find %s (best %.2f)", self.name, name, score)
                return screen, None
            human_sleep(poll)

    def save_debug(self, screen, label):
        self.debug_dir.mkdir(exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.debug_dir / f"{self.name}-{stamp}-{label}.png".replace(":", "_")
        cv2.imwrite(str(path), screen)
        log.info("[%s] saved debug screenshot %s", self.name, path.name)

    def reset(self):
        """Back out to a known screen. Uses the 'home_check' template if you made one."""
        home = self.cfg.get("home_template")
        cancel = self.cfg.get("exit_cancel_template")
        for _ in range(self.cfg.get("reset_back_presses", 4)):
            if home:
                _, box = self.wait_for(home, timeout=0)
                if box:
                    return
            self.dev.back()
            human_sleep((0.8, 1.4))
            if cancel:  # pressing back on the main screen may open "Exit game?"
                _, box = self.wait_for(cancel, timeout=0)
                if box:
                    self.dev.tap(*jitter_point(*box))
                    human_sleep((0.6, 1.0))
                    return

    # -- one step from config ---------------------------------------------- #
    def do_step(self, step: dict, resource: str) -> str:
        """Returns 'ok', 'skipped', or 'fail'."""
        wait_after = step.get("wait", self.cfg.get("default_wait", [0.8, 1.6]))
        timeout = step.get("timeout", self.cfg.get("default_timeout", 6))

        if "find" in step:
            name = step["find"].replace("{resource}", resource)
            screen, box = self.wait_for(name, timeout)
            # Scrollable lists (e.g. the resource carousel): swipe one way, then the other.
            scroll = step.get("scroll_if_missing")
            if not box and scroll:
                h, w = screen.shape[:2]
                x1, y1, x2, y2 = scroll["swipe"]
                tries = scroll.get("tries", 3)
                for fwd in (True, False):
                    for _ in range(tries if fwd else tries * 2):
                        a, b = ((x1, y1), (x2, y2)) if fwd else ((x2, y2), (x1, y1))
                        self.dev.swipe(int(a[0] * w), int(a[1] * h), int(b[0] * w), int(b[1] * h))
                        human_sleep((0.8, 1.3))
                        screen, box = self.wait_for(name, timeout=0)
                        if box:
                            break
                    if box:
                        break
            if not box:
                if step.get("optional"):
                    return "skipped"
                self.save_debug(screen, f"missing-{name}")
                return "fail"
            self.dev.tap(*jitter_point(*box))

        elif "ensure" in step:
            # Make sure a state is showing (e.g. "Lv.6"); if not, run the fix taps and re-check.
            target = step["ensure"].replace("{resource}", resource)
            screen, box = self.wait_for(target, timeout=1.5)
            if not box:
                for fix in step.get("fix", []):
                    screen, btn = self.wait_for(fix["press"], timeout=3)
                    if not btn:
                        self.save_debug(screen, f"missing-{fix['press']}")
                        return "fail"
                    for _ in range(fix.get("times", 1)):
                        self.dev.tap(*jitter_point(*btn))
                        human_sleep((0.25, 0.55))
                screen, box = self.wait_for(target, timeout=2)
                if not box:
                    self.save_debug(screen, f"not-{target}")
                    return "fail"
                log.debug("[%s] fixed -> %s", self.name, target)

        elif "tap_frac" in step:  # tap a spot given as a fraction of the screen, e.g. [0.5, 0.5]
            screen = self.dev.screenshot()
            h, w = screen.shape[:2]
            fx, fy = step["tap_frac"]
            x = int(w * fx + random.uniform(-w * 0.015, w * 0.015))
            y = int(h * fy + random.uniform(-h * 0.015, h * 0.015))
            self.dev.tap(x, y)

        elif step.get("back"):
            self.dev.back()

        elif "sleep" in step:
            human_sleep(step["sleep"])
            return "ok"

        human_sleep(wait_after)
        return "ok"

    # -- one march ---------------------------------------------------------- #
    def send_march(self, resource: str) -> bool:
        free_tpl = self.cfg.get("free_march_template")
        if free_tpl:
            _, box = self.wait_for(free_tpl, timeout=2)
            if not box:
                log.info("[%s] no idle squads", self.name)
                return False
        stop_tpl = self.cfg.get("no_march_template")
        for step in self.cfg["gather_sequence"]:
            if stop_tpl:
                _, box = self.wait_for(stop_tpl, timeout=0)
                if box:
                    log.info("[%s] no free march slots", self.name)
                    return False
            result = self.do_step(step, resource)
            if result == "fail":
                log.warning("[%s] step failed: %s", self.name, step)
                return False
        log.info("[%s] march sent -> %s", self.name, resource)
        return True

    # -- one full cycle ----------------------------------------------------- #
    def cycle(self) -> int:
        self.dev.connect()
        sent = 0
        order = self.resources[:]
        shuffle = self.cfg.get("shuffle_resources", True)
        if shuffle:
            random.shuffle(order)
        for i in range(self.max_marches):
            if not order:
                resource = ""
            elif shuffle:
                resource = order[i % len(order)]
            else:  # strict rotation: wood, food, wood, food ... continuing across cycles
                resource = order[self.rr % len(order)]
            if not self.send_march(resource):
                break
            self.rr += 1
            sent += 1
            human_sleep(self.cfg.get("between_marches", [2, 6]))
        self.reset()
        return sent


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #
def in_active_hours(cfg) -> bool:
    hours = cfg.get("active_hours")
    if not hours:
        return True
    start, end = hours
    now = dt.datetime.now().hour
    return start <= now < end if start < end else (now >= start or now < end)


def run_forever(cfg):
    bots = [FarmBot(cfg, d) for d in cfg["devices"]]
    next_run = {b.name: 0.0 for b in bots}
    log.info("Running on %d device(s). Ctrl+C to stop.", len(bots))
    while True:
        if not in_active_hours(cfg):
            time.sleep(300)
            continue
        for bot in bots:
            if time.time() < next_run[bot.name]:
                continue
            try:
                n = bot.cycle()
                log.info("[%s] cycle done, %d march(es) sent", bot.name, n)
            except Exception as e:  # keep the loop alive if one instance hiccups
                log.error("[%s] error: %s", bot.name, e)
            lo, hi = cfg.get("cycle_minutes", [25, 45])
            mins = random.uniform(lo, hi)
            next_run[bot.name] = time.time() + mins * 60
            log.info("[%s] next check in %.0f min", bot.name, mins)
        time.sleep(random.uniform(20, 40))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def load_cfg():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def device_cfg_for(cfg, serial):
    for d in cfg.get("devices", []):
        if d["serial"] == serial:
            return d
    return {"serial": serial}


def main():
    p = argparse.ArgumentParser(description="Last Z farm helper")
    p.add_argument("command", choices=["devices", "snap", "test", "once", "run"])
    p.add_argument("-d", "--device", help="ADB serial, e.g. 127.0.0.1:5555")
    p.add_argument("-t", "--template", help="template name (without .png) for 'test'")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_cfg()
    adb = cfg.get("adb_path", "adb")

    if a.command == "devices":
        print(subprocess.run([adb, "devices"], capture_output=True, text=True).stdout)
        return

    if a.command == "run":
        run_forever(cfg)
        return

    if not a.device:
        sys.exit("Use -d <serial> for this command.")
    dev = Device(a.device, adb)
    dev.connect()

    if a.command == "snap":
        out = ROOT / f"snap-{dt.datetime.now():%H%M%S}.png"
        img = dev.screenshot()
        cv2.imwrite(str(out), img)
        print(f"Saved {out.name}  ({img.shape[1]}x{img.shape[0]})")

    elif a.command == "test":
        if not a.template:
            sys.exit("Use -t <template_name>.")
        tpl = Templates(ROOT / cfg.get("templates_dir", "templates"))
        score, x, y, w, h = tpl.match(dev.screenshot(), a.template)
        need = (cfg.get("thresholds") or {}).get(a.template, cfg.get("match_threshold", 0.85))
        verdict = "MATCH" if score >= need else "no match"
        print(f"{a.template}: score {score:.3f} at ({x},{y}) size {w}x{h} -> {verdict}")

    elif a.command == "once":
        bot = FarmBot(cfg, device_cfg_for(cfg, a.device))
        print(f"Sent {bot.cycle()} march(es).")


if __name__ == "__main__":
    main()
