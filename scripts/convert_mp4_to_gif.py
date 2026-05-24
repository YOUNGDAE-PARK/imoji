import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: convert_mp4_to_gif.py <input.mp4> <output.gif>")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
        from moviepy.editor import VideoFileClip
    except Exception as exc:
        raise SystemExit(
            "moviepy is required for real Veo conversion.\n"
            f"Python executable: {sys.executable}\n"
            "Install with: python3 -m pip install -r requirements.txt\n"
            f"Original import error: {exc}"
        ) from exc

    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.Resampling.LANCZOS

    clip = VideoFileClip(str(input_path)).without_audio()
    duration = min(clip.duration or 2.0, 2.4)
    clip = clip.subclip(0, duration).resize((320, 320)).set_fps(12)
    clip.write_gif(str(output_path), fps=12, program="imageio", opt="nq", logger=None)
    clip.close()


if __name__ == "__main__":
    main()
