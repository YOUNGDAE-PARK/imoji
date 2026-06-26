#!/usr/bin/env python3
"""
POC: KakaoTalk Emoji Generator
스케치 → 베이스 캐릭터 → 기쁨/슬픔 애니메이션 GIF

실행: .venv/bin/python poc/run.py
"""

import sys, os, math, json, base64, time, hashlib
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
}

def _call_image_gen(base_b64: str, prompt: str) -> bytes | None:
    """gemini-2.5-flash-image 호출, 이미지 bytes 반환. 실패시 None."""
    try:
        resp = client.models.generate_content(
            model=IMAGE_GEN_MODEL,
            contents=[
                gtypes.Part.from_bytes(data=base64.b64decode(base_b64), mime_type="image/png"),
                gtypes.Part.from_text(text=prompt),
            ],
            config=gtypes.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        for part in resp.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                raw = part.inline_data.data
                return base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
    except Exception as e:
        print(f"    image_gen 오류: {e}")
    return None

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


def generate_keyframes(emotion: str, dna: dict, base_path: Path, colors: dict) -> list[Path]:
    """4개 키프레임 이미지 생성. 각각 구체적인 액션 순간."""
    print(f"\n[Stage 3] '{emotion}' 키프레임 4장 생성 중...")
    base_b64 = base64.b64encode(base_path.read_bytes()).decode()
    kfs = EMOTION_KEYFRAMES[emotion]
    paths = []

    for i, kf in enumerate(kfs):
        out = OUTPUT_DIR / f"{emotion}_kf{i+1}_{kf['label']}.png"
        hash_file = OUTPUT_DIR / f"{emotion}_kf{i+1}_{kf['label']}.hash"
        current_hash = _prompt_hash(dna, colors, kf)

        # 캐시: 파일 존재 + 해시 일치 시 스킵 (프롬프트 변경 시 무효화)
        if out.exists() and hash_file.exists() and hash_file.read_text().strip() == current_hash:
            print(f"  [{i+1}/{len(kfs)}] {kf['label']}: 캐시 사용")
            paths.append(out)
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
            f"Character identity: {dna['body_shape']}, {dna['head_features']}, unique details: {dna.get('unique_details', 'small curly tail')}. "
            f"{color_lock}"
            f"ONLY change the pose/expression to: {kf['desc']}. "
            f"Keep ALL proportions, outline thickness, and art style identical to the reference. "
            f"KakaoTalk sticker style: thick outlines, flat colors, pure flat white background, "
            f"no shadow, no drop shadow, centered, square composition. No text, no background elements."
        )

        img_bytes = _call_image_gen(base_b64, prompt)

        if img_bytes is None:
            print(f"    ⚠ 폴백 → Imagen")
            # 폴백: base_prompt + 키프레임 동작 설명
            fallback_prompt = (
                f"{dna['base_prompt']} Action: {kf['desc']}. "
                f"Body color {colors.get('body','#F5F0E8')}, outline {colors.get('outline','#2A2A2A')}, "
                "KakaoTalk sticker, thick outlines, flat colors, white background, no text."
            )
            img_bytes = _call_imagen_fallback(fallback_prompt)

        out.write_bytes(img_bytes)
        hash_file.write_text(current_hash)
        print(f"    저장: {out.name}")
        paths.append(out)

        # Gemini rate limit 방지
        if i < len(kfs) - 1:
            time.sleep(1.5)

    return paths


# ═════════════════════════════════════════════════════════════════════════════
# STAGE 4: 키프레임 보간 → GIF (PIL blend + easing)
# 4개 키프레임을 부드럽게 이어붙여 실제 액션 애니메이션 생성
# ═════════════════════════════════════════════════════════════════════════════
SIZE = 360
FPS  = 12

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

def animate_from_keyframes(
    emotion: str,
    kf_paths: list[Path],
    hold_frames: list[int],
    transition_frames: list[int],
) -> Path:
    """PIL 직접 저장 — per-frame duration 정확 제어, 잔상 없는 컷."""
    print(f"\n[Stage 4] '{emotion}' GIF 생성 중...")
    kf_images = [_load_kf(p) for p in kf_paths]
    n = len(kf_images)
    frame_ms = 1000 // FPS  # 83ms

    frames_out: list[Image.Image] = []
    durations_out: list[int] = []

    for i in range(n):
        kf_cur  = kf_images[i]
        kf_next = kf_images[(i + 1) % n]
        hold  = hold_frames[i % len(hold_frames)]
        trans = transition_frames[i % len(transition_frames)]

        # 홀드: 1장 + 긴 duration (파일 크기 절약)
        frames_out.append(kf_cur.copy())
        durations_out.append(hold * frame_ms)

        # 전환: trans=0 → 즉시 컷, trans≥1 → blend 삽입
        if trans > 0:
            for j in range(trans):
                alpha = (j + 1) / (trans + 1)
                frames_out.append(Image.blend(kf_cur, kf_next, alpha))
                durations_out.append(frame_ms)

    out = OUTPUT_DIR / f"{emotion}.gif"
    pil_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames_out]
    pil_frames[0].save(
        out,
        save_all=True,
        append_images=pil_frames[1:],
        loop=0,
        duration=durations_out,
        optimize=True,
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
    joy_kfs = generate_keyframes("joy", dna, base_path, colors)
    animate_from_keyframes(
        emotion    = "joy",
        kf_paths   = joy_kfs,
        # ready:2, squat:2, leap:2, peak:4(정점 강조), descend:2, land:3
        hold_frames       = [2, 2, 2, 4, 2, 3],
        # 점프 구간은 즉시 컷(0), 시작/끝은 1프레임 컷
        transition_frames = [1, 0, 1, 1, 0, 1],
    )

    # ── 슬픔 ────────────────────────────────────────────────────────────────
    sad_kfs = generate_keyframes("sadness", dna, base_path, colors)
    animate_from_keyframes(
        emotion    = "sadness",
        kf_paths   = sad_kfs,
        # neutral:3, cry_start:2, arm_raise:2, wipe:5(동작 강조), arm_lower:2, slump:4
        hold_frames       = [3, 2, 2, 5, 2, 4],
        # 눈물 닦는 동작은 1프레임 전환, 나머지도 최소
        transition_frames = [1, 1, 1, 1, 1, 1],
    )

    print("\n" + "=" * 52)
    print("  완료! poc/output/ 에서 결과 확인")
    print("  base_character.png")
    print("  joy_kf1~4.png  /  sadness_kf1~4.png  — 키프레임")
    print("  joy.gif  /  sadness.gif  — 애니메이션")
    print("=" * 52)
