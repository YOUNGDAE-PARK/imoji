import situationData from "../data/situations.json";

export const STYLE_PRESETS = [
  { id: "soft-sticker", label: "말랑 2D 스티커", prompt: "soft rounded 2D sticker, warm colors, clean readable silhouette" },
  { id: "clean-line", label: "깔끔한 라인 캐릭터", prompt: "clean line character, minimal polished vector-like drawing" },
  { id: "chibi", label: "귀여운 SD/치비", prompt: "cute super-deformed chibi mascot, large expressive face" },
  { id: "watercolor", label: "손그림 수채화", prompt: "hand-drawn watercolor texture, gentle pencil and paint feeling" },
  { id: "clay-toy", label: "클레이/토이 느낌", prompt: "clay toy character look, soft 3D handmade material" },
  { id: "pixel", label: "픽셀 아트 이모티콘", prompt: "pixel art emoticon, crisp low-resolution pixel style, readable at small size" }
] as const;

export type FinalSituation = {
  id: string;
  label: string;
  prompt: string;
  animationPrompt: string;
  motionPreset: string;
  textVariants: string[];
  frames: string[];
};

export const FINAL_SITUATIONS = situationData.situations as FinalSituation[];
export const GIF_FRAME_COUNT = 16;

export const MIN_SELECTED_SITUATIONS = 1;
export const MAX_SELECTED_SITUATIONS = FINAL_SITUATIONS.length;

export const LETTERING_STYLES = [
  {
    id: "minimal-black",
    label: "담백 손글씨",
    prompt:
      "minimal black handwritten Korean lettering, thin marker or pencil-like strokes, sparse and witty placement, sometimes vertical or split around the character, no decorative font"
  },
  {
    id: "cute-color",
    label: "말랑 컬러 손글씨",
    prompt:
      "cute playful Korean handwritten lettering, rounded casual marker strokes, lively placement with small hearts, sparkles, and soft pastel accent marks, never a standard digital font"
  }
] as const;

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
export const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
