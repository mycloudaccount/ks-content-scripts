import os
import math
from PIL import Image

# ============================================================
# CONFIG
# ============================================================

MAX_SHEET_WIDTH = 4096
FRAME_DELAY_MS = 166
PREVIEW_BG = "#2b2b2b"
PIXELATED = True

# ============================================================
# LOGGING
# ============================================================


def log(msg):
    print(msg)

# ============================================================
# HTML TEMPLATE (ESCAPED FOR PYTHON .format)
# ============================================================


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>{name}</title>
<style>
body {{
  background: {bg};
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
}}
#sprite {{
  width: {w}px;
  height: {h}px;
  background-image: url("sheet.png");
  background-repeat: no-repeat;
  image-rendering: {rendering};
}}
</style>
</head>
<body>
<div id="sprite"></div>
<script>
const frameW = {w};
const frameH = {h};
const frames = {frames};
const cols = {cols};

let index = 0;

setInterval(() => {{
  const col = index % cols;
  const row = Math.floor(index / cols);

  const x = -(col * frameW);
  const y = -(row * frameH);

  document.getElementById("sprite").style.backgroundPosition =
    `${{x}}px ${{y}}px`;

  index = (index + 1) % frames;
}}, {delay});
</script>
</body>
</html>
"""

# ============================================================
# CLEAN OUTPUT FILES
# ============================================================


def clean_previous_outputs(anim_dir):
    for fname in ("sheet.png", "sheet.json", "preview.html"):
        path = os.path.join(anim_dir, fname)
        if os.path.exists(path):
            os.remove(path)
            log(f"  🧹 Removed {fname}")

# ============================================================
# SPRITESHEET BUILDER
# ============================================================


def build_spritesheet(anim_dir):
    pngs = sorted(
        f for f in os.listdir(anim_dir)
        if f.lower().endswith(".png")
    )

    if not pngs:
        log("  ⚠ No PNG frames found, skipping")
        return None

    images = [
        Image.open(os.path.join(anim_dir, f)).convert("RGBA")
        for f in pngs
    ]

    max_w = max(img.width for img in images)
    max_h = max(img.height for img in images)

    frame_count = len(images)

    cols = max(1, min(frame_count, MAX_SHEET_WIDTH // max_w))
    rows = math.ceil(frame_count / cols)

    sheet_w = cols * max_w
    sheet_h = rows * max_h

    log(f"  📐 Sheet layout: {cols}x{rows} → {sheet_w}x{sheet_h}")

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

    x = y = 0
    col = 0

    for img in images:
        ox = (max_w - img.width) // 2
        oy = (max_h - img.height) // 2

        sheet.paste(img, (x + ox, y + oy), img)

        col += 1
        x += max_w

        if col >= cols:
            col = 0
            x = 0
            y += max_h

    sheet.save(os.path.join(anim_dir, "sheet.png"))

    return max_w, max_h, frame_count, cols

# ============================================================
# PREVIEW BUILDER
# ============================================================


def build_preview(anim_dir, w, h, frames, cols):
    html = HTML_TEMPLATE.format(
        name=os.path.basename(anim_dir),
        bg=PREVIEW_BG,
        w=w,
        h=h,
        frames=frames,
        cols=cols,
        delay=FRAME_DELAY_MS,
        rendering="pixelated" if PIXELATED else "auto",
    )

    with open(
        os.path.join(anim_dir, "preview.html"),
        "w",
        encoding="utf-8"
    ) as f:
        f.write(html)

# ============================================================
# MAIN
# ============================================================


def main(root_dir):
    log(f"▶ Processing sprite root: {root_dir}")

    for name in sorted(os.listdir(root_dir)):
        anim_dir = os.path.join(root_dir, name)
        if not os.path.isdir(anim_dir):
            continue

        log(f"\n📦 Processing {name}")

        clean_previous_outputs(anim_dir)

        result = build_spritesheet(anim_dir)
        if not result:
            continue

        w, h, frames, cols = result
        build_preview(anim_dir, w, h, frames, cols)

    log("\n✅ Sprite sheets + previews rebuilt cleanly (multi-row safe)")

# ============================================================
# ENTRY
# ============================================================


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python build_spritesheets.py <2d_right_dir>")
        sys.exit(1)

    main(os.path.abspath(sys.argv[1]))
