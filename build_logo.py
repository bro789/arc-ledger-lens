"""Build original project SVG/480px PNG using geometric primitives. No external art.

Pillow is an optional development dependency for this asset regeneration script.
The web application and accounting CLI do not depend on it.
"""
from pathlib import Path
from shutil import copyfile
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
SIZE, SUPERSAMPLE = 480, 4
PAPER, GREEN, INK = "#f4f6ef", "#c7ef83", "#14291e"

# This same ordered primitive list drives both the editable vector and raster.
# Ledger rows + inspection lens + check, not a Circle or Arc brand mark.
SHAPES = [
    ("rect", {"x": 0, "y": 0, "width": 480, "height": 480, "fill": PAPER}),
    ("rect", {"x": 91, "y": 95, "width": 215, "height": 270, "rx": 25, "fill": GREEN, "stroke": INK, "stroke-width": 16}),
    ("line", {"x1": 135, "y1": 155, "x2": 257, "y2": 155, "stroke": INK, "stroke-width": 15, "stroke-linecap": "round"}),
    ("line", {"x1": 135, "y1": 208, "x2": 248, "y2": 208, "stroke": INK, "stroke-width": 15, "stroke-linecap": "round"}),
    ("line", {"x1": 135, "y1": 261, "x2": 178, "y2": 261, "stroke": INK, "stroke-width": 15, "stroke-linecap": "round"}),
    ("line", {"x1": 340, "y1": 334, "x2": 388, "y2": 382, "stroke": INK, "stroke-width": 27, "stroke-linecap": "round"}),
    ("circle", {"cx": 292, "cy": 285, "r": 76, "fill": PAPER, "stroke": INK, "stroke-width": 16}),
    ("circle", {"cx": 292, "cy": 285, "r": 53, "fill": GREEN}),
    ("line", {"x1": 266, "y1": 285, "x2": 285, "y2": 304, "stroke": INK, "stroke-width": 13, "stroke-linecap": "round"}),
    ("line", {"x1": 285, "y1": 304, "x2": 318, "y2": 266, "stroke": INK, "stroke-width": 13, "stroke-linecap": "round"}),
]


def build():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    xml = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"480\" height=\"480\" viewBox=\"0 0 480 480\" role=\"img\" aria-labelledby=\"title desc\">",
           "<title id=\"title\">Arc Ledger Lens project logo</title>",
           "<desc id=\"desc\">An original geometric ledger with an inspection lens and verification check.</desc>",
           "<metadata>Copyright (c) 2026 Arc Ledger Lens contributors. MIT License. Original project artwork; no Circle or Arc trademark assets.</metadata>"]
    image = Image.new("RGB", (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE), PAPER)
    draw = ImageDraw.Draw(image)
    s = lambda n: round(n * SUPERSAMPLE)
    for kind, p in SHAPES:
        xml.append("  <" + kind + " " + " ".join(f'{key}=\"{value}\"' for key, value in p.items()) + "/>")
        stroke, width = p.get("stroke"), s(p.get("stroke-width", 0))
        if kind == "rect":
            box = (s(p["x"]), s(p["y"]), s(p["x"] + p["width"]), s(p["y"] + p["height"]))
            if stroke:
                # SVG stroke straddles its geometry; Pillow outline is inside.
                half = width // 2
                outer = (box[0] - half, box[1] - half, box[2] + half, box[3] + half)
                inner = (box[0] + half, box[1] + half, box[2] - half, box[3] - half)
                draw.rounded_rectangle(outer, radius=s(p.get("rx", 0)) + half, fill=stroke)
                draw.rounded_rectangle(inner, radius=max(0, s(p.get("rx", 0)) - half), fill=p["fill"])
            else:
                draw.rectangle(box, fill=p["fill"])
        elif kind == "circle":
            x, y, r = s(p["cx"]), s(p["cy"]), s(p["r"])
            if stroke:
                half = width // 2
                draw.ellipse((x - r - half, y - r - half, x + r + half, y + r + half), fill=stroke)
                draw.ellipse((x - r + half, y - r + half, x + r - half, y + r - half), fill=p["fill"])
            else:
                draw.ellipse((x - r, y - r, x + r, y + r), fill=p["fill"])
        elif kind == "line":
            start, end = (s(p["x1"]), s(p["y1"])), (s(p["x2"]), s(p["y2"]))
            draw.line([start, end], fill=stroke, width=width)
            half = width // 2
            for x, y in (start, end):
                draw.ellipse((x - half, y - half, x + half, y + half), fill=stroke)
    xml.append("</svg>")
    (assets / "logo.svg").write_text("\n".join(xml) + "\n", encoding="utf-8")
    image.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(assets / "logo.png", optimize=True)
    for name in ("logo.svg", "logo.png"):
        copyfile(assets / name, ROOT / "web" / name)
    print(f"Original SVG and {SIZE}x{SIZE} PNG ready. PNG bytes: {(assets / 'logo.png').stat().st_size}")


if __name__ == "__main__":
    build()
