"""Automated verification of the M0 widget spike success criteria.

Starts spike/deck_widget_spike.py in a subprocess, drives it with Playwright
chromium using real mouse events at pixel coordinates computed from
web-mercator math, and checks every M0 criterion. Prints PASS/FAIL per check.

Run:  .venv/bin/python spike/verify_spike.py [--blank]
"""

import json
import math
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 5391
REPO = Path(__file__).resolve().parents[1]

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def world_px(lon, lat, zoom):
    world = 512 * 2**zoom
    x = (lon / 360 + 0.5) * world
    merc_y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    y = (0.5 - merc_y / (2 * math.pi)) * world
    return x, y


def screen_px(box, lon, lat, center=(0.0, 0.0), zoom=2):
    wx, wy = world_px(lon, lat, zoom)
    cx, cy = world_px(center[0], center[1], zoom)
    return (
        box["x"] + box["width"] / 2 + (wx - cx),
        box["y"] + box["height"] / 2 + (wy - cy),
    )


def read_probe(page):
    txt = page.locator(".spike-probe").inner_text()
    return json.loads(txt)


def wait_probe(page, pred, timeout=10.0, poll=0.1):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = read_probe(page)
            if pred(last):
                return last
        except Exception:  # noqa: BLE001 - probe may be mid-render
            pass
        time.sleep(poll)
    return last if last and pred(last) else None


