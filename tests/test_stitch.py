"""Stitcher tests: scroll a synthetic tall page past the Stitcher with
bottom-edge artifacts (window corners, link bubble) and check the result.

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


def scroll_through(page, lo, hi, seed, header=0):
    rnd = random.Random(seed)
    st = sc.Stitcher()
    pos = 0
    while True:
        frame = page[pos:pos + HVIEW].copy()
        if header:
            frame[:header] = (200, 220, 255)              # sticky bar
        frame[-40:, :30] = 0
        frame[-40:, -30:] = 0                             # window corners
        frame[-50:, 200:900] = (60, 60, 60)               # link status bubble
        st.add(frame)
        if pos + HVIEW >= PH:
            break
        pos = min(pos + rnd.randint(lo, hi), PH - HVIEW)
    return np.asarray(st.result())


def check(name, out, page, header=0):
    ok = out.shape[0] == PH and np.array_equal(out[header:-60], page[header:-60])
    print(f"{'PASS' if ok else 'FAIL'}  {name}  rows={out.shape[0]}")
    return ok


if __name__ == "__main__":
    page = make_page()
    results = [
        check("steps 60-300", scroll_through(page, 60, 300, 1), page),
        check("steps 4-40 (slow)", scroll_through(page, 4, 40, 2), page),
        check("steps 300-800 (fast)", scroll_through(page, 300, 800, 3), page),
        check("sticky header", scroll_through(page, 60, 300, 4, header=140), page, header=140),
    ]
    sys.exit(0 if all(results) else 1)
