import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


CANVAS_SIZE = 320
FRAME_COUNT = 16
FRAME_DURATION_MS = 180
TARGET_CONTENT_SIZE = 242

FONT_CANDIDATES = [
    "/mnt/c/Windows/Fonts/HMFMPYUN.TTF",
    "/mnt/c/Windows/Fonts/HMKMRHD.TTF",
    "/mnt/c/Windows/Fonts/HMKMMAG.TTF",
    "/mnt/c/Windows/Fonts/HMKMAMI.TTF",
    "/mnt/c/Windows/Fonts/HMFMMUEX.TTC",
    "/mnt/c/Windows/Fonts/NotoSansKR-VF.ttf",
    "/mnt/c/Windows/Fonts/malgunbd.ttf",
    "/mnt/c/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def foreground_bbox(image):
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    points = []

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            is_background = a < 24 or (r > 238 and g > 238 and b > 238 and max(r, g, b) - min(r, g, b) < 20)
            if not is_background:
                points.append((x, y))

    if not points:
        return (0, 0, width, height)

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def remove_white_background(image, threshold=210, max_delta=30):
    """모션 GIF의 흰색/밝은 배경 픽셀을 투명(alpha=0)으로 변환"""
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a > 0 and r > threshold and g > threshold and b > threshold \
               and max(r, g, b) - min(r, g, b) < max_delta:
                pixels[x, y] = (r, g, b, 0)
    return rgba


def rgba_to_palette_with_transparency(rgba_image):
    """투명도를 보존하면서 RGBA → P(팔레트) 변환, 인덱스 255를 투명으로 예약"""
    alpha = rgba_image.split()[3]
    p_image = rgba_image.convert("RGB").quantize(colors=255, dither=Image.Dither.NONE)
    palette = p_image.getpalette()
    palette[255 * 3:255 * 3 + 3] = [255, 255, 255]
    p_image.putpalette(palette)
    p_data = bytearray(p_image.tobytes())
    a_data = alpha.tobytes()
    for i, a_val in enumerate(a_data):
        if a_val < 128:
            p_data[i] = 255
    result = Image.frombytes("P", p_image.size, bytes(p_data))
    result.putpalette(palette)
    return result


def crop_with_padding(image, padding_ratio=0.16):
    rgba = image.convert("RGBA")
    width, height = rgba.size
    left, top, right, bottom = foreground_bbox(rgba)
    box_width = max(1, right - left)
    box_height = max(1, bottom - top)
    padding = round(max(box_width, box_height) * padding_ratio)

    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(width, right + padding)
    bottom = min(height, bottom + padding)
    return rgba.crop((left, top, right, bottom))


def fit_subject(image):
    subject = crop_with_padding(image)
    subject.thumbnail((TARGET_CONTENT_SIZE, TARGET_CONTENT_SIZE), Image.Resampling.LANCZOS)
    return subject


def motion_steps(preset):
    base = [
        {"angle": 0, "scale": 1.0, "sx": 1.0, "sy": 1.0, "x": 0, "y": 0},
        {"angle": -2, "scale": 1.015, "sx": 1.0, "sy": 1.0, "x": -4, "y": -2},
        {"angle": 2, "scale": 1.025, "sx": 1.0, "sy": 1.0, "x": 4, "y": -4},
        {"angle": -3, "scale": 1.02, "sx": 1.0, "sy": 1.0, "x": -5, "y": -2},
        {"angle": 3, "scale": 1.03, "sx": 1.0, "sy": 1.0, "x": 5, "y": -5},
        {"angle": -2, "scale": 1.02, "sx": 1.0, "sy": 1.0, "x": -4, "y": -3},
        {"angle": 2, "scale": 1.015, "sx": 1.0, "sy": 1.0, "x": 4, "y": -2},
        {"angle": -1, "scale": 1.01, "sx": 1.0, "sy": 1.0, "x": -2, "y": -1},
        {"angle": 0, "scale": 1.0, "sx": 1.0, "sy": 1.0, "x": 0, "y": 0},
    ]

    presets = {
        "wave": [
            (0, 1.0, 1, 1, 0, 0),
            (-3, 1.01, 1, 1, -5, -2),
            (4, 1.02, 1, 1, 6, -4),
            (-5, 1.02, 1, 1, -7, -3),
            (5, 1.03, 1, 1, 7, -5),
            (-4, 1.02, 1, 1, -6, -3),
            (3, 1.015, 1, 1, 5, -2),
            (-2, 1.01, 1, 1, -3, -1),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "pop": [
            (0, 0.94, 1, 1, 0, 7),
            (0, 0.98, 1, 1, 0, 3),
            (0, 1.08, 1.03, 0.98, 0, -8),
            (-1, 1.13, 1.04, 0.96, 0, -12),
            (1, 1.08, 1, 1, 0, -7),
            (0, 1.03, 0.98, 1.03, 0, -2),
            (0, 1.0, 1, 1, 0, 0),
            (0, 1.02, 1, 1, 0, -2),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "recoil": [
            (0, 1.0, 1, 1, 0, 0),
            (0, 0.98, 1, 1, 0, 4),
            (-4, 1.08, 1.04, 0.97, -8, -8),
            (5, 1.13, 1.06, 0.94, 9, -13),
            (-3, 1.08, 1.02, 0.98, -6, -8),
            (2, 1.03, 1, 1, 4, -3),
            (0, 1.0, 1, 1, 0, 1),
            (0, 1.02, 1, 1, 0, -1),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "bounce": [
            (0, 1.0, 1, 1, 0, 0),
            (-1, 0.99, 1.04, 0.96, 0, 7),
            (1, 1.04, 0.98, 1.04, 0, -10),
            (-1, 1.0, 1.03, 0.97, 0, 5),
            (1, 1.06, 0.98, 1.05, 0, -13),
            (0, 1.0, 1.02, 0.98, 0, 4),
            (0, 1.03, 1, 1, 0, -6),
            (0, 1.0, 1, 1, 0, 1),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "bow": [
            (0, 1.0, 1, 1, 0, 0),
            (1, 1.0, 1.02, 0.98, 0, 8),
            (3, 0.99, 1.05, 0.94, 0, 17),
            (4, 0.98, 1.08, 0.91, 0, 25),
            (3, 0.99, 1.06, 0.94, 0, 20),
            (1, 1.0, 1.02, 0.98, 0, 10),
            (0, 1.0, 1, 1, 0, 3),
            (0, 1.01, 1, 1, 0, -2),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "shake": [
            (0, 1.0, 1, 1, 0, 0),
            (-4, 1.01, 1, 1, -9, 0),
            (4, 1.02, 1, 1, 9, -1),
            (-5, 1.02, 1, 1, -10, 0),
            (5, 1.03, 1, 1, 10, -2),
            (-4, 1.02, 1, 1, -8, 0),
            (3, 1.01, 1, 1, 6, -1),
            (-2, 1.0, 1, 1, -4, 0),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "droop": [
            (0, 1.0, 1, 1, 0, 0),
            (-1, 0.995, 1, 1, 0, 5),
            (-2, 0.99, 1.02, 0.98, 0, 11),
            (-3, 0.985, 1.03, 0.96, 0, 18),
            (-3, 0.98, 1.04, 0.95, 0, 23),
            (-2, 0.985, 1.03, 0.97, 0, 18),
            (-1, 0.99, 1.01, 0.99, 0, 12),
            (0, 0.995, 1, 1, 0, 6),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "plead": [
            (0, 0.98, 1, 1, 0, 4),
            (-1, 1.0, 1, 1, 0, 0),
            (1, 1.04, 1.02, 0.99, 0, -5),
            (-1, 1.07, 1.03, 0.98, 0, -8),
            (1, 1.04, 1.02, 0.99, 0, -5),
            (-1, 1.07, 1.03, 0.98, 0, -8),
            (0, 1.03, 1, 1, 0, -3),
            (0, 1.0, 1, 1, 0, 0),
            (0, 0.98, 1, 1, 0, 4),
        ],
        "jump": [
            (0, 1.0, 1, 1, 0, 4),
            (0, 0.98, 1.05, 0.95, 0, 12),
            (-2, 1.05, 0.98, 1.04, 0, -12),
            (2, 1.08, 0.97, 1.05, 0, -22),
            (0, 1.05, 0.98, 1.03, 0, -14),
            (0, 0.99, 1.04, 0.96, 0, 8),
            (0, 1.02, 1, 1, 0, -4),
            (0, 1.0, 1, 1, 0, 0),
            (0, 1.0, 1, 1, 0, 4),
        ],
        "rush": [
            (0, 1.0, 1, 1, 0, 0),
            (-2, 1.01, 1.04, 0.98, -12, -2),
            (2, 1.02, 1.06, 0.96, 13, -3),
            (-3, 1.02, 1.08, 0.95, -15, -2),
            (3, 1.03, 1.08, 0.95, 15, -4),
            (-2, 1.02, 1.06, 0.97, -11, -2),
            (2, 1.01, 1.04, 0.98, 9, -1),
            (0, 1.0, 1, 1, 3, 0),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "march": [
            (0, 1.0, 1, 1, -4, 0),
            (-1, 1.01, 1, 1, 0, -3),
            (1, 1.0, 1, 1, 4, 1),
            (-1, 1.01, 1, 1, 8, -3),
            (1, 1.0, 1, 1, 4, 1),
            (-1, 1.01, 1, 1, 0, -3),
            (1, 1.0, 1, 1, -4, 1),
            (0, 1.0, 1, 1, -2, 0),
            (0, 1.0, 1, 1, -4, 0),
        ],
        "stretch": [
            (0, 0.98, 1.02, 0.98, 0, 8),
            (0, 1.0, 1, 1.02, 0, 1),
            (-1, 1.04, 0.98, 1.08, 0, -11),
            (1, 1.07, 0.96, 1.12, 0, -18),
            (0, 1.04, 0.98, 1.06, 0, -10),
            (0, 1.01, 1, 1.02, 0, -2),
            (0, 1.0, 1, 1, 0, 0),
            (0, 1.01, 1, 1, 0, -2),
            (0, 0.98, 1.02, 0.98, 0, 8),
        ],
        "nod": [
            (0, 1.0, 1, 1, 0, 0),
            (1, 1.01, 1, 0.99, 0, 5),
            (2, 1.02, 1.02, 0.97, 0, 10),
            (1, 1.01, 1, 0.99, 0, 4),
            (0, 1.0, 1, 1, 0, -2),
            (1, 1.01, 1.01, 0.98, 0, 7),
            (0, 1.0, 1, 1, 0, 1),
            (0, 1.0, 1, 1, 0, 0),
            (0, 1.0, 1, 1, 0, 0),
        ],
        "stop": [
            (0, 1.0, 1, 1, 0, 0),
            (-1, 1.02, 1, 1, -3, -2),
            (0, 1.05, 1.03, 0.98, -6, -4),
            (1, 1.08, 1.05, 0.96, -8, -5),
            (0, 1.05, 1.04, 0.97, -6, -3),
            (0, 1.04, 1.03, 0.98, -6, -3),
            (0, 1.02, 1, 1, -3, -1),
            (0, 1.0, 1, 1, -1, 0),
            (0, 1.0, 1, 1, 0, 0),
        ],
    }

    selected = presets.get(preset, None)
    if not selected:
        selected = base
    keyframes = [{"angle": a, "scale": sc, "sx": sx, "sy": sy, "x": x, "y": y} for a, sc, sx, sy, x, y in selected]
    return resample_steps(keyframes, FRAME_COUNT)


def resample_steps(keyframes, frame_count):
    if len(keyframes) == frame_count:
        return keyframes

    steps = []
    max_source_index = len(keyframes) - 1
    for index in range(frame_count):
        source_position = (index / (frame_count - 1)) * max_source_index
        left_index = min(max_source_index, math.floor(source_position))
        right_index = min(max_source_index, left_index + 1)
        ratio = source_position - left_index
        left = keyframes[left_index]
        right = keyframes[right_index]
        steps.append({
            key: left[key] + (right[key] - left[key]) * ratio
            for key in ("angle", "scale", "sx", "sy", "x", "y")
        })
    return steps


def load_label_font(size):
    font_path = next((path for path in FONT_CANDIDATES if Path(path).exists()), None)
    if not font_path:
        return ImageFont.load_default()
    return ImageFont.truetype(font_path, size=size)


def fit_label_font(label, max_width):
    size = 48
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    while size >= 24:
        font = load_label_font(size)
        left, top, right, bottom = probe.textbbox((0, 0), label, font=font, stroke_width=2)
        if right - left <= max_width:
            return font
        size -= 2
    return load_label_font(24)


def label_seed(label):
    result = 0
    for char in label:
        result = (result * 31 + ord(char)) & 0xFFFFFFFF
    return result


def draw_label(frame, label):
    if not label:
        return frame

    canvas = frame.copy()
    font = fit_label_font(label, 236)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), label, font=font, stroke_width=2)
    text_width = right - left
    text_height = bottom - top

    padding_x = 20
    padding_y = 16
    text_layer = Image.new("RGBA", (text_width + padding_x * 2, text_height + padding_y * 2), (255, 255, 255, 0))
    text_draw = ImageDraw.Draw(text_layer)
    text_x = padding_x - left
    text_y = padding_y - top
    text_draw.text((text_x + 1, text_y + 2), label, font=font, fill=(0, 0, 0, 65), stroke_width=2, stroke_fill=(0, 0, 0, 50))
    text_draw.text((text_x, text_y), label, font=font, fill=(38, 31, 25, 255), stroke_width=2, stroke_fill=(255, 255, 255, 235))

    seed = label_seed(label)
    angle = ((seed % 9) - 4) * 0.7
    rotated = text_layer.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255, 0))
    x = (CANVAS_SIZE - rotated.width) // 2 + ((seed // 11) % 7) - 3
    y = CANVAS_SIZE - rotated.height - 12 + ((seed // 17) % 5) - 2
    canvas.alpha_composite(rotated, (x, y))
    return canvas


def render_frame(subject, step, label):
    base_width, base_height = subject.size
    width = max(1, round(base_width * step["scale"] * step["sx"]))
    height = max(1, round(base_height * step["scale"] * step["sy"]))
    content = subject.resize((width, height), Image.Resampling.LANCZOS)
    content = content.rotate(step["angle"], resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255, 0))

    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    left = (CANVAS_SIZE - content.width) // 2 + round(step["x"])
    top = (CANVAS_SIZE - content.height) // 2 + round(step["y"]) - 16
    canvas.alpha_composite(content, (left, top))
    return rgba_to_palette_with_transparency(draw_label(remove_white_background(canvas), label))


def main():
    if len(sys.argv) not in (3, 4, 5):
        raise SystemExit("Usage: image_to_motion_gif.py <base_image> <output.gif> [label] [motion_preset]")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) >= 4 else ""
    preset = sys.argv[4] if len(sys.argv) >= 5 else "bounce"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subject = fit_subject(Image.open(input_path))
    frames = [render_frame(subject, step, label) for step in motion_steps(preset)]
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        transparency=255,
        disposal=2,
    )


if __name__ == "__main__":
    main()
