"""Draws the Tome Vault d20 icon at every size Android needs (run once; output is committed)."""
import os
from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(__file__), "..")
RES = os.path.join(ROOT, "app", "android", "app", "src", "main", "res")
OXBLOOD = (122, 26, 40, 255)
GOLD = (226, 195, 117, 255)
NIGHT = (16, 19, 26, 255)
ROSE = (212, 92, 112, 255)

# d20 line art in a 24x24 box (same drawing as the in-app logo)
LINES = [
    [(12, 2.5), (20.5, 7.3), (20.5, 16.7), (12, 21.5), (3.5, 16.7), (3.5, 7.3), (12, 2.5)],
    [(12, 2.5), (7.7, 15.2), (16.3, 15.2), (12, 2.5)],
    [(3.5, 7.3), (7.7, 15.2), (3.5, 16.7)],
    [(20.5, 7.3), (16.3, 15.2), (20.5, 16.7)],
    [(7.7, 15.2), (12, 21.5), (16.3, 15.2)],
]


def d20(draw, cx, cy, size, color, stroke):
    s = size / 24.0
    for line in LINES:
        pts = [(cx + (x - 12) * s, cy + (y - 12) * s) for x, y in line]
        draw.line(pts, fill=color, width=max(1, int(stroke)), joint="curve")
        r = stroke / 2
        for x, y in pts:
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def render(w, h, bg, shape, icon_frac, color, stroke_frac=0.075):
    k = 4  # supersample
    W, H = w * k, h * k
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    if shape == "square":
        dr.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(W * 0.22), fill=bg)
    elif shape == "circle":
        dr.ellipse([0, 0, W - 1, H - 1], fill=bg)
    elif shape == "full":
        dr.rectangle([0, 0, W, H], fill=bg)
    size = min(W, H) * icon_frac
    d20(dr, W / 2, H / 2, size, color, size * stroke_frac)
    return img.resize((w, h), Image.LANCZOS)


def main():
    legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for dens, px in legacy.items():
        d = os.path.join(RES, "mipmap-" + dens)
        os.makedirs(d, exist_ok=True)
        render(px, px, OXBLOOD, "square", 0.72, GOLD).save(os.path.join(d, "ic_launcher.png"))
        render(px, px, OXBLOOD, "circle", 0.66, GOLD).save(os.path.join(d, "ic_launcher_round.png"))
        fg = round(px * 108 / 48)
        render(fg, fg, None, None, 0.50, GOLD).save(os.path.join(d, "ic_launcher_foreground.png"))
    # splash screens: keep each file's existing size
    for folder in os.listdir(RES):
        p = os.path.join(RES, folder, "splash.png")
        if os.path.exists(p):
            w, h = Image.open(p).size
            render(w, h, NIGHT, "full", 0.30, ROSE, 0.06).convert("RGB").save(p)
    # web favicon / app icon for the browser version
    render(192, 192, OXBLOOD, "square", 0.72, GOLD).save(os.path.join(ROOT, "web", "icon.png"))
    render(512, 512, OXBLOOD, "square", 0.72, GOLD).save(os.path.join(ROOT, "docs-icon.png"))
    print("icons written")


if __name__ == "__main__":
    main()
