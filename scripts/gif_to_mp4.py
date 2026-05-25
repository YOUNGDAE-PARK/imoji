import sys
from pathlib import Path

from PIL import Image, ImageSequence


FRAME_DURATION_MS = 180
WHITE = (255, 255, 255)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: gif_to_mp4.py <input.gif> <output.mp4>")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import imageio.v2 as imageio
        import numpy as np
    except Exception as exc:
        raise SystemExit(
            "imageio and numpy are required for MP4 export.\n"
            f"Python executable: {sys.executable}\n"
            "Install with: python -m pip install -r requirements.txt\n"
            f"Original import error: {exc}"
        ) from exc

    gif = Image.open(input_path)
    duration_ms = int(gif.info.get("duration") or FRAME_DURATION_MS)
    fps = 1000 / max(1, duration_ms)

    with imageio.get_writer(
        output_path,
        fps=fps,
        codec="libx264",
        quality=8,
        macro_block_size=1,
        output_params=["-movflags", "faststart"],
    ) as writer:
        for frame in ImageSequence.Iterator(gif):
            rgba = frame.convert("RGBA")
            canvas = Image.new("RGBA", rgba.size, (*WHITE, 255))
            canvas.alpha_composite(rgba)
            writer.append_data(np.asarray(canvas.convert("RGB")))


if __name__ == "__main__":
    main()
