import sys
from collections import deque
from statistics import median
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


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

FRAME_COUNT = 16
GRID_COLUMNS = 4
GRID_ROWS = 4
FRAME_DURATION_MS = 180
SAFE_OVERLAP_THRESHOLD = 0.02


def fit_panel_to_canvas(panel, size=320):
    panel = remove_white_background(panel)
    panel.thumbnail((size - 8, size - 8), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    left = (size - panel.width) // 2
    top = (size - panel.height) // 2
    canvas.alpha_composite(panel, (left, top))
    return canvas


def foreground_mask(image):
    """Create binary mask of non-background pixels."""
    pixels = image.convert("RGBA").load()
    width, height = image.size
    mask = bytearray(width * height)

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            # Detect background: transparent or white-ish with low color variation
            is_background = (
                a < 24 or  # Fully transparent
                (r > 240 and g > 240 and b > 240 and max(r, g, b) - min(r, g, b) < 15)  # Near-white
            )
            if not is_background:
                mask[y * width + x] = 1

    return mask


def remove_white_background(image, threshold=220, max_delta=25):
    """AI 생성 스프라이트 시트의 흰색/밝은 배경 픽셀을 투명(alpha=0)으로 변환"""
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


def bbox_from_points(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def all_foreground_bbox(mask, width, height):
    points = [(index % width, index // width) for index, value in enumerate(mask) if value]
    return bbox_from_points(points) if points else None


def connected_components(mask, width, height):
    visited = bytearray(width * height)
    components = []

    for start, value in enumerate(mask):
        if not value or visited[start]:
            continue

        queue = deque([start])
        visited[start] = 1
        points = []

        while queue:
            index = queue.popleft()
            x = index % width
            y = index // width
            points.append((x, y))

            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if nx < 0 or ny < 0 or nx >= width or ny >= height:
                    continue
                next_index = ny * width + nx
                if mask[next_index] and not visited[next_index]:
                    visited[next_index] = 1
                    queue.append(next_index)

        if len(points) >= 24:
            components.append({"area": len(points), "bbox": bbox_from_points(points)})

    return components


def character_bbox(image):
    width, height = image.size
    mask = foreground_mask(image)
    components = connected_components(mask, width, height)

    if not components:
        return all_foreground_bbox(mask, width, height)

    center_x = width / 2
    center_y = height / 2

    def score(component):
        left, top, right, bottom = component["bbox"]
        comp_x = (left + right) / 2
        comp_y = (top + bottom) / 2
        distance = abs(comp_x - center_x) + abs(comp_y - center_y)
        return component["area"] - distance * 2

    return max(components, key=score)["bbox"]


def frame_metrics(frame):
    bbox = character_bbox(frame)
    if not bbox:
        width, height = frame.size
        bbox = (0, 0, width, height)

    left, top, right, bottom = bbox
    return {
        "bbox": bbox,
        "center_x": (left + right) / 2,
        "center_y": (top + bottom) / 2,
        "height": max(1, bottom - top),
    }


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def calculate_stable_target(all_metrics):
    """Calculate target metrics using percentile-based filtering to reduce outlier impact."""
    if not all_metrics:
        return (160, 160, 200)
    
    centers_x = sorted([m["center_x"] for m in all_metrics])
    centers_y = sorted([m["center_y"] for m in all_metrics])
    heights = sorted([m["height"] for m in all_metrics])
    
    # Use 25th-75th percentile range to reduce outlier impact
    n = len(all_metrics)
    q1_idx = max(0, n // 4 - 1)
    q3_idx = min(n - 1, (3 * n) // 4)
    
    # Use median of middle 50% range
    target_center_x = (centers_x[q1_idx] + centers_x[q3_idx]) / 2
    target_center_y = (centers_y[q1_idx] + centers_y[q3_idx]) / 2
    target_height = (heights[q1_idx] + heights[q3_idx]) / 2
    
    return (target_center_x, target_center_y, target_height)


def normalize_frame(frame, metrics, target, size=320, frame_index=0):
    target_center_x, target_center_y, target_height = target
    bbox = metrics["bbox"]
    
    # Very strict scale bounds to prevent jitter (0.98-1.02 for minimal movement)
    scale = clamp(target_height / metrics["height"], 0.98, 1.02)
    scaled_size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
    scaled = frame.resize(scaled_size, Image.Resampling.LANCZOS)

    # Calculate placement based on target position
    left = round(target_center_x - metrics["center_x"] * scale)
    top = round(target_center_y - metrics["center_y"] * scale)

    # Very tight margin constraint to minimize any position drift (30px per side)
    margin = 30
    fg_left, fg_top, fg_right, fg_bottom = bbox
    left = max(left, round(margin - fg_left * scale))
    top = max(top, round(margin - fg_top * scale))
    left = min(left, round(size - margin - fg_right * scale))
    top = min(top, round(size - margin - fg_bottom * scale))

    # Create transparent background
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, (left, top))
    return canvas


def stabilize_loop_frames(rgba_frames):
    """Ensure frame 16 connects smoothly to frame 1 by averaging their metrics."""
    if len(rgba_frames) < 2:
        return rgba_frames
    
    # Get metrics for first and last frames
    metrics_0 = frame_metrics(rgba_frames[0])
    metrics_15 = frame_metrics(rgba_frames[-1])
    
    # Create interpolated target that averages frame 0 and frame 15
    loop_target = (
        (metrics_0["center_x"] + metrics_15["center_x"]) / 2,
        (metrics_0["center_y"] + metrics_15["center_y"]) / 2,
        (metrics_0["height"] + metrics_15["height"]) / 2
    )
    
    # Re-normalize both frames to the loop target
    all_metrics = [frame_metrics(f) for f in rgba_frames]
    rgba_frames[0] = normalize_frame(rgba_frames[0], all_metrics[0], loop_target, frame_index=0)
    rgba_frames[-1] = normalize_frame(rgba_frames[-1], all_metrics[-1], loop_target, frame_index=15)
    
    return rgba_frames


def load_label_font(label, size):
    font_path = next((path for path in FONT_CANDIDATES if Path(path).exists()), None)
    if not font_path:
        return ImageFont.load_default()
    return ImageFont.truetype(font_path, size=size)


def fit_label_font(label, max_width):
    size = 48
    while size >= 24:
        font = load_label_font(label, size)
        left, top, right, bottom = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), label, font=font, stroke_width=2)
        if right - left <= max_width:
            return font
        size -= 2
    return load_label_font(label, 24)


def label_seed(label):
    result = 0
    for char in label:
        result = (result * 31 + ord(char)) & 0xFFFFFFFF
    return result


def _candidate_slots(width, height, text_width, text_height):
    return [
        (12, 12),
        (width - text_width - 12, 12),
        (12, height - text_height - 12),
        (width - text_width - 12, height - text_height - 12),
        ((width - text_width) // 2, 8),
        ((width - text_width) // 2, height - text_height - 8),
    ]


def _overlap_count(mask, width, height, x, y, w, h):
    overlap = 0
    for py in range(max(0, y), min(height, y + h)):
        row_start = py * width
        for px in range(max(0, x), min(width, x + w)):
            if mask[row_start + px]:
                overlap += 1
    return overlap


def best_safe_position(mask, width, height, text_width, text_height):
    """Return (x, y, overlap_count) for the candidate slot with lowest foreground overlap."""
    candidates = _candidate_slots(width, height, text_width, text_height)
    best = candidates[0]
    best_overlap = _overlap_count(mask, width, height, best[0], best[1], text_width, text_height)
    for x, y in candidates[1:]:
        overlap = _overlap_count(mask, width, height, x, y, text_width, text_height)
        if overlap < best_overlap:
            best_overlap = overlap
            best = (x, y)
    return best[0], best[1], best_overlap


def smart_label_position(mask, width, height, text_width, text_height):
    """Find best position for label that avoids character foreground (single-frame)."""
    x, y, _ = best_safe_position(mask, width, height, text_width, text_height)
    return (x, y)


def global_safe_position(rgba_frames, text_width, text_height):
    """Choose one (x, y) outside the union of all frame foregrounds.

    Returns (x, y) if the best slot's overlap with the union mask is at or below
    SAFE_OVERLAP_THRESHOLD of the text area; otherwise None to signal the caller
    should drop the label rather than overlap the character.
    """
    if not rgba_frames:
        return None
    width, height = rgba_frames[0].size
    union = bytearray(width * height)
    for frame in rgba_frames:
        mask = foreground_mask(frame)
        for i, v in enumerate(mask):
            if v:
                union[i] = 1

    x, y, overlap = best_safe_position(union, width, height, text_width, text_height)
    area = max(1, text_width * text_height)
    if overlap / area > SAFE_OVERLAP_THRESHOLD:
        return None
    return (x, y)


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


def build_text_layer(label):
    """Build the rotated, padded text layer once for reuse across all 16 frames."""
    font = fit_label_font(label, 236)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), label, font=font, stroke_width=2)
    text_width = right - left
    text_height = bottom - top

    padding_x = 18
    padding_y = 14
    text_layer = Image.new("RGBA", (text_width + padding_x * 2, text_height + padding_y * 2), (255, 255, 255, 0))
    text_draw = ImageDraw.Draw(text_layer)
    text_x = padding_x - left
    text_y = padding_y - top
    text_draw.text((text_x + 1, text_y + 2), label, font=font, fill=(0, 0, 0, 65), stroke_width=2, stroke_fill=(0, 0, 0, 50))
    text_draw.text((text_x, text_y), label, font=font, fill=(38, 31, 25, 255), stroke_width=2, stroke_fill=(255, 255, 255, 235))

    seed = label_seed(label)
    angle = ((seed % 3) - 1) * 0.3
    if angle == 0:
        return text_layer
    return text_layer.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255, 0))


def draw_label(frame, label, frame_index, position=None, text_to_place=None):
    if not label:
        return frame

    canvas_rgba = frame.copy().convert("RGBA")
    if text_to_place is None:
        text_to_place = build_text_layer(label)

    if position is None:
        width, height = canvas_rgba.size
        fg_mask = foreground_mask(canvas_rgba)
        position = smart_label_position(fg_mask, width, height, text_to_place.width, text_to_place.height)

    canvas_rgba.alpha_composite(text_to_place, position)
    return canvas_rgba


def main():
    if len(sys.argv) not in (3, 4, 5):
        raise SystemExit("Usage: sprite_sheet_to_gif.py <sprite_sheet.png> <output.gif> [label] [debug_dir]")

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) >= 4 else ""
    debug_dir = Path(sys.argv[4]) if len(sys.argv) == 5 else None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    sprite = Image.open(input_path).convert("RGBA")
    width, height = sprite.size
    cell_width = width // GRID_COLUMNS
    cell_height = height // GRID_ROWS

    boxes = []
    for index in range(FRAME_COUNT):
        column = index % GRID_COLUMNS
        row = index // GRID_COLUMNS
        left = column * cell_width
        top = row * cell_height
        right = width if column == GRID_COLUMNS - 1 else (column + 1) * cell_width
        bottom = height if row == GRID_ROWS - 1 else (row + 1) * cell_height
        boxes.append((left, top, right, bottom))
    raw_frames = [fit_panel_to_canvas(sprite.crop(box)) for box in boxes]
    if debug_dir:
        input_copy = debug_dir / "raw_sprite_sheet.png"
        sprite.save(input_copy)
        for index, frame in enumerate(raw_frames, start=1):
            frame.save(debug_dir / f"split_{index:02d}.png")

    metrics = [frame_metrics(frame) for frame in raw_frames]
    target = calculate_stable_target(metrics)
    
    rgba_frames = [normalize_frame(frame, metric, target, frame_index=idx) 
                   for idx, (frame, metric) in enumerate(zip(raw_frames, metrics))]
    
    # Stabilize loop closure (frame 16 -> frame 1)
    rgba_frames = stabilize_loop_frames(rgba_frames)
    if debug_dir:
        for index, frame in enumerate(rgba_frames, start=1):
            frame.save(debug_dir / f"normalized_{index:02d}.png")

    if label:
        text_to_place = build_text_layer(label)
        pos = global_safe_position(rgba_frames, text_to_place.width, text_to_place.height)
        if pos is None:
            print(f"[sprite_sheet_to_gif] no overlap-free slot for label '{label}'; dropping text", file=sys.stderr)
            effective_label = ""
            text_to_place = None
        else:
            effective_label = label
    else:
        effective_label = ""
        text_to_place = None
        pos = None

    frames = [
        rgba_to_palette_with_transparency(draw_label(frame, effective_label, index, position=pos, text_to_place=text_to_place))
        for index, frame in enumerate(rgba_frames)
    ]
    if debug_dir:
        for index, frame in enumerate(frames, start=1):
            frame.convert("RGBA").save(debug_dir / f"labeled_{index:02d}.png")

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
