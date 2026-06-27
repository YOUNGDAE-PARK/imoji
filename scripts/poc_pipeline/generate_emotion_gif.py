#!/usr/bin/env python3
"""
웹서비스 POC 파이프라인 - 단일 상황 GIF 생성기

Usage:
  .venv/bin/python scripts/poc_pipeline/generate_emotion_gif.py \
    --base_char storage/jobs/xxx/base_character.png \
    --animation_prompt "hand waving side to side" \
    --situation_id hello \
    --text "안뇽!" \
    --text_color "#FF6E00" \
    --text_rotation -8 \
    --text_anchor bottom_right \
    --text_size 48 \
    --colors_json '{"body":"#F5F0E8","outline":"#2A2A2A","background":"#FFFFFF"}' \
    --output storage/jobs/xxx/final/emoticon_01_hello.gif \
    --work_dir storage/jobs/xxx/tmp/hello
"""

import argparse, base64, hashlib, json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent

# .env.local 로드 (Node.js 프로세스가 이미 env를 상속하므로 setdefault 사용)
env_file = ROOT / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types as gtypes

API_KEY         = os.environ["GEMINI_API_KEY"]
VISION_MODEL    = os.environ.get("VISION_MODEL", "gemini-2.5-flash")
IMAGE_GEN_MODEL = os.environ.get("IMAGE_GEN_MODEL", "gemini-2.5-flash-image")
SIZE = 360
FPS  = 10
FONT_PATH = Path.home() / ".fonts" / "NanumPenScript.ttf"

client = genai.Client(api_key=API_KEY)

PARAMS_FALLBACK = {"hold_ms": 150, "dy": 0, "dx": 0, "shake_x": 0}

_PARAMS_REQUEST = (
    '\n\nAfter the image, output ONLY this JSON (no markdown, no extra text):\n'
    '{"hold_ms": <100-400>, "dy": <-30 to 30, negative=up>, "dx": <-10 to 10>, "shake_x": <0 or 3-8>}\n'
    'Guidelines:\n'
    '- hold_ms: 300-400 for peak/climax moments, 100-150 for transitions\n'
    '- dy: negative if character is airborne, positive if crouching, 0 if on ground\n'
    '- shake_x: non-zero ONLY for vibrating/shaking actions (wiping, trembling); typical 4-6'
)


# ─── 파라미터 파싱 ─────────────────────────────────────────────────────────────

def _parse_params(text: str) -> dict:
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
        except Exception:
            pass
    return PARAMS_FALLBACK.copy()


# motionPreset별 "변하는 부분" / "변하면 안 되는 부분" 가이드
_MOTION_CONSTRAINTS: dict[str, dict] = {
    "shake":  {"changes": "head rotates horizontally (left ↔ right) and facial expression tightens/frowns",
               "frozen":  "arms stay in EXACTLY the same position as the reference — do NOT raise, lower, or extend them. Torso, legs, feet also COMPLETELY FROZEN"},
    "nod":    {"changes": "head tilts forward-down then back up, expression stays consistent",
               "frozen":  "arms stay in EXACTLY the same position as the reference. Torso, legs — COMPLETELY FROZEN, identical to reference"},
    "wave":   {"changes": "ONE arm raises and waves (wrist bends), expression is friendly",
               "frozen":  "other arm, torso, legs, feet — COMPLETELY FROZEN, identical to reference"},
    "bounce": {"changes": "whole body moves vertically (squash on landing, stretch on rise), legs bend/extend",
               "frozen":  "body shape, face proportions, arm style — identical to reference"},
    "jump":   {"changes": "whole body is airborne with legs tucked or extended, arms spread or raised",
               "frozen":  "body shape, face proportions — identical to reference"},
    "pop":    {"changes": "whole body briefly scales up (pop) then returns, expression brightens",
               "frozen":  "art style, body proportions — identical to reference"},
    "bow":    {"changes": "body bends forward at waist, head tilts down respectfully",
               "frozen":  "legs, feet, arm length — identical to reference"},
    "recoil": {"changes": "body leans backward, arms spread wide, eyes widen in shock",
               "frozen":  "body shape, limb count/style — identical to reference"},
    "droop":  {"changes": "body gradually slumps downward, head droops, energy visibly drains",
               "frozen":  "body shape, feature style — identical to reference"},
    "plead":  {"changes": "hands/arms clasp together or reach forward, eyes get big and pleading",
               "frozen":  "legs, feet, body shape — identical to reference"},
    "stop":   {"changes": "one hand extends forward flat (palm out stop gesture), expression is firm",
               "frozen":  "other arm, legs, torso shape — identical to reference"},
    "rush":   {"changes": "body leans forward, legs in running stride, arms swing",
               "frozen":  "body shape, head proportions — identical to reference"},
    "march":  {"changes": "legs alternate in marching step, arms swing rhythmically",
               "frozen":  "body shape, head proportions — identical to reference"},
    "stretch":{"changes": "arms reach upward or outward, body elongates slightly, yawning expression",
               "frozen":  "leg shape, body width — identical to reference"},
    "swing": {
        "changes": "the racket-holding arm (right arm) swings in a full arc from backswing through contact, weight shifts toward the swing direction",
        "frozen":  "non-swinging arm, legs, feet, head position, racket grip style — COMPLETELY FROZEN, identical to reference. Racket must remain in right hand.",
    },
    "serve": {
        "changes": "toss arm (left) rises then falls, serving arm (right, with racket) arcs from backswing overhead through contact point, body weight shifts forward",
        "frozen":  "legs, waist angle, non-serving arm symmetry after toss — COMPLETELY FROZEN. Racket must remain in right hand throughout.",
    },
    "volley_stop": {
        "changes": "short punching motion of the racket-holding arm (right), body tilts slightly forward toward net, firm decisive expression",
        "frozen":  "non-volley arm, legs, head — COMPLETELY FROZEN, identical to reference. Racket must remain in right hand.",
    },
}

_DEFAULT_CONSTRAINT = {
    "changes": "pose and expression change as described",
    "frozen":  "body proportions, limb count, art style — identical to reference",
}


