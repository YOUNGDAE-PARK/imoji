import { GIF_FRAME_COUNT, STYLE_PRESETS } from "./constants";

type PromptInput = {
  styleId: string;
  situationPrompt: string;
  situationLabel: string;
  situationAnimationPrompt: string;
  situationFrames: string[];
  characterProfile: string;
  letteringStylePrompt: string;
};

export function buildGenerationPrompt({
  styleId,
  situationPrompt,
  situationLabel,
  situationAnimationPrompt,
  situationFrames,
  characterProfile,
  letteringStylePrompt
}: PromptInput) {
  const style = STYLE_PRESETS.find((item) => item.id === styleId) ?? STYLE_PRESETS[0];

  return [
    `KOREAN_LABEL_FOR_MEANING_ONLY: ${situationLabel}`,
    `SITUATION_ACTION: ${situationAnimationPrompt}`,
    `OUTPUT_FORMAT: Exactly 4×4 sprite sheet grid = 16 distinct animation frames in reading order (left-to-right, top-to-bottom)`,
    `TOTAL_ANIMATION_FRAMES: ${GIF_FRAME_COUNT}`,
    "STRICT PIXEL ALIGNMENT: every frame must use the EXACT SAME CANVAS COORDINATES for the character's feet/base and torso",
    "FIXED CHARACTER ANCHOR: the character's core mass must stay mathematically centered and frozen in place across all 16 frames — zero drift, zero scale shift, and zero jitter allowed",
    "KEEP FEET PLANTED: the character's feet and lower body must remain in the exact same position in every single frame",
    "STRICT BOTTOM ANCHOR: the bottom-most part of the character must never shift or wobble; only limbs, head, and facial features should change between frames",
    "SMOOTH LERP MOTION: change only the specific limb or facial feature mentioned in each frame; the rest of the body must remain perfectly static and unchanged",
    "LOOP CONTINUITY: frame 16 must be identical to frame 1 to ensure a seamless cycle",
    ...situationFrames.map((frame, index) => `FRAME_${index + 1}: ${frame}`),
    "based on this exact hand-drawn sketch uploaded by the user as reference image",
    `character identity lock: ${characterProfile}`,
    "preserve the uploaded sketch's outline, proportions, line quality, and unique quirks in all 16 frames",
    "do not redesign, replace, genericize, or invent a different character",
    `art style: ${style.prompt}`,
    `emotion and situation: ${situationPrompt}`,
    "VISUAL_STORYTELLING_PRIMARY: the character's pose, facial expression, gesture amplitude, and body language must communicate the situation unmistakably at a glance, with zero reliance on captions",
    "exaggerate expression and silhouette so the emotion is readable from the visual alone — no caption needed to disambiguate",
    "one core action repeated smoothly through the 16-frame loop; no multiple actions or sudden direction changes",
    `post-processing lettering style, not for model rendering: ${letteringStylePrompt}`,
    "do not draw any letters, captions, speech bubbles, or text in the generated image",
    "simple readable sticker character with clear silhouette and opaque clean colors",
    "pure white background (#FFFFFF) only; no transparency, no colors, no gradients in the background",
    "absolutely no borders, no frames, no background boxes, no panels, no ground shadows, no scenery, and no background plates",
    "the character must be the only element in the frame, placed directly on the pure white background"
  ].join(", ");
}
