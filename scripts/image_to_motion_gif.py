import sys
from pathlib import Path
from PIL import Image


def fit_on_canvas(image, size=320):
    image = image.convert("RGBA")
    image.thumbnail((276, 276), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    left = (size - image.width) // 2
    top = (size - image.height) // 2
    canvas.alpha_composite(image, (left, top))
    return canvas


def motion_frame(base, angle, scale, offset_y):
    size = 320
    layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    content = base.convert("RGBA")
    content = content.resize((int(size * scale), int(size * scale)), Image.Resampling.LANCZOS)
    content = content.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(255, 255, 255, 0))
    left = (size - content.width) // 2
    top = (size - content.height) // 2 + offset_y
    layer.alpha_composite(content, (left, top))

    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    canvas.alpha_composite(layer)
    return canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: image_to_motion_gif.py <base_image> <output.gif>")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = fit_on_canvas(Image.open(input_path))
    steps = [
        (0, 1.0, 0),
        (-2.5, 1.015, -3),
        (2.5, 1.02, -5),
        (0, 1.0, 0),
    ]
    frames = [motion_frame(base, angle, scale, offset_y) for angle, scale, offset_y in steps]

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=180,
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
