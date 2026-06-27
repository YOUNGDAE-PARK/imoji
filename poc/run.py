#!/usr/bin/env python3
"""
POC: KakaoTalk Emoji Generator
스케치 → 베이스 캐릭터 → 기쁨/슬픔 애니메이션 GIF

실행: .venv/bin/python poc/run.py
"""

import sys, os, math, json, base64, time, hashlib, re
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "slack-gif-creator"))

# ── env 로드 ──────────────────────────────────────────────────────────────────
for line in (ROOT / ".env.local").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip()

API_KEY         = os.environ["GEMINI_API_KEY"]
IMAGEN_MODEL    = "imagen-4.0-fast-generate-001"
VISION_MODEL    = "gemini-2.5-flash"
IMAGE_GEN_MODEL = "gemini-2.5-flash-image"

OUTPUT_DIR  = ROOT / "poc" / "output"
SKETCH_PATH = ROOT / "scripts" / "sketch.png"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Google AI 클라이언트 ──────────────────────────────────────────────────────
from google import genai
from google.genai import types as gtypes

client = genai.Client(api_key=API_KEY)

# ── PIL / GIFBuilder ──────────────────────────────────────────────────────────
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core.gif_builder import GIFBuilder
from core.easing import interpolate


# ═════════════════════════════════════════════════════════════════════════════
# STAGE 1: 스케치 분석 → 캐릭터 DNA
# ═════════════════════════════════════════════════════════════════════════════
def analyze_sketch() -> dict:
    print("\n[Stage 1] 스케치 분석 중...")
    sketch_b64 = base64.b64encode(SKETCH_PATH.read_bytes()).decode()
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            gtypes.Part.from_bytes(data=base64.b64decode(sketch_b64), mime_type="image/png"),
            gtypes.Part.from_text(text="""캐릭터 디자이너로서 이 스케치를 분석해 AI 이미지 생성용 캐릭터 DNA를 추출해줘.

아래 JSON만 출력 (다른 텍스트 없이):
{
  "body_shape": "몸 형태와 비율 설명",
  "head_features": "귀, 주둥이, 얼굴 형태 설명",
  "eyes": "눈 모양, 크기, 위치",
  "limbs": "팔/다리 설명",
  "unique_details": "특이한 디테일",
  "colors": "추정 색상",
  "vibe": "캐릭터 느낌 형용사 3개",
  "base_prompt": "이 캐릭터를 카카오톡 이모티콘으로 생성하기 위한 영문 프롬프트 (100단어 내외)"
}"""),
        ],
    )
    raw = resp.text or ""
    m = __import__("re").search(r"\{[\s\S]*\}", raw)
    if not m:
        raise RuntimeError(f"캐릭터 DNA 파싱 실패:\n{raw}")
    dna = json.loads(m.group())
    print(f"  body: {dna.get('body_shape','?')[:60]}")
    print(f"  vibe: {dna.get('vibe','?')}")
    return dna


# ═════════════════════════════════════════════════════════════════════════════
# STAGE 2: 베이스 캐릭터 PNG (Imagen 4.0)
# ═════════════════════════════════════════════════════════════════════════════
def generate_base_character(dna: dict) -> tuple[Path, dict]:
    print("\n[Stage 2] 베이스 캐릭터 생성 중 (Imagen 4.0)...")
    prompt = (
        f"{dna['base_prompt']} "
        "KakaoTalk commercial emoji art style, thick black outlines, "
        "flat pastel body color (soft cream-white #F5F0E8), "
        "pure white background (#FFFFFF), centered, "
        "front-facing neutral pose, cute kawaii, professional sticker quality, "
        "no text, no watermark."
    )
    print(f"  prompt: {prompt[:100]}...")
    resp = client.models.generate_images(
        model=IMAGEN_MODEL,
        prompt=prompt,
        config=gtypes.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
    )
    img_bytes = resp.generated_images[0].image.image_bytes
    if isinstance(img_bytes, str):
        img_bytes = base64.b64decode(img_bytes)
    out = OUTPUT_DIR / "base_character.png"
    out.write_bytes(img_bytes)
    print(f"  저장: {out}")

    # 생성된 베이스 이미지에서 정확한 색상 코드 추출
    colors = extract_colors(out)
    print(f"  추출 색상: {colors}")
    return out, colors