# preset당 3가지 variant (job_id로 선택 → 매 생성마다 다른 표현)
# 각 variant는 같은 motion 구조지만 표정·디테일·강도가 다름
_PRESET_VARIANTS: dict[str, list[list[dict]]] = {
    "shake": [
        [   # v0: 단호한 거절
            {"label": "center",     "desc": "face forward, neutral expression, arms unchanged"},
            {"label": "turn_left",  "desc": "head rotated ~20 deg to character's LEFT, furrowed brow, tight-lipped frown, arms unchanged"},
            {"label": "turn_right", "desc": "head rotated ~25 deg to character's RIGHT, firm glare, arms unchanged"},
            {"label": "return",     "desc": "head back to center, residual frown, arms unchanged"},
        ],
        [   # v1: 눈 질끈 감고 세게 젓기
            {"label": "center",     "desc": "face forward, closed eyes, calm expression, arms unchanged"},
            {"label": "turn_left",  "desc": "head rotated ~30 deg LEFT, eyes squeezed shut, cheeks puffed in refusal, arms unchanged"},
            {"label": "turn_right", "desc": "head rotated ~30 deg RIGHT, eyes still shut tight, emphatic refusal expression, arms unchanged"},
            {"label": "return",     "desc": "head center, one eye opens, still slightly disapproving, arms unchanged"},
        ],
        [   # v2: 시크한 곁눈질 거절
            {"label": "center",     "desc": "face forward, cool indifferent expression, arms unchanged"},
            {"label": "turn_left",  "desc": "head rotated LEFT ~20 deg, side-eye glance, unimpressed smirk, arms unchanged"},
            {"label": "turn_right", "desc": "head rotated RIGHT ~20 deg, side-eye the other way, eyebrow raised skeptically, arms unchanged"},
            {"label": "return",     "desc": "head center, dismissive look, arms unchanged"},
        ],
    ],
    "nod": [
        [   # v0: 씩씩한 OK
            {"label": "center",     "desc": "face forward, confident expression, arms unchanged"},
            {"label": "down",       "desc": "head tilts down ~20 deg, bright agreeable eyes"},
            {"label": "down_peak",  "desc": "head at deepest nod, big approving smile, eyes curved happily"},
            {"label": "return",     "desc": "head back to center, satisfied nod expression"},
        ],
        [   # v1: 진지한 동의
            {"label": "center",     "desc": "face forward, serious attentive expression, arms unchanged"},
            {"label": "down",       "desc": "head tilts down ~25 deg slowly, earnest expression"},
            {"label": "down_peak",  "desc": "head at deepest point, eyes closed in firm agreement, respectful expression"},
            {"label": "return",     "desc": "head back to center, calm assured look"},
        ],
        [   # v2: 귀여운 빠른 끄덕
            {"label": "center",     "desc": "face forward, eager happy expression, arms unchanged"},
            {"label": "down",       "desc": "head tilts down quickly ~15 deg, sparkle eyes, big grin"},
            {"label": "down_peak",  "desc": "head at lowest, cheeks rosy, enthusiastic smile, tongue slightly out"},
            {"label": "return",     "desc": "head back to center, excited pleased look"},
        ],
    ],
    "wave": [
        [   # v0: 반가운 인사
            {"label": "rest",       "desc": "neutral, both arms relaxed at sides"},
            {"label": "raise",      "desc": "right arm raised to shoulder height, hand open, bright smile"},
            {"label": "wave_peak",  "desc": "right arm at full height, wrist bent waving sideways, big cheerful smile"},
            {"label": "lower",      "desc": "arm lowering, warm happy expression"},
        ],
        [   # v1: 신난 양손 흔들기
            {"label": "rest",       "desc": "neutral, both arms relaxed at sides"},
            {"label": "raise",      "desc": "both arms start to raise, excited expression building"},
            {"label": "wave_peak",  "desc": "both arms raised high waving enthusiastically, eyes curved in joy, big open smile"},
            {"label": "lower",      "desc": "arms lowering, glowing happy face"},
        ],
        [   # v2: 수줍은 살짝 인사
            {"label": "rest",       "desc": "neutral, shy slight smile, arms at sides"},
            {"label": "raise",      "desc": "one arm raised just to chest height, small tentative wave, shy expression"},
            {"label": "wave_peak",  "desc": "arm at shoulder height, small wrist wave, blushing cheeks, eyes slightly averted"},
            {"label": "lower",      "desc": "arm lowering, relieved soft smile"},
        ],
    ],
    "bow": [
        [   # v0: 정중한 인사
            {"label": "upright",    "desc": "standing upright, polite neutral expression"},
            {"label": "bow_start",  "desc": "body bending forward ~15 deg at waist, respectful expression"},
            {"label": "bow_deep",   "desc": "body bent ~35 deg, head looking at floor, sincere bow"},
            {"label": "return",     "desc": "returning upright, warm appreciative smile"},
        ],
        [   # v1: 과장된 큰절
            {"label": "upright",    "desc": "standing upright, slightly formal expression"},
            {"label": "bow_start",  "desc": "body bending forward dramatically ~25 deg, exaggerated respectful eyes"},
            {"label": "bow_deep",   "desc": "body bent ~50 deg very deep bow, eyes squeezed shut in sincerity"},
            {"label": "return",     "desc": "returning upright slowly, embarrassed but sincere smile"},
        ],
        [   # v2: 귀여운 고개 숙임
            {"label": "upright",    "desc": "upright, bright cheerful expression"},
            {"label": "bow_start",  "desc": "body tilting gently forward ~10 deg, cute shy expression"},
            {"label": "bow_deep",   "desc": "body at ~20 deg lean, head bowed, rosy cheeks, little happy expression"},
            {"label": "return",     "desc": "returning upright, playful cute smile"},
        ],
    ],
    "pop": [
        [   # v0: 사랑스러운 팝
            {"label": "normal",     "desc": "normal size, calm warm expression"},
            {"label": "squish",     "desc": "body slightly wider and shorter (squish), anticipation expression"},
            {"label": "pop_peak",   "desc": "body puffed up larger, bright heart-eyes, rosy cheeks, happy pop"},
            {"label": "return",     "desc": "body back to normal, lingering warm smile"},
        ],
        [   # v1: 에너지 폭발 팝
            {"label": "normal",     "desc": "normal size, contained excited expression"},
            {"label": "squish",     "desc": "body squished flat briefly, coiled energy expression"},
            {"label": "pop_peak",   "desc": "body popped large, star sparkle eyes, huge grin, energy radiating"},
            {"label": "return",     "desc": "body returns to normal, satisfied energetic expression"},
        ],
        [   # v2: 깜짝 팝
            {"label": "normal",     "desc": "normal size, calm neutral expression"},
            {"label": "squish",     "desc": "body squished, eyes going wide as something surprises them"},
            {"label": "pop_peak",   "desc": "body popped big with surprise, O-shaped mouth, wide eyes, cheeks pink"},
            {"label": "return",     "desc": "body returns, flustered delighted expression"},
        ],
    ],
    "bounce": [
        [   # v0: 신난 점프
            {"label": "crouch",     "desc": "body crouching slightly, knees bent, big grin building"},
            {"label": "rise",       "desc": "body rising upward, legs extending, happy expression"},
            {"label": "air",        "desc": "feet off ground, peak of bounce, joyful laugh expression"},
            {"label": "land",       "desc": "landing with slight squat, still smiling happily"},
        ],
        [   # v1: 통통 귀여운 점프
            {"label": "crouch",     "desc": "body squatting low cute, eyes curved in anticipation"},
            {"label": "rise",       "desc": "body bouncing up, arms slightly spread for balance, bright smile"},
            {"label": "air",        "desc": "airborne at peak, legs tucked, eyes sparkle, cheeks puffed"},
            {"label": "land",       "desc": "landing softly, beaming with pride"},
        ],
        [   # v2: 신나서 팔딱팔딱
            {"label": "crouch",     "desc": "body crouching, excited expression can't contain itself"},
            {"label": "rise",       "desc": "body springing up energetically, full of energy"},
            {"label": "air",        "desc": "in the air high up, arms spread wide, shouting joyful expression"},
            {"label": "land",       "desc": "landing with thud, satisfied triumphant expression"},
        ],
    ],
    "jump": [
        [   # v0: 힘차게 점프
            {"label": "crouch",     "desc": "crouched low, arms swung back, focused determined expression"},
            {"label": "leap",       "desc": "body launching upward, arms spreading, energetic expression"},
            {"label": "peak",       "desc": "at peak height, arms raised triumphant, huge joyful grin"},
            {"label": "land",       "desc": "landing with bent knees, proud satisfied smile"},
        ],
        [   # v1: 신나서 폴짝
            {"label": "crouch",     "desc": "quick crouch, can't-wait expression, big smile"},
            {"label": "leap",       "desc": "leaping up enthusiastically, arms wide open, eyes sparkling"},
            {"label": "peak",       "desc": "peak of leap, legs tucked up, fist pumping, ecstatic expression"},
            {"label": "land",       "desc": "landing gracefully, elated expression"},
        ],
        [   # v2: 깜짝 점프
            {"label": "crouch",     "desc": "surprised crouch, startled but excited expression"},
            {"label": "leap",       "desc": "springing up with surprise energy, arms flailing outward"},
            {"label": "peak",       "desc": "airborne at peak, shocked-happy expression, O-shaped mouth, arms wide"},
            {"label": "land",       "desc": "landing and laughing at self, bemused happy face"},
        ],
    ],
    "recoil": [
        [   # v0: 깜짝 놀람
            {"label": "neutral",    "desc": "calm neutral expression, normal stance"},
            {"label": "start",      "desc": "body starting to lean back, eyes widening"},
            {"label": "peak",       "desc": "leaning back sharply, wide shocked eyes, mouth open in O, surprise"},
            {"label": "recover",    "desc": "recovering, hand on chest, still wide-eyed"},
        ],
        [   # v1: 과장된 경악
            {"label": "neutral",    "desc": "calm expression, arms at sides"},
            {"label": "start",      "desc": "body jolting backward, eyes going huge"},
            {"label": "peak",       "desc": "extreme lean back, eyes enormous, jaw dropped, sweat drop, hands spread"},
            {"label": "recover",    "desc": "recovering, shaking head in disbelief, still shocked"},
        ],
        [   # v2: 귀여운 깜짝
            {"label": "neutral",    "desc": "soft calm expression, neutral stance"},
            {"label": "start",      "desc": "little hop backward, eyes blinking wide in surprise"},
            {"label": "peak",       "desc": "leaning back cute, star-shaped wide eyes, rosy cheeks, tiny exclamation"},
            {"label": "recover",    "desc": "recovering, bashful surprised smile"},
        ],
    ],
    "droop": [
        [   # v0: 축 처짐
            {"label": "upright",    "desc": "upright posture, neutral slightly tired expression"},
            {"label": "sag",        "desc": "body sagging slightly, head beginning to hang, downturned mouth"},
            {"label": "droop",      "desc": "fully drooped forward, head hanging, sad heavy eyes, low energy"},
            {"label": "stay",       "desc": "held in drooped position, tears forming in eyes"},
        ],
        [   # v1: 울적하게 퍼짐
            {"label": "upright",    "desc": "upright, trying to look okay but eyes sad"},
            {"label": "sag",        "desc": "shoulders sagging noticeably, head drooping, eyes going glassy"},
            {"label": "droop",      "desc": "body slumped low, head hanging heavy, single teardrop, very sad"},
            {"label": "stay",       "desc": "collapsed in sadness, eyes barely open"},
        ],
        [   # v2: 피곤해서 녹아내림
            {"label": "upright",    "desc": "standing but visibly exhausted, half-lidded eyes"},
            {"label": "sag",        "desc": "body melting downward like losing energy, sleepy expression"},
            {"label": "droop",      "desc": "body fully wilted, eyes closed, ZZZ energy, completely drained"},
            {"label": "stay",       "desc": "held in wilted pose, snoring peacefully"},
        ],
    ],
    "plead": [
        [   # v0: 간절하게 부탁
            {"label": "neutral",    "desc": "normal pose, slightly nervous expression"},
            {"label": "reach",      "desc": "arms extending forward, hopeful pleading eyes beginning"},
            {"label": "plead",      "desc": "hands clasped together, enormous pleading eyes, quivering lips"},
            {"label": "hold",       "desc": "held in plead, eyes glistening with hope"},
        ],
        [   # v1: 눈물 글썽 부탁
            {"label": "neutral",    "desc": "normal pose, expression starting to crumble"},
            {"label": "reach",      "desc": "arms reaching forward, eyes welling up slightly"},
            {"label": "plead",      "desc": "hands pressed together, teary sparkling eyes, slight pout"},
            {"label": "hold",       "desc": "trembling pleading pose, tears about to fall"},
        ],
        [   # v2: 귀엽게 조르기
            {"label": "neutral",    "desc": "normal pose, scheming cute expression"},
            {"label": "reach",      "desc": "arms reaching forward cutely, big doe eyes forming"},
            {"label": "plead",      "desc": "wiggling arms, biggest puppy eyes, rosy cheeks, cute pout"},
            {"label": "hold",       "desc": "held in full cute-attack plead pose"},
        ],
    ],
    "stop": [
        [   # v0: 단호한 스탑
            {"label": "neutral",    "desc": "normal pose, arms at sides"},
            {"label": "raise",      "desc": "one arm starting to rise, firm expression forming"},
            {"label": "stop",       "desc": "arm fully extended, palm flat out, firm unwavering expression"},
            {"label": "hold",       "desc": "held in stop, resolute expression"},
        ],
        [   # v1: 강력한 스탑
            {"label": "neutral",    "desc": "normal pose, arms at sides"},
            {"label": "raise",      "desc": "arm shooting up decisively, determined expression"},
            {"label": "stop",       "desc": "arm thrust out powerfully, serious glare, eyebrows furrowed"},
            {"label": "hold",       "desc": "maintained stop, stern authoritative look"},
        ],
        [   # v2: 귀여운 스탑
            {"label": "neutral",    "desc": "normal pose, slightly stern expression"},
            {"label": "raise",      "desc": "arm lifting with determined cute look"},
            {"label": "stop",       "desc": "arm out in stop gesture, cheeks puffed, pouting firm expression"},
            {"label": "hold",       "desc": "held in stop, one eyebrow raised, unimpressed"},
        ],
    ],
    "rush": [
        [   # v0: 식은땀 바쁨
            {"label": "neutral",    "desc": "upright, normal expression"},
            {"label": "lean",       "desc": "body leaning forward with urgency, sweat drop on forehead, arms swinging"},
            {"label": "rush",       "desc": "leaning forward more, arms pumping, sweat flying, frantic stress expression"},
            {"label": "hold",       "desc": "held in rushed lean, multiple sweat drops, overwhelmed face"},
        ],
        [   # v1: 헐레벌떡 뜀
            {"label": "neutral",    "desc": "upright, just realized something urgent"},
            {"label": "lean",       "desc": "suddenly lurching forward, shocked O-mouth, arms starting to pump"},
            {"label": "rush",       "desc": "full sprint lean, tongue out panting, steam from head, legs blurring"},
            {"label": "hold",       "desc": "peak panic run, eyes wide, arms in windmill"},
        ],
        [   # v2: 시계 보며 헐레벌떡
            {"label": "neutral",    "desc": "upright, calm unaware expression"},
            {"label": "lean",       "desc": "body tilting forward, eyes wide after checking time, panic spreading"},
            {"label": "rush",       "desc": "leaning into full rush, one hand raised in oh-no gesture, sweating"},
            {"label": "hold",       "desc": "frozen in panicked rush lean, spiral eyes, sweat everywhere"},
        ],
    ],
    "march": [
        [   # v0: 씩씩하게 출발
            {"label": "neutral",    "desc": "standing upright, determined ready expression"},
            {"label": "step_1",     "desc": "left leg raised mid-step, right arm forward, confident stride"},
            {"label": "step_2",     "desc": "right leg raised mid-step, left arm forward, matching stride"},
            {"label": "return",     "desc": "planted feet, proud accomplished expression"},
        ],
        [   # v1: 힘차게 행진
            {"label": "neutral",    "desc": "upright, pumped-up expression"},
            {"label": "step_1",     "desc": "left leg high-stepping, right arm swinging forward, motivated"},
            {"label": "step_2",     "desc": "right leg high-stepping, left arm forward, energetic march"},
            {"label": "return",     "desc": "standing tall, fist pump expression"},
        ],
        [   # v2: 귀엽게 뒤뚱뒤뚱
            {"label": "neutral",    "desc": "upright, cute cheerful expression"},
            {"label": "step_1",     "desc": "left leg raised cute waddling step, slightly wobbly, big grin"},
            {"label": "step_2",     "desc": "right leg raised matching cute waddle, cheeks rosy, eyes bright"},
            {"label": "return",     "desc": "rocking back to center, delightfully silly proud look"},
        ],
    ],
    "stretch": [
        [   # v0: 졸린 기지개
            {"label": "resting",    "desc": "slightly slouched, heavy sleepy eyes, arms at sides"},
            {"label": "reach_up",   "desc": "both arms reaching up, mouth opening in big yawn"},
            {"label": "full_stretch","desc": "arms fully overhead, body elongated, eyes squeezed shut mid-yawn"},
            {"label": "relax",      "desc": "arms coming down, refreshed but still-sleepy expression"},
        ],
        [   # v1: 개운하게 기지개
            {"label": "resting",    "desc": "slightly slouched, muzzy morning expression"},
            {"label": "reach_up",   "desc": "arms sweeping upward, eyes widening, big breath in"},
            {"label": "full_stretch","desc": "full overhead stretch, eyes closed, huge satisfied grin"},
            {"label": "relax",      "desc": "arms lowering, bright and awake now, cheerful smile"},
        ],
        [   # v2: 온몸 비틀기 기지개
            {"label": "resting",    "desc": "slumped down, groggy sleepy expression"},
            {"label": "reach_up",   "desc": "twisting stretch upward, one arm higher, mouth open wide"},
            {"label": "full_stretch","desc": "arms twisted overhead at angles, body doing a full twisty stretch, sleeping face"},
            {"label": "relax",      "desc": "untwisting and settling, drowsy peaceful expression"},
        ],
    ],
    "swing": [
        [   # v0: 강력한 탑스핀 포핸드
            {"label": "ready",      "desc": "character in ready position, racket held in right hand at waist level, slight forward lean, focused expression"},
            {"label": "backswing",  "desc": "right arm with racket pulled back behind body, low backswing, weight on back foot, eyes tracking ball"},
            {"label": "contact",    "desc": "right arm with racket sweeps forward and upward through contact zone, explosive topspin swing, determined grin"},
            {"label": "follow_thru","desc": "right arm with racket completes high follow-through over left shoulder, triumphant expression, weight on front foot"},
        ],
        [   # v1: 날카로운 슬라이스
            {"label": "ready",      "desc": "character set with racket in right hand at shoulder height, weight balanced, focused face"},
            {"label": "backswing",  "desc": "right arm with racket pulled back high and slightly open, body coiling, sharp eyes"},
            {"label": "contact",    "desc": "right arm swings down and through with open racket face, slicing motion, controlled precise expression"},
            {"label": "follow_thru","desc": "right arm with racket extends low across body in follow-through, satisfied slicing expression"},
        ],
        [   # v2: 귀여운 첫 포핸드 스윙
            {"label": "ready",      "desc": "character in stance with racket in right hand, slightly nervous cute expression, bright eyes"},
            {"label": "backswing",  "desc": "right arm with racket pulled back in exaggerated wide backswing, tongue sticking out in concentration"},
            {"label": "contact",    "desc": "right arm swings racket through awkwardly but enthusiastically, eyes squinted in effort, rosy cheeks"},
            {"label": "follow_thru","desc": "right arm with racket ends in happy wobbly follow-through, proud delighted expression"},
        ],
    ],
    "serve": [
        [   # v0: 힘찬 플랫 서브
            {"label": "toss",       "desc": "left arm rises for ball toss, right arm with racket drops behind back into backswing, body coiling upward"},
            {"label": "cocked",     "desc": "left arm at full toss height, right arm with racket cocked at maximum backswing overhead, weight shifting forward"},
            {"label": "contact",    "desc": "right arm with racket explodes upward through contact point overhead, full extension, power face with big grin"},
            {"label": "follow_thru","desc": "right arm with racket sweeps down to left hip in follow-through, triumphant landing pose"},
        ],
        [   # v1: 킥 서브 (높이 튀김)
            {"label": "toss",       "desc": "left arm lifts ball toss slightly to the left, right arm with racket begins pull back, knees bending"},
            {"label": "cocked",     "desc": "body bowing back in kick-serve arch, right arm with racket cocked high behind head, intense focused look"},
            {"label": "contact",    "desc": "right arm with racket reaches upward at angle brushing the ball with spin, body straightening with pop"},
            {"label": "follow_thru","desc": "right arm with racket completes high follow-through, satisfied spin-serve smile"},
        ],
        [   # v2: 귀여운 언더서브
            {"label": "toss",       "desc": "character tossing ball up with left arm very low, right arm with racket swinging underhand, innocent expression"},
            {"label": "cocked",     "desc": "right arm with racket pulled back at waist, ball dropping to contact height, cute focused face"},
            {"label": "contact",    "desc": "right arm with racket scoops upward hitting ball gently underhand, cheeky grin"},
            {"label": "follow_thru","desc": "right arm with racket finishes in little upward flourish, playful satisfied expression"},
        ],
    ],
    "volley_stop": [
        [   # v0: 단호한 네트 발리
            {"label": "ready",      "desc": "character at net position, racket in right hand raised to chest height, alert crisp expression"},
            {"label": "punch_out",  "desc": "right arm with racket extends forward in short punching motion, body tilts slightly into net, sharp eyes"},
            {"label": "contact",    "desc": "racket face pushes through ball at full extension, decisive crack expression, confident posture"},
            {"label": "return",     "desc": "right arm with racket pulls back to ready position, satisfied net-player expression"},
        ],
        [   # v1: 강력한 발리 펀치
            {"label": "ready",      "desc": "character crouched low at net, racket in right hand forward, aggressive focused expression"},
            {"label": "punch_out",  "desc": "right arm with racket thrusts powerfully forward, whole body drives through, fierce eyes"},
            {"label": "contact",    "desc": "racket jabs through ball with full force, explosive expression, momentum carries body forward"},
            {"label": "return",     "desc": "right arm with racket resets with authority, dominant net presence expression"},
        ],
        [   # v2: 귀여운 터치 발리
            {"label": "ready",      "desc": "character at net, racket in right hand, slightly tippy-toes, eager expression"},
            {"label": "punch_out",  "desc": "right arm with racket reaches forward in cute little punch, tongue slightly out in effort, rosy cheeks"},
            {"label": "contact",    "desc": "gentle tap with racket face, surprised-happy expression at successful volley"},
            {"label": "return",     "desc": "right arm with racket returns, proud little celebration expression"},
        ],
    ],
}


