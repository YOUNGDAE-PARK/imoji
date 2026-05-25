import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { GIFEncoder, applyPalette, quantize } from "gifenc";

const execFileAsync = promisify(execFile);
let nextImagenRequestAt = 0;

type GenerateInput = {
  prompt: string;
  situationLabel: string;
  motionPreset: string;
  referenceImagePath: string;
  referenceMimeType: string;
  outputGifPath: string;
  tempDir: string;
  label: string;
};

export async function generateGif(input: GenerateInput) {
  await mkdir(path.dirname(input.outputGifPath), { recursive: true });
  await mkdir(input.tempDir, { recursive: true });

  if (process.env.MOCK_GENERATION === "true") {
    await createMockGif(input.outputGifPath, input.label);
    return;
  }

  const mode = generationMode();
  if (mode === "source_motion" || !process.env.GEMINI_API_KEY) {
    await generateSourceMotionGif(input);
    return;
  }

  if (mode === "imagen_sprite") {
    await generateImagenFrameGif(input);
    return;
  }

  await generateImageReferenceSpriteGif(input);
}

function generationMode() {
  return process.env.GENERATION_MODE ?? "image_reference_sprite";
}

async function generateSourceMotionGif(input: GenerateInput) {
  await execFileAsync(
    resolvePythonBin(),
    ["scripts/image_to_motion_gif.py", input.referenceImagePath, input.outputGifPath, input.label, input.motionPreset],
    {
      cwd: process.cwd(),
      timeout: 120000
    }
  );
}

async function generateImagenFrameGif(input: GenerateInput) {
  if (!process.env.GEMINI_API_KEY) {
    await generateSourceMotionGif(input);
    return;
  }

  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  const spriteSheetPath = path.join(input.tempDir, `${path.basename(input.outputGifPath, ".gif")}_sprite.png`);
  const prompt = buildImagenSpriteSheetPrompt(input.prompt, input.situationLabel);
  const response: any = await generateImageWithQuotaRetry(ai, {
    model: process.env.IMAGEN_MODEL ?? "imagen-4.0-fast-generate-001",
    prompt,
    config: {
      numberOfImages: 1,
      aspectRatio: "1:1"
    }
  });

  const generatedImage = response.generatedImages?.[0] ?? response.generated_images?.[0];
  const imageBytes =
    generatedImage?.image?.imageBytes ??
    generatedImage?.image?.image_bytes ??
    generatedImage?.imageBytes ??
    generatedImage?.image_bytes;

  if (!imageBytes) {
    throw new Error("Imagen 응답에서 스프라이트 시트 이미지 데이터를 찾지 못했습니다.");
  }

  const spriteSheetBytes = typeof imageBytes === "string" ? Buffer.from(imageBytes, "base64") : Buffer.from(imageBytes);
  await writeFile(spriteSheetPath, spriteSheetBytes);
  await convertSpriteSheetToGif(spriteSheetPath, input.outputGifPath, input.label);
}

async function generateImageReferenceSpriteGif(input: GenerateInput) {
  if (!process.env.GEMINI_API_KEY) {
    await generateSourceMotionGif(input);
    return;
  }

  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  const imageBase64 = (await readFile(input.referenceImagePath)).toString("base64");
  const spriteSheetPath = path.join(input.tempDir, `${path.basename(input.outputGifPath, ".gif")}_reference_sprite.png`);
  const prompt = buildReferenceSpriteSheetPrompt(input.prompt, input.situationLabel);

  const response: any = await generateContentWithQuotaRetry(ai, {
    model: process.env.GEMINI_IMAGE_MODEL ?? "gemini-2.5-flash-image",
    contents: [
      {
        inlineData: {
          data: imageBase64,
          mimeType: input.referenceMimeType
        }
      },
      {
        text: prompt
      }
    ],
    config: {
      responseModalities: ["TEXT", "IMAGE"],
      imageConfig: {
        aspectRatio: "1:1"
      }
    }
  });

  const imageBytes = extractInlineImageBytes(response);
  if (!imageBytes) {
    throw new Error("Gemini 이미지 응답에서 4x4 스프라이트 데이터를 찾지 못했습니다.");
  }

  const spriteSheetBytes = typeof imageBytes === "string" ? Buffer.from(imageBytes, "base64") : Buffer.from(imageBytes);
  await writeFile(spriteSheetPath, spriteSheetBytes);
  await convertSpriteSheetToGif(spriteSheetPath, input.outputGifPath, input.label);
}