def main():
    blank = "--blank" in sys.argv
    cmd = [
        str(REPO / ".venv/bin/python"),
        str(REPO / "spike/deck_widget_spike.py"),
        "--server",
        "--port",
        str(PORT),
    ]
    if blank:
        cmd.append("--blank")
    server = subprocess.Popen(
        cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    try:
        # wait for server to come up
        t0 = time.time()
        while time.time() - t0 < 30:
            line = server.stdout.readline()
            if "App running" in line or "Starting factory" in line:
                break
        time.sleep(1.0)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 900})
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="networkidle")

            probe = wait_probe(page, lambda pr: pr.get("ready"), timeout=15)
            check("ready event", probe is not None)
            if probe is None:
                msg = "widget never became ready"
                raise RuntimeError(msg)

            box_l = page.locator(".celeri-deck")
            box_l.wait_for(state="visible")
            box = box_l.bounding_box()
            check("container box", box is not None, str(box))

            # --- empty click gives lon/lat -------------------------------
            ex, ey = screen_px(box, -10.0, 8.0)
            page.mouse.click(ex, ey)
            probe = wait_probe(page, lambda pr: pr.get("last_click"))
            ok = False
            detail = "no click event"
            if probe:
                c = probe["last_click"]
                coord = c.get("coordinate") or [999, 999]
                ok = (
                    not c.get("picked")
                    and abs(coord[0] - (-10.0)) < 0.5
                    and abs(coord[1] - 8.0) < 0.5
                )
                detail = f"picked={c.get('picked')} coord={coord}"
            check("empty click coordinate", ok, detail)

            # --- click picks a point -------------------------------------
            px, py = screen_px(box, 20.0, 10.0)
            page.mouse.click(px, py)
            probe = wait_probe(
                page, lambda pr: (pr.get("last_click") or {}).get("picked")
            )
            ok = False
            detail = "no picked click"
            if probe:
                c = probe["last_click"]
                ok = c.get("layerId") == "points" and c.get("index") == 1
                detail = f"layerId={c.get('layerId')} index={c.get('index')}"
            check("click picks point (layerId,index)", ok, detail)

            # --- hover rate ----------------------------------------------
            n0 = (read_probe(page) or {}).get("n_hover", 0)
            t0 = time.time()
            steps = 50
            for i in range(steps):
                page.mouse.move(
                    box["x"] + 100 + i * 8, box["y"] + 300 + (i % 7) * 4
                )
                page.wait_for_timeout(20)  # ~1 s of continuous movement
            elapsed = time.time() - t0
            probe = read_probe(page) or {}
            n_hover = probe.get("n_hover", 0) - n0
            rate = n_hover / elapsed if elapsed else 99
            check(
                "hover throttled <= ~12 Hz and > 0",
                0 < rate <= 14,
                f"{n_hover} events in {elapsed:.2f}s = {rate:.1f} Hz",
            )

            # --- drag point 1 --------------------------------------------
            vs_before = (read_probe(page) or {}).get("view_state")
            sx, sy = screen_px(box, 20.0, 10.0)
            tx, ty = sx + 60, sy - 40
            page.mouse.move(sx, sy)
            page.wait_for_timeout(300)  # allow hover-arm
            page.mouse.down()
            for i in range(1, 11):
                page.mouse.move(sx + (tx - sx) * i / 10, sy + (ty - sy) * i / 10)
                page.wait_for_timeout(30)
            page.mouse.up()
            probe = wait_probe(page, lambda pr: pr.get("last_dragend"))
            ok = False
            detail = "no dragend"
            if probe:
                de = probe["last_dragend"]
                pts = probe.get("points") or []
                moved = pts[1] if len(pts) > 1 else {}
                ok = (
                    de.get("layerId") == "points"
                    and de.get("index") == 1
                    and moved.get("lon", 0) > 20.5
                    and moved.get("lat", 0) > 10.5
                    and probe.get("n_drag", 0) > 0
                )
                detail = (
                    f"dragend={de.get('coordinate')} committed="
                    f"({moved.get('lon'):.3f},{moved.get('lat'):.3f}) "
                    f"n_drag={probe.get('n_drag')}"
                )
            check("drag: arm, ghost, dragend commit", ok, detail)

            # camera must not have moved during the drag
            page.wait_for_timeout(400)
            vs_after = (read_probe(page) or {}).get("view_state")
            check(
                "camera unchanged by drag (pan disarmed)",
                vs_after == vs_before,
                f"before={vs_before} after={vs_after}",
            )

            # --- Enter / Escape keys --------------------------------------
            page.keyboard.press("Escape")
            probe = wait_probe(
                page, lambda pr: (pr.get("last_key") or {}).get("key") == "Escape"
            )
            check("Escape key event", probe is not None)
            page.keyboard.press("Enter")
            probe = wait_probe(
                page, lambda pr: (pr.get("last_key") or {}).get("key") == "Enter"
            )
            check("Enter key event", probe is not None)

            # --- big push: scale + camera survival ------------------------
            t0 = time.time()
            page.locator(".btn-big").click()
            probe = wait_probe(page, lambda pr: pr.get("big_loaded"), timeout=20)
            dt = time.time() - t0
            check("big push (2000 lines + 1500 pts)", probe is not None, f"{dt:.2f}s")

            # camera still centered: empty click maps to expected lon/lat
            page.wait_for_timeout(500)
            ex, ey = screen_px(box, -15.0, -12.0)
            page.mouse.click(ex, ey)
            probe = wait_probe(
                page,
                lambda pr: (pr.get("last_click") or {}).get("coordinate")
                and abs(pr["last_click"]["coordinate"][0] - (-15.0)) < 1.0,
            )
            ok = probe is not None and abs(
                probe["last_click"]["coordinate"][1] - (-12.0)
            ) < 1.0
            check("camera survived layer push", ok)

            # --- fly-to via view_state_revision ---------------------------
            page.locator(".btn-fly").click()
            page.wait_for_timeout(800)
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.click(cx, cy)
            probe = wait_probe(
                page,
                lambda pr: (pr.get("last_click") or {}).get("coordinate")
                and abs(pr["last_click"]["coordinate"][0] - 140.0) < 1.0
                and abs(pr["last_click"]["coordinate"][1] - 37.5) < 1.0,
            )
            check("fly-to applied on revision bump", probe is not None)

            page.screenshot(path=str(REPO / "spike/spike_final.png"))
            browser.close()
    finally:
        server.terminate()
        try:
            out = server.stdout.read()
            tail = "\n".join(out.strip().splitlines()[-15:])
            print("--- server tail ---\n" + tail, flush=True)
        except Exception:  # noqa: BLE001
            pass

    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{'=' * 50}\n{len(results) - n_fail}/{len(results)} checks passed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
