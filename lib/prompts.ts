import { STYLE_PRESETS } from "./constants";

type PromptInput = {
  styleId: string;
  situationPrompt: string;
  situationLabel: string;
  characterProfile: string;
  letteringStylePrompt: string;
};

export function buildGenerationPrompt({ styleId, situationPrompt, situationLabel, characterProfile, letteringStylePrompt }: PromptInput) {
  const style = STYLE_PRESETS.find((item) => item.id === styleId) ?? STYLE_PRESETS[0];

  return [
    "a cute KakaoTalk emoticon character based on this exact sketch-derived character profile",
    "do not redesign, replace, genericize, or invent a different character",
    `character identity lock: ${characterProfile}`,
    `art style: ${style.prompt}`,
    `emotion and situation: ${situationPrompt}`,
    `Korean situation word to include: ${situationLabel}`,
    `lettering style: ${letteringStylePrompt}`,
    "centered full body character, simple readable sticker pose"
  ].join(", ");
}
