"""Turn frames/ from record_demo.py into demo.gif (needs Pillow)."""

import sys
from pathlib import Path
from PIL import Image, ImageChops

WIDTH = int(sys.argv[1]) if len(sys.argv) > 1 else 960
files = sorted(Path("frames").glob("*.png"))
times = [int(f.stem.split("_")[1]) for f in files]
imgs = []
for f in files:
    im = Image.open(f).convert("RGB")
    imgs.append(im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.LANCZOS))

# One palette for every frame: per-frame palettes make unchanged pixels change index,
# which defeats GIF's frame-difference compression.
sample = Image.new("RGB", (WIDTH, imgs[0].height * 6))
for i, k in enumerate(range(0, len(imgs), max(1, len(imgs) // 6))[:6]):
    sample.paste(imgs[k], (0, i * imgs[0].height))
pal = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)

frames, durs = [], []
for i, im in enumerate(imgs):
    d = (times[i + 1] - times[i]) if i + 1 < len(imgs) else 3000
    q = im.quantize(palette=pal, dither=Image.Dither.NONE)
    if frames and ImageChops.difference(q.convert("RGB"), frames[-1].convert("RGB")).getbbox() is None:
        durs[-1] += d
    else:
        frames.append(q); durs.append(max(d, 40))
frames[0].save("demo.gif", save_all=True, append_images=frames[1:], duration=durs, loop=0, optimize=True, disposal=1)
print(len(frames), "unique frames,", round(sum(durs) / 1000, 1), "s,", round(Path("demo.gif").stat().st_size / 1e6, 2), "MB")
