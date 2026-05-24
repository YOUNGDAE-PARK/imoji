import sys
from pathlib import Path
from PIL import Image


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: frames_to_gif.py <frame_dir> <output.gif>")

    frame_dir = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    frame_paths = sorted(frame_dir.glob("frame_*.png"))
    if not frame_paths:
        raise SystemExit(f"No frame_*.png files found in {frame_dir}")

    frames = []
    for frame_path in frame_paths:
        image = Image.open(frame_path).convert("RGBA")
        image.thumbnail((320, 320), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (320, 320), (255, 255, 255, 255))
        left = (320 - image.width) // 2
        top = (320 - image.height) // 2
        canvas.alpha_composite(image, (left, top))
        frames.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=250,
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