def extract_colors(img_path: Path) -> dict:
    """Gemini Vision으로 베이스 캐릭터의 정확한 색상 코드 추출."""
    print("  색상 코드 추출 중...")
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    resp = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            gtypes.Part.from_bytes(data=base64.b64decode(b64), mime_type="image/png"),
            gtypes.Part.from_text(text="""이 캐릭터 이미지에서 정확한 색상 코드를 추출해줘.
아래 JSON만 출력 (다른 텍스트 없이):
{
  "body": "몸통 주요 색상 hex 코드 (예: #F5F0E8)",
  "outline": "외곽선 색상 hex 코드 (예: #2A2A2A)",
  "ear_inner": "귀 안쪽 색상 hex 코드 (없으면 body와 동일)",
  "cheek": "볼 색상 hex 코드 (없으면 null)",
  "background": "배경 색상 hex 코드 (예: #FFFFFF)"
}"""),
        ],
    )
    raw = resp.text or ""
    m = __import__("re").search(r"\{[\s\S]*?\}", raw)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {"body": "#F5F0E8", "outline": "#2A2A2A", "background": "#FFFFFF"}


# ═════════════════════════════════════════════════════════════════════════════
# STAGE 3: 감정별 액션 키프레임 4장 생성
# AI가 각 키프레임의 구체적인 동작 순간을 표현
# ═════════════════════════════════════════════════════════════════════════════

# 각 감정의 액션을 4단계 키프레임으로 분해
EMOTION_KEYFRAMES = {
    "joy": [
        {
            "label": "ready",
            "desc": "standing upright, gentle smile, arms relaxed at sides, weight on both feet",
        },
        {
            "label": "squat",
            "desc": "both knees visibly bent downward in a squat position, body lowering, arms pulled slightly back, excited face, preparing to jump — lower body crouch must be clearly visible",
        },
        {
            "label": "leap",
            "desc": "just leaving the ground, legs beginning to straighten, arms swinging forward and upward, mouth open in a big smile, body lifting, vibrant expression, no drop shadow, no cast shadow",
        },
        {
            "label": "peak",
            "desc": "at the highest peak of the jump, both arms fully raised in a wide V above head, eyes closed with joy (><), big open smile, colorful small pink hearts and yellow sparkles floating around, no drop shadow, no cast shadow",
        },
        {
            "label": "descend",
            "desc": "coming back down, arms beginning to lower from raised position, eyes opening, happy smile, body slightly above ground, NO ground shadow, NO drop shadow, pure white floor",
        },
        {
            "label": "land",
            "desc": "just landed softly, knees gently bent absorbing impact, arms at sides, bright smile, stable standing pose",
        },
    ],
    "sadness": [
        {
            "label": "neutral_sad",
            "desc": "standing still, mildly sad expression, small frown, arms at sides, eyes slightly droopy",
        },
        {
            "label": "cry_start",
            "desc": "tears beginning to form in eyes, mouth turned further down, shoulders starting to slump, arms still at sides",
        },
        {
            "label": "arm_raise",
            "desc": "right arm slowly raising up, elbow bending, hand/paw at about chest height moving toward face, tears on cheeks, very sad expression",
        },
        {
            "label": "wipe",
            "desc": "right hand/paw firmly pressed against eye wiping tears, scrunched-up crying face, eyes tightly shut with tear lines, left arm hanging at side, blue tears on cheek, NO drop shadow",
        },
        {
            "label": "arm_lower",
            "desc": "right arm lowering back down from face, hand near cheek level, eyes reopening still watery, fresh tears forming, sad sniffling look",
        },
        {
            "label": "slump",
            "desc": "arm fully lowered, shoulders drooped, head slightly bowed, tears on cheeks, dejected slumped posture, arms hanging limp",
        },
    ],
    "surprise": [
        {
            "label": "calm",
            "desc": "standing relaxed, neutral calm expression, arms at sides, eyes half-open, peaceful look",
        },
        {
            "label": "notice",
            "desc": "eyes beginning to widen, eyebrows raising, mouth slightly open, body stiffening, something caught attention",
        },
        {
            "label": "shock",
            "desc": "full shock reaction, eyes extremely wide and round (O_O), mouth wide open in a large O shape, body jerking backward slightly, eyebrows raised to top of head, pure white background, no shadow",
        },
        {
            "label": "hands_cheeks",
            "desc": "both hands/paws pressed against cheeks in Home Alone style, eyes huge and round, mouth wide open O, body upright, yellow exclamation marks and stars bursting around head, no shadow",
        },
        {
            "label": "settle",
            "desc": "hands starting to lower from cheeks, eyes still wide but calming, mouth half-closed, body steadying, still surprised but recovering",
        },
        {
            "label": "recover",
            "desc": "arms returning to sides, eyes back to normal size with surprised/amused look, small smile forming, body relaxed, tiny sweat drop on forehead",
        },
    ],
}