async function generateImageWithQuotaRetry(ai: any, request: Record<string, unknown>) {
  const maxAttempts = maxGenerationAttempts();

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    await waitForImagenSlot();

    try {
      return await ai.models.generateImages(request);
    } catch (error) {
      const retryMs = retryDelayMs(error, attempt);
      if (!retryMs || attempt === maxAttempts) throw error;
      await sleep(retryMs);
    }
  }

  throw new Error("Imagen 이미지 생성 재시도 횟수를 초과했습니다.");
}

async function generateContentWithQuotaRetry(ai: any, request: Record<string, unknown>) {
  const maxAttempts = maxGenerationAttempts();

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    await waitForImagenSlot();

    try {
      return await ai.models.generateContent(request);
    } catch (error) {
      const retryMs = retryDelayMs(error, attempt);
      if (!retryMs || attempt === maxAttempts) throw error;
      await sleep(retryMs);
    }
  }

  throw new Error("Gemini 이미지 생성 재시도 횟수를 초과했습니다.");
}

function maxGenerationAttempts() {
  return Math.max(1, Number(process.env.IMAGE_GENERATION_MAX_ATTEMPTS ?? 6));
}

async function waitForImagenSlot() {
  const minimumGapMs = Number(process.env.IMAGEN_REQUEST_GAP_MS ?? 6500);
  const now = Date.now();

  if (nextImagenRequestAt > now) {
    await sleep(nextImagenRequestAt - now);
  }

  nextImagenRequestAt = Date.now() + minimumGapMs;
}

function retryDelayMs(error: unknown, attempt: number) {
  const text = error instanceof Error ? error.message : JSON.stringify(error);
  const retryDelayMatch = text.match(/retryDelay"?\s*:\s*"?(\d+(?:\.\d+)?)s/i);
  if (retryDelayMatch) return Math.ceil(Number(retryDelayMatch[1]) * 1000) + 1000;

  const retryInMatch = text.match(/retry in (\d+(?:\.\d+)?)s/i);
  if (retryInMatch) return Math.ceil(Number(retryInMatch[1]) * 1000) + 1000;

  if (text.includes("429") || text.includes("RESOURCE_EXHAUSTED") || text.includes("quota")) {
    return 65000;
  }

  if (
    text.includes("503") ||
    text.includes("UNAVAILABLE") ||
    text.toLowerCase().includes("high demand") ||
    text.toLowerCase().includes("overloaded")
  ) {
    const baseMs = Number(process.env.IMAGE_GENERATION_RETRY_BASE_MS ?? 15000);
    const exponentialMs = baseMs * 2 ** Math.min(attempt - 1, 4);
    const jitterMs = Math.round(Math.random() * 3000);
    return Math.min(exponentialMs + jitterMs, 180000);
  }

  return 0;
}

async function convertSpriteSheetToGif(spriteSheetPath: string, outputPath: string, label: string) {
  const debugDir = path.join(path.dirname(spriteSheetPath), `${path.basename(outputPath, ".gif")}_debug_frames`);
  await execFileAsync(resolvePythonBin(), ["scripts/sprite_sheet_to_gif.py", spriteSheetPath, outputPath, label, debugDir], {
    cwd: process.cwd(),
    timeout: 120000
  });
}

function resolvePythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  if (existsSync("/usr/bin/python3")) return "/usr/bin/python3";
  return "python3";
}