# ─── Step 1: animationPrompt → 4 키프레임 설명 ────────────────────────────────

def generate_keyframes_from_prompt(
    animation_prompt: str,
    motion_preset: str = "",
    char_description: str = "",
    variation_id: str = "",
) -> list[dict]:
    """animationPrompt + motionPreset → 4개 키프레임 변경 설명 생성.
    preset에 variant가 있으면 variation_id로 선택 (매 생성마다 다른 표현).
    """
    if motion_preset in _PRESET_VARIANTS:
        variants = _PRESET_VARIANTS[motion_preset]
        idx = int(hashlib.md5((variation_id or "0").encode()).hexdigest(), 16) % len(variants)
        print(f"  preset variant 선택 ({motion_preset} v{idx}/{len(variants)-1})")
        return variants[idx]

    constraint = _MOTION_CONSTRAINTS.get(motion_preset, _DEFAULT_CONSTRAINT)
    char_line = f"Character: {char_description}\n" if char_description else ""

    prompt = (
        f'You are a KakaoTalk emoji animator.\n'
        f'{char_line}'
        f'Animation: "{animation_prompt}"\n'
        f'Motion type: {motion_preset or "general"}\n\n'
        f'WHAT CHANGES: {constraint["changes"]}\n'
        f'WHAT STAYS FROZEN (DO NOT MENTION IN DESC): {constraint["frozen"]}\n\n'
        f'Generate exactly 4 keyframes. Each "desc" must describe ONLY WHAT CHANGES from the neutral reference.\n'
        f'Output ONLY JSON (no other text):\n'
        f'[\n'
        f'  {{"label": "start",  "desc": "neutral, before motion begins"}},\n'
        f'  {{"label": "action", "desc": "<first peak of the change — be specific about angles/positions>"}},\n'
        f'  {{"label": "peak",   "desc": "<most expressive/extreme moment of the change>"}},\n'
        f'  {{"label": "end",    "desc": "returning to neutral for seamless loop"}}\n'
        f']'
    )
    try:
        resp = client.models.generate_content(
            model=VISION_MODEL,
            contents=[gtypes.Part.from_text(text=prompt)]
        )
        text = resp.text or ""
        m = re.search(r'\[[\s\S]*?\]', text)
        if m:
            kfs = json.loads(m.group())
            if isinstance(kfs, list) and len(kfs) >= 2:
                return kfs[:4]
    except Exception as e:
        print(f"  ⚠ 키프레임 설명 생성 오류: {e}")

    return [
        {"label": "start",  "desc": "neutral standing pose"},
        {"label": "action", "desc": f"mid-action: {animation_prompt[:60]}"},
        {"label": "peak",   "desc": f"peak of action: {animation_prompt[:60]}"},
        {"label": "end",    "desc": "returning to neutral pose"},
    ]