PARAMS_FALLBACK = {"hold_ms": 150, "dy": 0, "dx": 0, "shake_x": 0}

# Imagen fallback 시 레이블 기반 규칙 (AI params를 얻지 못한 경우에만)
_LABEL_RULES: dict[str, dict] = {
    "ready":       {"hold_ms": 200, "dy":   0, "dx": 0, "shake_x": 0},
    "squat":       {"hold_ms": 100, "dy":   8, "dx": 0, "shake_x": 0},
    "leap":        {"hold_ms": 100, "dy": -15, "dx": 0, "shake_x": 0},
    "peak":        {"hold_ms": 350, "dy": -22, "dx": 0, "shake_x": 0},
    "descend":     {"hold_ms": 100, "dy":  -8, "dx": 0, "shake_x": 0},
    "land":        {"hold_ms": 200, "dy":   0, "dx": 0, "shake_x": 0},
    "neutral_sad": {"hold_ms": 200, "dy":   0, "dx": 0, "shake_x": 0},
    "cry_start":   {"hold_ms": 100, "dy":   0, "dx": 0, "shake_x": 0},
    "arm_raise":   {"hold_ms": 100, "dy":   0, "dx": 0, "shake_x": 0},
    "wipe":        {"hold_ms": 400, "dy":   0, "dx": 0, "shake_x": 6},
    "arm_lower":   {"hold_ms": 100, "dy":   0, "dx": 0, "shake_x": 0},
    "slump":       {"hold_ms": 400, "dy":   0, "dx": 0, "shake_x": 0},
    "calm":        {"hold_ms": 200, "dy":   0, "dx": 0, "shake_x": 0},
    "notice":      {"hold_ms": 100, "dy":   0, "dx": 0, "shake_x": 0},
    "shock":       {"hold_ms": 150, "dy":  -8, "dx": 0, "shake_x": 4},
    "hands_cheeks":{"hold_ms": 400, "dy":  -5, "dx": 0, "shake_x": 5},
    "settle":      {"hold_ms": 150, "dy":   0, "dx": 0, "shake_x": 0},
    "recover":     {"hold_ms": 300, "dy":   0, "dx": 0, "shake_x": 0},
}

