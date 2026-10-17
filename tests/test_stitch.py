"""Stitcher tests: scroll a synthetic tall page past the Stitcher with
bottom-edge artifacts (window corners, link bubble), a sticky header, and fixed overlays
(a partial-width composer and a floating button), and check the result.
Steps stay under about half the viewport in the overlay cases: a row that only ever
appears under an overlay cannot be recovered by any stitcher.

Run:  ./venv/bin/python tests/test_stitch.py
"""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shiely_capture as sc  # noqa: E402

W, PH, HVIEW = 1600, 9000, 1200


def make_page(seed=3):
    rnd = random.Random(seed)
    page = Image.new("RGB", (W, PH), (250, 250, 250))
    d = ImageDraw.Draw(page)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 30)
    except Exception:
        font = ImageFont.load_default()
    words = "the quick brown fox jumps over lazy dog yacht rock scroll capture stitch".split()
    y = 20
    while y < PH - 60:
        if rnd.random() < 0.12:
            y += rnd.randint(80, 260)
            continue
        d.text((rnd.choice([40, 40, 90]), y), " ".join(rnd.choices(words, k=rnd.randint(4, 14))),
               fill=(20, 20, 30), font=font)
        if rnd.random() < 0.08:
            d.rectangle([60, y + 40, 60 + rnd.randint(200, 1200), y + 120],
                        fill=tuple(rnd.randint(0, 255) for _ in range(3)))
            y += 140
        y += 46
    return np.asarray(page)


def scroll_through(page, lo, hi, seed, header=0, overlays=False):
    rnd = random.Random(seed)
    st = sc.Stitcher()
    pos = last_ok = 0
    while True:
        frame = page[pos:pos + HVIEW].copy()
        if header:
            frame[:header] = (200, 220, 255)              # sticky bar
        if overlays:
            frame[HVIEW - 190:HVIEW - 60, 300:1300] = (255, 255, 255)   # fixed composer
            frame[HVIEW - 190:HVIEW - 186, 300:1300] = (90, 90, 200)
            frame[HVIEW - 150:HVIEW - 130, 340:700] = (120, 120, 120)   # its placeholder text
            yy, xx = np.ogrid[:HVIEW, :W]
            frame[(yy - 700) ** 2 + (xx - 1230) ** 2 < 24 ** 2] = (30, 30, 30)  # floating arrow
        frame[-40:, :30] = 0
        frame[-40:, -30:] = 0                             # window corners
        frame[-50:, 200:900] = (60, 60, 60)               # link status bubble
        r = st.add(frame)
        if r.startswith(("shift", "first")):
            last_ok = pos
        if pos + HVIEW >= PH and r != "no-match":
            break
        if r == "no-match":                               # a real user scrolls back when tracking is lost
            pos = last_ok + (pos - last_ok) // 2
        else:
            pos = min(pos + rnd.randint(lo, hi), PH - HVIEW)
    return np.asarray(st.result())


def check(name, out, page, header=0, tail=60, allow=0.0):
    """allow: fraction of rows that may differ (rows only ever seen under an overlay)."""
    if out.shape[0] != PH:
        print(f"FAIL  {name}  rows={out.shape[0]}")
        return False
    diff = np.abs(out[header:-tail].astype(np.int16) - page[header:-tail]).max(axis=(1, 2))
    bad = (diff > (8 if allow else 0)).mean()   # allow: ignore invisible 5-level mismatches too
    ok = bad <= allow
    print(f"{'PASS' if ok else 'FAIL'}  {name}  rows={out.shape[0]}  differing={bad:.2%}")
    return ok


if __name__ == "__main__":
    page = make_page()
    results = [
        check("steps 60-300", scroll_through(page, 60, 300, 1), page),
        check("steps 4-40 (slow)", scroll_through(page, 4, 40, 2), page),
        check("steps 300-800 (fast)", scroll_through(page, 300, 800, 3), page),
        check("sticky header", scroll_through(page, 60, 300, 4, header=140), page, header=140),
        check("fixed composer + floating button", scroll_through(page, 60, 300, 5, overlays=True), page, tail=250),
        check("overlays + header, steps 150-500", scroll_through(page, 150, 500, 6, header=140, overlays=True), page, header=140, tail=250, allow=0.01),
        check("overlays + header, seed 7", scroll_through(page, 150, 500, 7, header=140, overlays=True), page, header=140, tail=250, allow=0.01),
        check("overlays + header, seed 5", scroll_through(page, 150, 500, 5, header=140, overlays=True), page, header=140, tail=250, allow=0.01),
    ]
    sys.exit(0 if all(results) else 1)
