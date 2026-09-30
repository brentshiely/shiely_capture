import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from PIL import Image
import shiely_capture as sc

rng = np.random.default_rng(1)
page = Image.fromarray(rng.integers(0, 255, (40000, 1500, 3), dtype=np.uint8))

tiles = sc.tile_image(page, 2500, 175, 1470)
assert len(tiles) == 17, len(tiles)
assert all(t.width == 1470 for t in tiles)
assert max(t.height for t in tiles) == 2500
assert tiles[-1].height > 175          # last tile is more than pure overlap

small = Image.new("RGB", (800, 2000))
assert sc.tile_image(small, 2500, 175, 1470) == []

# overlap: tile k+1 starts 175 px above where tile k ends
a = np.asarray(sc.tile_image(Image.fromarray(np.asarray(page)[:6000, :1470]), 2500, 175, 1470)[0])
b = np.asarray(sc.tile_image(Image.fromarray(np.asarray(page)[:6000, :1470]), 2500, 175, 1470)[1])
assert (a[-175:] == b[:175]).all()

with tempfile.TemporaryDirectory() as d:
    folder = sc.save_tiles(page, stamp="t", out_root=d)
    files = sorted(os.listdir(folder))
    assert len(files) == 17 and files[0] == "01-of-17.jpg", files[:2]
    assert sc.save_tiles(small, out_root=d) is None
print("ok")
