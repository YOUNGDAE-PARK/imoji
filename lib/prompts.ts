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
    "CRITICAL STABILITY: all 16 frames must show the SAME CHARACTER in completely stable, unchanging position, scale, and canvas anchoring",
    "LOCK CHARACTER POSITION: all 16 frames must have identical canvas size, identical character centerline placement, and identical background handling — zero position drift allowed",
    "ZERO JITTER: do not shift or wobble character position, size, or body anchor between frames; character must stay locked to center; only the pose/expression/gesture changes",
    "SMOOTH LOOP CLOSURE: frame 16 must connect visually to frame 1 with zero jump, wobble, size shift, or position discontinuity",
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
    "transparent background or plain removable white background only; all character pixels must be fully colored and opaque; no scenery, props, or environmental elements"
  ].join(", ");
}
