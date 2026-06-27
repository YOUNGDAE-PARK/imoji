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
        # Ensure it's 320x320
        canvas = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        left = (320 - image.width) // 2
        top = (320 - image.height) // 2
        canvas.alpha_composite(image, (left, top))
        
        # Use the same transparency-preserving palette conversion as V1
        frames.append(rgba_to_palette_with_transparency(canvas))

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=180,  # Match V1 duration
        loop=0,
        transparency=255,
        disposal=2,
        optimize=False,
    )

def rgba_to_palette_with_transparency(rgba_image):
    """Convert RGBA frame to GIF palette image while preserving transparency."""
    rgba_image = rgba_image.convert("RGBA")
    alpha = rgba_image.split()[3]

    # Use a fallback color for almost-transparent pixels
    rgb_image = Image.new("RGB", rgba_image.size, (255, 255, 255))
    rgb_image.paste(rgba_image.convert("RGB"), mask=alpha)

    # Quantize to 255 colors, leaving index 255 for transparency
    p_image = rgb_image.quantize(colors=255, dither=Image.Dither.NONE)
    palette = p_image.getpalette() or []
    palette = palette[:256 * 3]
    if len(palette) < 256 * 3:
        palette.extend([255] * (256 * 3 - len(palette)))
    
    # Set index 255 to white (or whatever your fallback is)
    palette[255 * 3:255 * 3 + 3] = [255, 255, 255]
    palette_bytes = bytes(palette)
    p_image.putpalette(palette_bytes, "RGB")

    p_data = bytearray(p_image.tobytes())
    for i, a_val in enumerate(alpha.tobytes()):
        if a_val < 128:
            p_data[i] = 255

    result = Image.frombytes("P", p_image.size, bytes(p_data))
    result.putpalette(palette_bytes, "RGB")
    result.info["transparency"] = 255
    result.info["background"] = 255
    return result


if __name__ == "__main__":
    main()
