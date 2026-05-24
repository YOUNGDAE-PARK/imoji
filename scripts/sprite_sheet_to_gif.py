import sys
from pathlib import Path
from PIL import Image


def fit_panel_to_frame(panel, size=320):
    panel = panel.convert("RGBA")
    panel.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    left = (size - panel.width) // 2
    top = (size - panel.height) // 2
    canvas.alpha_composite(panel, (left, top))
    return canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: sprite_sheet_to_gif.py <sprite_sheet.png> <output.gif>")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sprite = Image.open(input_path).convert("RGBA")
    width, height = sprite.size
    mid_x = width // 2
    mid_y = height // 2

    boxes = [
        (0, 0, mid_x, mid_y),
        (mid_x, 0, width, mid_y),
        (0, mid_y, mid_x, height),
        (mid_x, mid_y, width, height),
    ]
    frames = [fit_panel_to_frame(sprite.crop(box)) for box in boxes]

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=200,
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