function buildImagenSpriteSheetPrompt(basePrompt: string, situationLabel: string) {
  return [
    `MANDATORY KOREAN TEXT TO SHOW IN EVERY PANEL: "${situationLabel}".`,
    "The Korean text above is required. It must be visible, readable, and spelled exactly as provided.",
    "The pose/action must match the Korean text's meaning and the action script below.",
    "Create one single 4x4 grid animation sprite sheet for a KakaoTalk emoticon GIF.",
    "Use exactly 16 animation frames in reading order across all 4 rows and 4 columns.",
    "Every grid cell must contain one animation frame; do not leave any cell blank or unused.",
    "Solid plain white background across the entire image.",
    "No room, no street, no scenery, no props in the background.",
    "Do not add panel borders, numbers, captions, subtitles, or watermarks.",
    "Use a clean 4x4 grid layout with even spacing. Each used panel contains the same character centered in a square area.",
    "Use identical camera distance, identical character scale, and a stable torso/feet anchor across all sixteen panels.",
    "Do not make a static sticker. The animation must have visible action: the arms, head, face, body bounce, and hand-lettering should change clearly between frames.",
    "Keep the character readable and stable, but allow large expressive limb and facial movement that matches the situation.",
    "Clear non-photorealistic sticker art style, clean lines, vibrant colors.",
    "Preserve the exact character identity from the sketch-derived profile in all sixteen panels.",
    "Do not redesign, replace, simplify into a generic mascot, or change the handmade quirks.",
    "Keep the same silhouette, face, colors, outfit, line feeling, proportions, and recognizable quirks in every panel.",
    `ACTION SCRIPT AND CHARACTER BRIEF: ${basePrompt}.`,
    "Animate the exact emotion and action script above. Every frame must express that same situation, not a generic wave or idle pose.",
    `Add the exact Korean text "${situationLabel}" as expressive hand-lettering inside each panel.`,
    "The lettering must feel hand-drawn, witty, and composed around the pose, not like a fixed font or repeated template.",
    "Vary the word placement naturally between panels so the lettering feels part of the motion.",
    "Keep lettering readable but secondary to the character. Do not cover the face or key body silhouette.",
    "Follow all 16 frame action notes from the action script exactly in reading order across the 4x4 grid.",
    "The sixteen panels must look like consecutive snapshots of the same exact character, not different characters."
  ].join(" ");
}

function buildReferenceSpriteSheetPrompt(basePrompt: string, situationLabel: string) {
  return [
    "Use the attached reference image as the strict visual source for the character.",
    "This is an image-reference animation task, not a new mascot design task.",
    "Preserve the reference image's exact character identity, line quality, color palette, proportions, silhouette, face layout, outfit/details, and handmade quirks.",
    "Do not replace, redesign, beautify into a different character, simplify into a generic mascot, or change the art style.",
    "Create one single square 4x4 sprite sheet for a KakaoTalk-style animated emoticon GIF.",
    "Use exactly 16 animation frames in reading order: left to right, top row to bottom row.",
    "Every cell must be used and must show the same exact reference character in a consecutive animation pose.",
    "No text, no Korean letters, no captions, no speech bubbles, no watermarks, no frame numbers, and no panel labels. Korean text will be overlaid later by post-processing.",
    "Use a plain white or transparent background only. No rooms, scenery, props, borders, or grid lines.",
    "Keep camera distance, canvas coordinates, character scale, torso anchor, and framing stable across all sixteen frames.",
    "Animate exactly one core action only. Do not combine multiple gestures, new poses, scene cuts, or separate mini-actions in the same sprite sheet.",
    "The sixteen frames must be a smooth looping cycle of that one action: rest -> tiny anticipation -> action begins -> action peak -> soft rebound -> return to rest.",
    "The last frame must visually connect back to the first frame without a jump cut.",
    "Use small incremental pose changes between neighboring frames. No sudden pose swaps, no teleporting limbs, no camera jump.",
    "Keep the motion readable but restrained; prioritize loop continuity over dramatic variety.",
    `Korean label meaning to express through pose only: "${situationLabel}".`,
    `Sixteen-frame situation/action script: ${basePrompt}.`,
    "The result should look like the uploaded character has been naturally re-posed and animated, not like a separate character copied from a text prompt."
  ].join(" ");
}