def _parse_params(text: str) -> dict:
    """Gemini 텍스트에서 params JSON 추출. 실패 시 PARAMS_FALLBACK."""
    m = re.search(r'\{[^{}]*"hold_ms"[^{}]*\}', text) or re.search(r'\{[\s\S]*?\}', text)
    if m:
        try:
            p = json.loads(m.group())
            return {
                "hold_ms": max(50, min(600, int(p.get("hold_ms", 150)))),
                "dy":      max(-30, min(30,  int(p.get("dy",      0)))),
                "dx":      max(-10, min(10,  int(p.get("dx",      0)))),
                "shake_x": max(0,   min(12,  int(p.get("shake_x", 0)))),
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return PARAMS_FALLBACK.copy()

def _call_image_gen_with_params(base_b64: str, prompt: str) -> tuple[bytes | None, dict | None]:
    """gemini-2.5-flash-image 호출 → (이미지 bytes, params dict). 실패 시 (None, None)."""
    try:
        resp = client.models.generate_content(
            model=IMAGE_GEN_MODEL,
            contents=[
                gtypes.Part.from_bytes(data=base64.b64decode(base_b64), mime_type="image/png"),
                gtypes.Part.from_text(text=prompt),
            ],
            config=gtypes.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        img_bytes, text_parts = None, []
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                raw = part.inline_data.data
                img_bytes = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
            elif part.text:
                text_parts.append(part.text)
        params = _parse_params(" ".join(text_parts)) if text_parts else None
        return img_bytes, params
    except Exception as e:
        print(f"    image_gen 오류: {e}")
        return None, None

def _call_imagen_fallback(prompt: str) -> bytes:
    """Imagen 텍스트 전용 폴백."""
    resp = client.models.generate_images(
        model=IMAGEN_MODEL,
        prompt=prompt,
        config=gtypes.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
    )
    raw = resp.generated_images[0].image.image_bytes
    return base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)

def _prompt_hash(dna: dict, colors: dict, kf: dict) -> str:
    """프롬프트 구성 요소의 해시. 프롬프트 변경 시 캐시 무효화."""
    key = json.dumps({"dna_shape": dna.get("body_shape",""),
                      "colors": colors,
                      "desc": kf["desc"]}, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:8]


_PARAMS_REQUEST = (
    '\n\nAfter the image, output ONLY this JSON (no markdown, no extra text):\n'
    '{"hold_ms": <100-400>, "dy": <-30 to 30, negative=up>, '
    '"dx": <-10 to 10>, "shake_x": <0 or 3-8>}\n\n'
    'Guidelines:\n'
    '- hold_ms: 300-400 for key emotion moments (peak/wipe), 100-150 for transition frames\n'
    '- dy: negative for airborne frames (in air), positive for crouching (going down), 0 for ground contact\n'
    '- shake_x: non-zero ONLY for vibrating actions (wiping tears, shaking head); typical 4-6'
)

def generate_keyframes(emotion: str, dna: dict, base_path: Path, colors: dict) -> list[tuple[Path, dict]]:
    """키프레임 이미지 + animation params 동시 생성.
    반환: [(path, params), ...] — Stage 4가 하드코딩 없이 직접 소비.
    """
    print(f"\n[Stage 3] '{emotion}' 키프레임 생성 중...")
    base_b64 = base64.b64encode(base_path.read_bytes()).decode()
    kfs = EMOTION_KEYFRAMES[emotion]
    kf_data = []

    for i, kf in enumerate(kfs):
        out         = OUTPUT_DIR / f"{emotion}_kf{i+1}_{kf['label']}.png"
        hash_file   = OUTPUT_DIR / f"{emotion}_kf{i+1}_{kf['label']}.hash"
        params_file = OUTPUT_DIR / f"{emotion}_kf{i+1}_{kf['label']}.params.json"
        current_hash = _prompt_hash(dna, colors, kf)

        # 캐시: PNG + 해시 + params 세 파일 모두 존재해야 히트
        if (out.exists() and hash_file.exists()
                and hash_file.read_text().strip() == current_hash
                and params_file.exists()):
            params = json.loads(params_file.read_text())
            print(f"  [{i+1}/{len(kfs)}] {kf['label']}: 캐시 사용  params={params}")
            kf_data.append((out, params))
            continue

        print(f"  [{i+1}/{len(kfs)}] {kf['label']}: {kf['desc'][:60]}...")

        color_lock = (
            f"STRICT COLOR LOCK — use EXACTLY these colors, do not change them: "
            f"body color {colors.get('body','#F5F0E8')}, "
            f"outline color {colors.get('outline','#2A2A2A')}, "
            f"background pure white {colors.get('background','#FFFFFF')}. "
            + (f"ear inner {colors['ear_inner']}, " if colors.get('ear_inner') else "")
            + (f"cheek {colors['cheek']}. " if colors.get('cheek') else "")
        )
        prompt = (
            f"Draw the EXACT SAME character as in the reference image. "
            f"Character identity: {dna['body_shape']}, {dna['head_features']}, "
            f"unique details: {dna.get('unique_details', 'small curly tail')}. "
            f"{color_lock}"
            f"ONLY change the pose/expression to: {kf['desc']}. "
            f"Keep ALL proportions, outline thickness, and art style identical to the reference. "
            f"KakaoTalk sticker style: thick outlines, flat colors, pure flat white background, "
            f"no shadow, no drop shadow, centered, square composition. No text, no background elements."
            f"{_PARAMS_REQUEST}"
        )

        img_bytes, params = _call_image_gen_with_params(base_b64, prompt)

        if img_bytes is None:
            print(f"    ⚠ 폴백 → Imagen (params는 레이블 규칙 사용)")
            fallback_prompt = (
                f"{dna['base_prompt']} Action: {kf['desc']}. "
                f"Body color {colors.get('body','#F5F0E8')}, outline {colors.get('outline','#2A2A2A')}, "
                "KakaoTalk sticker, thick outlines, flat colors, white background, no text."
            )
            img_bytes = _call_imagen_fallback(fallback_prompt)
            params = _LABEL_RULES.get(kf["label"], PARAMS_FALLBACK.copy())
        elif params is None:
            print(f"    ⚠ params 파싱 실패 → 레이블 규칙 사용")
            params = _LABEL_RULES.get(kf["label"], PARAMS_FALLBACK.copy())

        print(f"    params: {params}")
        out.write_bytes(img_bytes)
        hash_file.write_text(current_hash)
        params_file.write_text(json.dumps(params, ensure_ascii=False))
        print(f"    저장: {out.name}")
        kf_data.append((out, params))

        if i < len(kfs) - 1:
            time.sleep(1.5)

    return kf_data


# ═════════════════════════════════════════════════════════════════════════════
# STAGE 4: 키프레임 → GIF (shift 보간 — blend 잔상 없음)
# ═════════════════════════════════════════════════════════════════════════════
SIZE = 360
FPS  = 10  # 100ms/frame
FONT_PATH = Path.home() / ".fonts" / "NanumPenScript.ttf"

# 감정별 텍스트 오버레이 설정
EMOTION_TEXT: dict[str, dict] = {
    "joy": {
        "text": "야호!",
        "color": (255, 110, 0),   # 주황
        "size":  54,
        "rotation": -8,
        "anchor": "bottom_right",  # 우측 하단
    },
    "sadness": {
        "text": "흑흑...",
        "color": (55, 115, 200),  # 파랑
        "size":  46,
        "rotation": 5,
        "anchor": "bottom_center",
    },
    "surprise": {
        "text": "헉!",
        "color": (210, 30, 30),   # 빨강
        "size":  64,
        "rotation": -12,
        "anchor": "bottom_right",
    },
}

BASE_CHAR_BBOX: tuple | None = None  # (top, bottom, left, right)

def _get_char_bbox(arr: np.ndarray, threshold: int = 230) -> tuple[int,int,int,int]:
    """흰 배경 제외 바운딩 박스 반환."""
    mask = ~((arr[:,:,0] > threshold) & (arr[:,:,1] > threshold) & (arr[:,:,2] > threshold))
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any():
        return (0, arr.shape[0], 0, arr.shape[1])
    return (int(np.where(rows)[0][0]), int(np.where(rows)[0][-1]),
            int(np.where(cols)[0][0]), int(np.where(cols)[0][-1]))

def _remove_shadow(img_rgb: Image.Image, threshold: int = 210) -> Image.Image:
    """배경 그림자 픽셀을 흰색으로 교체 (외곽 오염 제거)."""
    arr = np.array(img_rgb)
    # 세 채널이 모두 threshold 이상인 픽셀을 흰색으로
    mask = (arr[:,:,0] >= threshold) & (arr[:,:,1] >= threshold) & (arr[:,:,2] >= threshold)
    arr[mask] = [255, 255, 255]
    return Image.fromarray(arr)

def _load_kf(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    arr = np.array(img.convert("RGB"))
    top, bottom, left, right = _get_char_bbox(arr)
    char_h = max(bottom - top, 1)
    char_w = max(right - left, 1)

    target_h = int(SIZE * 0.78)   # 360px 기준 약 280px 높이 고정
    scale = target_h / char_h
    new_h = int(char_h * scale)
    new_w = int(char_w * scale)

    cropped = img.crop((left, top, right, bottom))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    paste_x = (SIZE - new_w) // 2
    paste_y = (SIZE - new_h) // 2 + int(SIZE * 0.04)
    alpha = resized.convert("RGBA").split()[3]
    char_rgb = _remove_shadow(resized.convert("RGB"), threshold=200)
    canvas.paste(char_rgb, (paste_x, paste_y), mask=alpha)

    # 캐릭터 발 아래 바닥 그림자 제거: 캐릭터 하단 + 여백 영역을 강제 화이트
    char_bottom = paste_y + new_h
    if char_bottom < SIZE:
        canvas_arr = np.array(canvas)
        canvas_arr[char_bottom:, :] = 255
        canvas = Image.fromarray(canvas_arr)

    return canvas

def _draw_emotion_text(canvas: Image.Image, cfg: dict) -> Image.Image:
    """손글씨체 감정 텍스트를 캔버스 하단에 오버레이."""
    from PIL import ImageDraw, ImageFont
    font = ImageFont.truetype(str(FONT_PATH), cfg["size"])
    text, color, rotation, anchor = cfg["text"], cfg["color"], cfg["rotation"], cfg["anchor"]

    # 텍스트 크기 측정
    tmp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = tmp_draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]

    # 텍스트 → RGBA 레이어 (흰 외곽선 + 본색)
    pad = 12
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for ox, oy in [(-3,0),(3,0),(0,-3),(0,3),(-2,-2),(2,-2),(-2,2),(2,2)]:
        d.text((pad + ox, pad + oy), text, font=font, fill=(255, 255, 255, 200))
    d.text((pad, pad), text, font=font, fill=(*color, 255))

    rotated = layer.rotate(rotation, expand=True, resample=Image.BICUBIC)
    rw, rh = rotated.size

    # 앵커 위치 계산 (캐릭터 영역 아래 ~40px 여백)
    margin = 12
    if anchor == "bottom_right":
        x, y = SIZE - rw - margin, SIZE - rh - margin
    elif anchor == "bottom_center":
        x, y = (SIZE - rw) // 2, SIZE - rh - margin
    else:  # bottom_left
        x, y = margin, SIZE - rh - margin

    result = canvas.convert("RGBA")
    result.paste(rotated, (x, y), rotated)
    return result.convert("RGB")


def _shift_canvas(img: Image.Image, dy: int, dx: int = 0) -> Image.Image:
    """캐릭터를 dy(아래+/위-), dx(오른쪽+/왼쪽-) 픽셀 이동. 빈 영역 흰색."""
    if dy == 0 and dx == 0:
        return img
    arr = np.array(img)
    h, w = arr.shape[:2]
    result = np.full_like(arr, 255)
    if dy > 0:
        result[dy:, :] = arr[:h - dy, :]
    elif dy < 0:
        result[:h + dy, :] = arr[-dy:, :]
    else:
        result[:] = arr
    if dx != 0:
        tmp = result.copy()
        result = np.full_like(arr, 255)
        if dx > 0:
            result[:, dx:] = tmp[:, :w - dx]
        else:
            result[:, :w + dx] = tmp[:, -dx:]
    return Image.fromarray(result)


def animate_from_keyframes(emotion: str, kf_data: list[tuple[Path, dict]]) -> Path:
    """
    kf_data: [(path, params), ...]
    params keys: hold_ms, dy, dx, shake_x — AI가 생성한 값을 그대로 사용.
    하드코딩된 hold_frames / shift_offsets / shake_holds 없음.
    """
    print(f"\n[Stage 4] '{emotion}' GIF 생성 중...")
    kf_images = [_load_kf(p) for p, _ in kf_data]
    n = len(kf_images)
    frame_ms = 1000 // FPS

    frames_out: list[Image.Image] = []
    durations_out: list[int] = []

    for i in range(n):
        kf_cur    = kf_images[i]
        params    = kf_data[i][1]
        p_next    = kf_data[(i + 1) % n][1]

        hold_count = max(1, params["hold_ms"] // frame_ms)
        dy_cur, dx_cur = params["dy"], params["dx"]
        dy_nxt, dx_nxt = p_next["dy"],  p_next["dx"]
        shake_amp = params["shake_x"]

        text_cfg = EMOTION_TEXT.get(emotion)

        # 홀드: AI가 지정한 hold_ms 만큼, shake_x 적용
        for k in range(hold_count):
            if shake_amp and k % 2 == 1:
                sign = -1 if (k % 4) < 2 else 1
                frame = _shift_canvas(kf_cur, dy_cur, dx_cur + shake_amp * sign)
            else:
                frame = _shift_canvas(kf_cur, dy_cur, dx_cur)
            if text_cfg:
                frame = _draw_emotion_text(frame, text_cfg)
            frames_out.append(frame)
            durations_out.append(frame_ms)

        # 전환: 1프레임 shift 보간 (blend 없음 → 잔상 없음)
        dy_t = (dy_cur + dy_nxt) // 2
        dx_t = (dx_cur + dx_nxt) // 2
        trans_frame = _shift_canvas(kf_cur, dy_t, dx_t)
        if text_cfg:
            trans_frame = _draw_emotion_text(trans_frame, text_cfg)
        frames_out.append(trans_frame)
        durations_out.append(frame_ms)

    out = OUTPUT_DIR / f"{emotion}.gif"
    pil_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames_out]
    pil_frames[0].save(
        out,
        save_all=True,
        append_images=pil_frames[1:],
        loop=0,
        duration=durations_out,
        optimize=False,
    )
    size_kb = out.stat().st_size / 1024
    total_s = sum(durations_out) / 1000
    print(f"  ✓ {out.name}  {size_kb:.0f}KB  {len(frames_out)}프레임  {total_s:.1f}초")
    return out


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 52)
    print("  카카오톡 이모지 POC  (키프레임 액션 버전)")
    print("=" * 52)

    CACHE_FILE = OUTPUT_DIR / "pipeline_cache.json"
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

    # Stage 1
    if "dna" in cache:
        print("\n[Stage 1] 캐시 사용 — 스케치 분석 스킵")
        dna = cache["dna"]
    else:
        dna = analyze_sketch()
        cache["dna"] = dna
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

    # Stage 2
    base_path = OUTPUT_DIR / "base_character.png"
    if "colors" in cache and base_path.exists():
        print("\n[Stage 2] 캐시 사용 — 베이스 캐릭터 생성 스킵")
        colors = cache["colors"]
    else:
        base_path, colors = generate_base_character(dna)
        cache["colors"] = colors
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

    BASE_CHAR_BBOX = _get_char_bbox(np.array(Image.open(base_path).convert("RGB")))
    print(f"  베이스 bbox: {BASE_CHAR_BBOX}")

    # ── 기쁨 ────────────────────────────────────────────────────────────────
    joy_kf_data = generate_keyframes("joy", dna, base_path, colors)
    animate_from_keyframes("joy", joy_kf_data)

    # ── 슬픔 ────────────────────────────────────────────────────────────────
    sad_kf_data = generate_keyframes("sadness", dna, base_path, colors)
    animate_from_keyframes("sadness", sad_kf_data)

    # ── 놀람 ────────────────────────────────────────────────────────────────
    surprise_kf_data = generate_keyframes("surprise", dna, base_path, colors)
    animate_from_keyframes("surprise", surprise_kf_data)

    print("\n" + "=" * 52)
    print("  완료! poc/output/ 에서 결과 확인")
    print("  base_character.png")
    print("  joy_kf1~4.png  /  sadness_kf1~4.png  — 키프레임")
    print("  joy.gif  /  sadness.gif  — 애니메이션")
    print("=" * 52)
