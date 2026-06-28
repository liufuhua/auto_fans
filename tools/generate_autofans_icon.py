from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "launcher" / "assets" / "autofans.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw_icon(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(x * scale, y * scale) for x, y in points]

    radius = 56 * scale
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=radius,
        fill=(17, 24, 39, 255),
    )
    draw.ellipse(
        (36 * scale, 36 * scale, 220 * scale, 220 * scale),
        fill=(16, 185, 129, 255),
    )
    draw.ellipse(
        (56 * scale, 56 * scale, 200 * scale, 200 * scale),
        fill=(249, 250, 251, 255),
    )

    stroke = max(1, round(14 * scale))
    blade_fill = (17, 24, 39, 255)
    blades = [
        [(112, 113), (88, 88), (101, 54), (134, 48), (152, 78), (142, 104)],
        [(143, 116), (177, 107), (201, 134), (190, 166), (155, 167), (134, 146)],
        [(125, 144), (115, 178), (80, 186), (56, 163), (73, 132), (103, 124)],
    ]
    for blade in blades:
        draw.polygon(xy(blade), fill=blade_fill)
        draw.line(xy(blade + [blade[0]]), fill=blade_fill, width=stroke, joint="curve")

    draw.ellipse(
        (114 * scale, 114 * scale, 142 * scale, 142 * scale),
        fill=blade_fill,
    )
    return image


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    images = [draw_icon(size) for size in SIZES]
    images[-1].save(OUTPUT_PATH, sizes=[(size, size) for size in SIZES], append_images=images[:-1])
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