function extractInlineImageBytes(response: any) {
  const candidateParts =
    response?.candidates?.flatMap((candidate: any) => candidate?.content?.parts ?? []) ??
    response?.parts ??
    response?.content?.parts ??
    [];

  for (const part of candidateParts) {
    const inlineData = part?.inlineData ?? part?.inline_data;
    const data = inlineData?.data ?? inlineData?.imageBytes ?? inlineData?.image_bytes;
    if (data) return data;
  }

  const generatedImage = response?.generatedImages?.[0] ?? response?.generated_images?.[0];
  return (
    generatedImage?.image?.imageBytes ??
    generatedImage?.image?.image_bytes ??
    generatedImage?.imageBytes ??
    generatedImage?.image_bytes
  );
}

async function createMockGif(outputPath: string, label: string) {
  const width = 320;
  const height = 320;
  const gif = GIFEncoder();
  const seed = hash(label);

  const frameCount = 9;

  for (let frameIndex = 0; frameIndex < frameCount; frameIndex += 1) {
    const rgba = new Uint8Array(width * height * 4);
    const pulse = Math.sin((frameIndex / frameCount) * Math.PI * 2);
    const centerX = 160 + Math.round(pulse * 14);
    const centerY = 158 + Math.round(Math.cos((frameIndex / frameCount) * Math.PI * 2) * 6);
    const bodyColor = [80 + (seed % 120), 80 + ((seed >> 3) % 120), 90 + ((seed >> 6) % 110)];

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const offset = (y * width + x) * 4;
        rgba[offset] = 255;
        rgba[offset + 1] = 251;
        rgba[offset + 2] = 241;
        rgba[offset + 3] = 255;

        const dx = x - centerX;
        const dy = y - centerY;
        const inBody = dx * dx + dy * dy < 72 * 72;
        const inFace = dx * dx + (dy + 12) * (dy + 12) < 54 * 54;
        const inEarLeft = (x - centerX + 58) ** 2 + (y - centerY + 56) ** 2 < 26 ** 2;
        const inEarRight = (x - centerX - 58) ** 2 + (y - centerY + 56) ** 2 < 26 ** 2;

        if (inBody || inEarLeft || inEarRight) {
          rgba[offset] = bodyColor[0];
          rgba[offset + 1] = bodyColor[1];
          rgba[offset + 2] = bodyColor[2];
        }

        if (inFace) {
          rgba[offset] = Math.min(255, bodyColor[0] + 48);
          rgba[offset + 1] = Math.min(255, bodyColor[1] + 48);
          rgba[offset + 2] = Math.min(255, bodyColor[2] + 48);
        }

        const eyeY = centerY - 10;
        const eyeOpen = frameIndex % 8 < 6;
        if (Math.abs(y - eyeY) < (eyeOpen ? 7 : 2) && (Math.abs(x - (centerX - 22)) < 7 || Math.abs(x - (centerX + 22)) < 7)) {
          rgba[offset] = 38;
          rgba[offset + 1] = 34;
          rgba[offset + 2] = 30;
        }

        const mouthY = centerY + 28;
        if (Math.abs(y - mouthY) < 3 && Math.abs(x - centerX) < 16 + pulse * 3) {
          rgba[offset] = 38;
          rgba[offset + 1] = 34;
          rgba[offset + 2] = 30;
        }
      }
    }

    const palette = quantize(rgba, 256);
    const indexed = applyPalette(rgba, palette);
    gif.writeFrame(indexed, width, height, { palette, delay: 90 });
  }

  gif.finish();
  await writeFile(outputPath, Buffer.from(gif.bytes()));
}

function hash(value: string) {
  let result = 0;
  for (let i = 0; i < value.length; i += 1) result = (result * 31 + value.charCodeAt(i)) >>> 0;
  return result;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