# ─── Step 2: 키프레임 이미지 + params 생성 ────────────────────────────────────

def _prompt_hash(base_mtime: float, kf: dict, variation_id: str = "") -> str:
    key = json.dumps({"mtime": int(base_mtime), "desc": kf["desc"], "vid": variation_id}, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:8]


def generate_keyframe_images(
    base_char_path: Path,
    keyframes: list[dict],
    work_dir: Path,
    colors: dict,
    motion_preset: str = "",
    char_description: str = "",
    variation_id: str = "",
    mode: str = "general",
) -> list[tuple[Path, dict]]:
    """각 키프레임 이미지 + animation params 생성. .hash/.params.json 캐시 활용."""
    base_b64 = base64.b64encode(base_char_path.read_bytes()).decode()
    base_mtime = base_char_path.stat().st_mtime
    kf_data = []

    constraint = _MOTION_CONSTRAINTS.get(motion_preset, _DEFAULT_CONSTRAINT)
    char_line = f"Character: {char_description} " if char_description else ""
    color_lock = (
        f"Colors MUST match reference exactly: "
        f"body {colors.get('body','#F5F0E8')}, "
        f"outline {colors.get('outline','#2A2A2A')}, "
        f"background pure white."
    )
    frozen_rule = (
        f"ABSOLUTELY FROZEN (must be pixel-perfect identical to reference): {constraint['frozen']}. "
        f"Do NOT alter these even slightly."
    )
    tennis_rule = (
        "TENNIS CONSISTENCY: The character MUST hold the tennis racket in the right hand at all times. "
        "Racket must remain visible and properly gripped across ALL frames. "
        "Tennis outfit (polo shirt, shorts/skirt, shoes) must be IDENTICAL across all frames. "
        "Do NOT drop the racket, change the outfit, or remove any tennis equipment."
    ) if mode == "tennis" else ""

    for i, kf in enumerate(keyframes):
        stem      = f"kf{i+1}_{kf['label']}"
        out        = work_dir / f"{stem}.png"
        hash_file  = work_dir / f"{stem}.hash"
        params_file = work_dir / f"{stem}.params.json"
        current_hash = _prompt_hash(base_mtime, kf, variation_id)

        if (out.exists() and hash_file.exists()
                and hash_file.read_text().strip() == current_hash
                and params_file.exists()):
            params = json.loads(params_file.read_text())
            print(f"  [kf{i+1}] {kf['label']}: 캐시 사용  params={params}")
            kf_data.append((out, params))
            continue

        print(f"  [kf{i+1}] {kf['label']}: 생성 중... {kf['desc'][:60]}")
        prompt = (
            f"Redraw the EXACT SAME character from the reference image. "
            f"{char_line}"
            f"{frozen_rule} "
            + (f"{tennis_rule} " if tennis_rule else "")
            + f"ONLY apply this ONE change: {kf['desc']}. "
            f"Everything else must look copy-pasted from the reference — same body width, "
            f"same arm positions, same leg shape, same ear shape, same overall silhouette. "
            f"{color_lock} "
            f"Art style: KakaoTalk sticker — thick outlines, flat colors, pure white background, "
            f"no shadows, centered square. No text, no decorations."
            f"{_PARAMS_REQUEST}"
        )

        img_bytes, params = None, None
        for attempt in range(5):
            try:
                resp = client.models.generate_content(
                    model=IMAGE_GEN_MODEL,
                    contents=[
                        gtypes.Part.from_bytes(data=base64.b64decode(base_b64), mime_type="image/png"),
                        gtypes.Part.from_text(text=prompt),
                    ],
                    config=gtypes.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
                )
                text_parts = []
                for part in resp.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        raw = part.inline_data.data
                        img_bytes = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
                    elif part.text:
                        text_parts.append(part.text)
                if text_parts:
                    params = _parse_params(" ".join(text_parts))
                break
            except Exception as e:
                wait = 15 * (attempt + 1)
                print(f"    오류 (시도 {attempt+1}/5): {e}")
                if attempt < 4:
                    print(f"    {wait}초 후 재시도...")
                    time.sleep(wait)

        if img_bytes is None:
            print(f"    ⚠ 생성 실패, 이전 프레임 재사용")
            img_bytes = kf_data[-1][0].read_bytes() if kf_data else base_char_path.read_bytes()
        if params is None:
            params = PARAMS_FALLBACK.copy()

        out.write_bytes(img_bytes)
        hash_file.write_text(current_hash)
        params_file.write_text(json.dumps(params, ensure_ascii=False))
        print(f"    params: {params}")
        kf_data.append((out, params))

        if i < len(keyframes) - 1:
            time.sleep(1.5)

    return kf_data


