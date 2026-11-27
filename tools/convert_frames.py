"""
Converts landing page scroll animation frames (JPG) to lighter WebP.

  core/static/img/story/frames_<name>/frame_XXXX.jpg
  -> core/static/img/story/frames_<name>_webp/frame_XXXX.webp

- keeps every STEP-th frame and renumbers them 0, 1, 2...
- scales down to MAX_WIDTH (aspect ratio preserved, never upscales)
- prints the new frame count for each folder (-> data-frames in base_landing.html)

Usage:  python tools/convert_frames.py [--step 2] [--width 1280] [--quality 72]
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

STORY_DIR = Path(__file__).resolve().parent.parent / "core" / "static" / "img" / "story"


def convert_one(args):
    src, dst, max_width, quality = args
    with Image.open(src) as img:
        img = img.convert("RGB")
        if img.width > max_width:
            new_height = round(img.height * max_width / img.width)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        img.save(dst, "WEBP", quality=quality, method=6)
    return dst.stat().st_size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--quality", type=int, default=72)
    opts = parser.parse_args()

    jobs, summary = [], []
    for folder in sorted(STORY_DIR.glob("frames_*")):
        if not folder.is_dir() or folder.name.endswith("_webp"):
            continue
        frames = sorted(folder.glob("frame_*.jpg"))[:: opts.step]
        out_dir = STORY_DIR / f"{folder.name}_webp"
        out_dir.mkdir(exist_ok=True)
        for old in out_dir.glob("frame_*.webp"):
            old.unlink()
        for idx, src in enumerate(frames):
            jobs.append((src, out_dir / f"frame_{idx:04d}.webp", opts.width, opts.quality))
        summary.append((out_dir.name, len(frames)))

    with ProcessPoolExecutor() as pool:
        total = sum(pool.map(convert_one, jobs, chunksize=8))

    for name, count in summary:
        print(f'{name}: data-frames="{count}"')
    print(f"Total: {len(jobs)} frames, {total / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
