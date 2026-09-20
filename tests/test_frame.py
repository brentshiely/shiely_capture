"""Tests for the remembered region frame: hit testing, drag math, persistence.

Run:  ./venv/bin/python tests/test_frame.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shiely_capture as sc  # noqa: E402

FR = (100, 100, 400, 300)        # x, y, w, h  (bottom-left origin)
fails = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  got={got} want={want}"))
    if not ok:
        fails.append(name)


# hit testing
check("inside is move", sc.hit_test(FR, (300, 250)), "move")
check("outside is None", sc.hit_test(FR, (700, 700)), None)
check("left edge", sc.hit_test(FR, (100, 250)), "w")
check("right edge", sc.hit_test(FR, (500, 250)), "e")
check("top edge", sc.hit_test(FR, (300, 400)), "n")
check("bottom edge", sc.hit_test(FR, (300, 100)), "s")
check("top-right corner", sc.hit_test(FR, (500, 400)), "ne")
check("bottom-left corner", sc.hit_test(FR, (100, 100)), "sw")
check("just outside tolerance", sc.hit_test(FR, (300, 415)), None)

# drag math
check("move", sc.apply_drag("move", FR, (300, 250), (320, 230)), (120, 80, 400, 300))
check("drag right edge out", sc.apply_drag("e", FR, (500, 250), (560, 250)), (100, 100, 460, 300))
check("drag left edge in", sc.apply_drag("w", FR, (100, 250), (150, 250)), (150, 100, 350, 300))
check("drag top edge up", sc.apply_drag("n", FR, (300, 400), (300, 450)), (100, 100, 400, 350))
check("drag bottom-right corner", sc.apply_drag("se", FR, (500, 100), (450, 60)), (100, 60, 350, 340))
check("edge dragged past opposite flips", sc.apply_drag("e", FR, (500, 250), (60, 250)), (60, 100, 40, 300))
check("draw new frame", sc.apply_drag("new", (0, 0, 0, 0), (50, 60), (250, 20)), (50, 20, 200, 40))
check("draw new frame backwards", sc.apply_drag("new", (0, 0, 0, 0), (250, 20), (50, 60)), (50, 20, 200, 40))

# persistence
screens = [(0, 0, 1470, 956)]                       # one 1470x956 display, cocoa coords
ph = 956
check("on screen", sc.rect_on_screens((100, 100, 400, 300), screens, ph), True)
check("off screen (unplugged display)", sc.rect_on_screens((3000, 100, 400, 300), screens, ph), False)
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "sub", "last_region.json")
    check("missing file", sc.load_region(path, screens, ph), None)
    sc.save_region((100, 120, 640, 480), path)
    check("round trip", sc.load_region(path, screens, ph), (100, 120, 640, 480))
    sc.save_region((5000, 120, 640, 480), path)
    check("saved off-screen region is ignored", sc.load_region(path, screens, ph), None)
    with open(path, "w") as fh:
        fh.write("not json")
    check("corrupt file", sc.load_region(path, screens, ph), None)
    with open(path, "w") as fh:
        json.dump([10, 10, 5, 5], fh)
    check("tiny region is ignored", sc.load_region(path, screens, ph), None)

sys.exit(1 if fails else 0)