# ─── Step 3: 이미지 처리 유틸 ─────────────────────────────────────────────────

def _get_char_bbox(arr: np.ndarray, threshold: int = 230):
    mask = ~((arr[:,:,0] > threshold) & (arr[:,:,1] > threshold) & (arr[:,:,2] > threshold))
    rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
    if not rows.any():
        return (0, arr.shape[0], 0, arr.shape[1])
    return (int(np.where(rows)[0][0]), int(np.where(rows)[0][-1]),
            int(np.where(cols)[0][0]), int(np.where(cols)[0][-1]))

def _remove_shadow(img: Image.Image, threshold: int = 200) -> Image.Image:
    arr = np.array(img)
    mask = (arr[:,:,0] >= threshold) & (arr[:,:,1] >= threshold) & (arr[:,:,2] >= threshold)
    arr[mask] = [255, 255, 255]
    return Image.fromarray(arr)

def _load_kf(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    arr = np.array(img.convert("RGB"))
    top, bottom, left, right = _get_char_bbox(arr)
    char_h, char_w = max(bottom - top, 1), max(right - left, 1)
    target_h = int(SIZE * 0.78)
    scale = target_h / char_h
    new_h, new_w = int(char_h * scale), int(char_w * scale)
    cropped = img.crop((left, top, right, bottom))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    paste_x = (SIZE - new_w) // 2
    paste_y = (SIZE - new_h) // 2 + int(SIZE * 0.04)
    alpha = resized.convert("RGBA").split()[3]
    char_rgb = _remove_shadow(resized.convert("RGB"))
    canvas.paste(char_rgb, (paste_x, paste_y), mask=alpha)
    char_bottom = paste_y + new_h
    if char_bottom < SIZE:
        c = np.array(canvas)
        c[char_bottom:, :] = 255
        canvas = Image.fromarray(c)
    return canvas

def _shift_canvas(img: Image.Image, dy: int, dx: int = 0) -> Image.Image:
    if dy == 0 and dx == 0:
        return img
    arr = np.array(img)
    h, w = arr.shape[:2]
    result = np.full_like(arr, 255)
    if dy > 0:   result[dy:, :]   = arr[:h - dy, :]
    elif dy < 0: result[:h + dy, :] = arr[-dy:, :]
    else:        result[:] = arr
    if dx != 0:
        tmp = result.copy()
        result = np.full_like(arr, 255)
        if dx > 0:   result[:, dx:]   = tmp[:, :w - dx]
        else:        result[:, :w + dx] = tmp[:, -dx:]
    return Image.fromarray(result)

def _draw_text(
    canvas: Image.Image,
    text: str,
    color_hex: str,
    size: int,
    rotation: int,
    anchor: str,
) -> Image.Image:
    if not text or not FONT_PATH.exists():
        return canvas
    color = tuple(int(color_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    font = ImageFont.truetype(str(FONT_PATH), size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = tmp.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad = 12
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for ox, oy in [(-3,0),(3,0),(0,-3),(0,3),(-2,-2),(2,-2),(-2,2),(2,2)]:
        d.text((pad + ox, pad + oy), text, font=font, fill=(255, 255, 255, 200))
    d.text((pad, pad), text, font=font, fill=(*color, 255))
    rotated = layer.rotate(rotation, expand=True, resample=Image.BICUBIC)
    rw, rh = rotated.size
    margin = 12
    if anchor == "bottom_right":   x, y = SIZE - rw - margin, SIZE - rh - margin
    elif anchor == "bottom_center": x, y = (SIZE - rw) // 2,  SIZE - rh - margin
    else:                           x, y = margin,              SIZE - rh - margin
    result = canvas.convert("RGBA")
    result.paste(rotated, (x, y), rotated)
    return result.convert("RGB")


# ─── Step 4: GIF 조립 ─────────────────────────────────────────────────────────

def _save_gif_with_quality(frames_out: list[Image.Image], durations_out: list[int], output_path: Path, colors: int = 256) -> None:
    """전체 프레임 공통 팔레트로 GIF 저장 — 프레임 간 색 깜빡임 방지 + 카카오 256색 스펙."""
    n = len(frames_out)
    step = max(1, n // 8)
    samples = [f.convert("RGB") for f in frames_out[::step]]
    combined = Image.new("RGB", (SIZE * len(samples), SIZE))
    for j, f in enumerate(samples):
        combined.paste(f, (SIZE * j, 0))
    palette_img = combined.quantize(colors=colors, method=0, dither=0)

    pil_frames = [f.convert("RGB").quantize(palette=palette_img, dither=1) for f in frames_out]
    pil_frames[0].save(
        output_path,
        save_all=True,
        append_images=pil_frames[1:],
        loop=0,
        duration=durations_out,
        optimize=False,
    )


def _optimize_gif_size(frames_out: list[Image.Image], durations_out: list[int], output_path: Path, target_kb: int = 300) -> float:
    """300KB 초과 시 색상 수를 단계적으로 줄여 재저장 (카카오 파일 크기 제한 준수)."""
    kb = output_path.stat().st_size / 1024
    if kb <= target_kb:
        return kb
    print(f"  ⚠ {kb:.0f}KB > {target_kb}KB, 자동 최적화 중...")
    for colors in [200, 160, 128, 96]:
        _save_gif_with_quality(frames_out, durations_out, output_path, colors=colors)
        kb = output_path.stat().st_size / 1024
        print(f"    {colors}색 → {kb:.0f}KB")
        if kb <= target_kb:
            break
    return kb


def build_gif(kf_data: list[tuple[Path, dict]], output_path: Path, text_cfg: dict) -> None:
    frame_ms = 1000 // FPS
    kf_images = [_load_kf(p) for p, _ in kf_data]
    n = len(kf_images)
    frames_out: list[Image.Image] = []
    durations_out: list[int] = []

    has_text = bool(text_cfg.get("text"))

    for i in range(n):
        kf_cur = kf_images[i]
        params = kf_data[i][1]
        p_next = kf_data[(i + 1) % n][1]

        hold_count = max(1, params["hold_ms"] // frame_ms)
        dy_cur, dx_cur = params["dy"], params["dx"]
        dy_nxt, dx_nxt = p_next["dy"],  p_next["dx"]
        shake_amp = params["shake_x"]

        for k in range(hold_count):
            if shake_amp and k % 2 == 1:
                sign = -1 if (k % 4) < 2 else 1
                frame = _shift_canvas(kf_cur, dy_cur, dx_cur + shake_amp * sign)
            else:
                frame = _shift_canvas(kf_cur, dy_cur, dx_cur)
            if has_text:
                frame = _draw_text(frame, **text_cfg)
            frames_out.append(frame)
            durations_out.append(frame_ms)

        # 전환: shift 보간 1프레임 (blend 없음)
        dy_t = (dy_cur + dy_nxt) // 2
        dx_t = (dx_cur + dx_nxt) // 2
        trans = _shift_canvas(kf_cur, dy_t, dx_t)
        if has_text:
            trans = _draw_text(trans, **text_cfg)
        frames_out.append(trans)
        durations_out.append(frame_ms)

    # 256색 공통 팔레트 GIF 저장 → 300KB 초과 시 자동 최적화
    _save_gif_with_quality(frames_out, durations_out, output_path, colors=256)
    kb = _optimize_gif_size(frames_out, durations_out, output_path)

    # peak 프레임(index 2) → PNG 썸네일 (카카오 스티콘/제출 패키지용)
    peak_idx = min(2, len(kf_images) - 1)
    peak_img = _shift_canvas(kf_images[peak_idx], 0, 0)
    if has_text:
        peak_img = _draw_text(peak_img, **text_cfg)
    peak_img.convert("RGB").save(str(output_path.with_suffix(".png")))

    total_s = sum(durations_out) / 1000
    print(f"  ✓ {output_path.name}  {kb:.0f}KB  {len(frames_out)}프레임  {total_s:.1f}초")


# ─── 진입점 ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="POC 파이프라인 단일 상황 GIF 생성")
    ap.add_argument("--base_char",       required=True,  help="base_character.png 경로")
    ap.add_argument("--animation_prompt",required=True,  help="애니메이션 설명 (situations.animationPrompt)")
    ap.add_argument("--situation_id",    required=True,  help="상황 ID (파일명용)")
    ap.add_argument("--text",            default="",     help="텍스트 오버레이 내용")
    ap.add_argument("--text_color",      default="#333333")
    ap.add_argument("--text_rotation",   type=int, default=-6)
    ap.add_argument("--text_anchor",     default="bottom_right",
                    choices=["bottom_right","bottom_center","bottom_left"])
    ap.add_argument("--text_size",       type=int, default=48)
    ap.add_argument("--motion_preset",    default="",   help="motionPreset (shake/bounce/wave...)")
    ap.add_argument("--char_description",default="",   help="캐릭터 특징 설명 (프롬프트 일관성용)")
    ap.add_argument("--variation_id",    default="",   help="job_id 등 — variant 선택 + 캐시 구분용")
    ap.add_argument("--colors_json",     default="{}", help="캐릭터 색상 JSON")
    ap.add_argument("--output",          required=True,  help="출력 GIF 경로")
    ap.add_argument("--work_dir",        required=True,  help="임시 파일 저장 디렉토리")
    ap.add_argument("--mode", default="general", help="모드 (general/tennis)")
    args = ap.parse_args()

    base_char = Path(args.base_char)
    work_dir  = Path(args.work_dir)
    output    = Path(args.output)
    work_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    colors = json.loads(args.colors_json) if args.colors_json.strip() != "{}" else {}

    print(f"\n[POC] {args.situation_id}: {args.animation_prompt[:70]}...")

    # 키프레임 설명 (캐시)
    kf_desc_file = work_dir / "keyframes.json"
    if kf_desc_file.exists():
        keyframes = json.loads(kf_desc_file.read_text())
        print(f"  키프레임 설명 캐시 ({len(keyframes)}개): {[k['label'] for k in keyframes]}")
    else:
        print(f"  키프레임 설명 생성 중 (preset={args.motion_preset or 'none'})...")
        keyframes = generate_keyframes_from_prompt(
            args.animation_prompt,
            motion_preset=args.motion_preset,
            char_description=args.char_description,
            variation_id=args.variation_id,
        )
        kf_desc_file.write_text(json.dumps(keyframes, ensure_ascii=False, indent=2))
        print(f"  생성된 키프레임: {[k['label'] for k in keyframes]}")

    # 키프레임 이미지 + params
    kf_data = generate_keyframe_images(
        base_char, keyframes, work_dir, colors,
        motion_preset=args.motion_preset,
        char_description=args.char_description,
        variation_id=args.variation_id,
        mode=args.mode,
    )

    # GIF 조립
    text_cfg = {
        "text":     args.text,
        "color_hex": args.text_color,
        "size":     args.text_size,
        "rotation": args.text_rotation,
        "anchor":   args.text_anchor,
    }
    build_gif(kf_data, output, text_cfg)
    print(f"  완료 → {output}")


if __name__ == "__main__":
    main()
