import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { GIFEncoder, applyPalette, quantize } from "gifenc";

const execFileAsync = promisify(execFile);
let nextImagenRequestAt = 0;

type GenerateInput = {
  prompt: string;
  referenceImagePath: string;
  referenceMimeType: string;
  outputGifPath: string;
  tempDir: string;
  label: string;
};

export async function generateGif(input: GenerateInput) {
  await mkdir(path.dirname(input.outputGifPath), { recursive: true });
  await mkdir(input.tempDir, { recursive: true });

  if (shouldUseMock()) {
    await createMockGif(input.outputGifPath, input.label);
    return;
  }

  await generateImagenFrameGif(input);
}

function shouldUseMock() {
  return process.env.MOCK_GENERATION === "true" || !process.env.GEMINI_API_KEY;
}

async function generateImagenFrameGif(input: GenerateInput) {
  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  const spriteSheetPath = path.join(input.tempDir, `${path.basename(input.outputGifPath, ".gif")}_sprite.png`);
  const prompt = buildImagenSpriteSheetPrompt(input.prompt);
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
  await convertSpriteSheetToGif(spriteSheetPath, input.outputGifPath);
}

async function generateImageWithQuotaRetry(ai: any, request: Record<string, unknown>) {
  const maxAttempts = 4;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    await waitForImagenSlot();

    try {
      return await ai.models.generateImages(request);
    } catch (error) {
      const retryMs = retryDelayMs(error);
      if (!retryMs || attempt === maxAttempts) throw error;
      await sleep(retryMs);
    }
  }

  throw new Error("Imagen 이미지 생성 재시도 횟수를 초과했습니다.");
}

async function waitForImagenSlot() {
  const minimumGapMs = Number(process.env.IMAGEN_REQUEST_GAP_MS ?? 6500);
  const now = Date.now();

  if (nextImagenRequestAt > now) {
    await sleep(nextImagenRequestAt - now);
  }

  nextImagenRequestAt = Date.now() + minimumGapMs;
}

function retryDelayMs(error: unknown) {
  const text = error instanceof Error ? error.message : JSON.stringify(error);
  const retryDelayMatch = text.match(/retryDelay"?\s*:\s*"?(\d+(?:\.\d+)?)s/i);
  if (retryDelayMatch) return Math.ceil(Number(retryDelayMatch[1]) * 1000) + 1000;

  const retryInMatch = text.match(/retry in (\d+(?:\.\d+)?)s/i);
  if (retryInMatch) return Math.ceil(Number(retryInMatch[1]) * 1000) + 1000;

  if (text.includes("429") || text.includes("RESOURCE_EXHAUSTED") || text.includes("quota")) {
    return 65000;
  }

  return 0;
}

async function convertSpriteSheetToGif(spriteSheetPath: string, outputPath: string) {
  await execFileAsync(resolvePythonBin(), ["scripts/sprite_sheet_to_gif.py", spriteSheetPath, outputPath], {
    cwd: process.cwd(),
    timeout: 120000
  });
}

function resolvePythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  if (existsSync("/usr/bin/python3")) return "/usr/bin/python3";
  return "python3";
}

function buildImagenSpriteSheetPrompt(basePrompt: string) {
  return [
    "Create one single 2x2 grid animation sprite sheet for a KakaoTalk emoticon GIF.",
    "Solid plain white background across the entire image.",
    "No room, no street, no scenery, no props in the background.",
    "Do not add panel borders, numbers, captions, subtitles, watermarks, or typed digital fonts.",
    "Use a clean 2x2 grid layout with even spacing. Each panel contains the same character centered in a square area.",
    "Clear non-photorealistic sticker art style, clean lines, vibrant colors.",
    "Preserve the exact character identity from the sketch-derived profile in all four panels.",
    "Do not redesign, replace, simplify into a generic mascot, or change the handmade quirks.",
    "Keep the same silhouette, face, colors, outfit, line feeling, proportions, and recognizable quirks in every panel.",
    `Subject prompt: ${basePrompt}.`,
    "Add the Korean situation word from the subject prompt as expressive hand-lettering inside each panel.",
    "The lettering must feel hand-drawn, witty, and composed around the pose, not like a fixed font or repeated template.",
    "Vary the word placement naturally between panels: near the raised hand, beside the face, vertical along empty space, or tucked into a corner.",
    "Keep lettering readable but secondary to the character. Do not cover the face or key body silhouette.",
    "Top-left panel: frame 1, standing facing forward, neutral friendly expression.",
    "Top-right panel: frame 2, raising one hand slightly, smiling.",
    "Bottom-left panel: frame 3, waving the same hand high, cheerful expression.",
    "Bottom-right panel: frame 4, putting the hand back down slightly, big smile.",
    "The four panels must look like consecutive snapshots of the same exact character, not four different characters."
  ].join(" ");
}

async function createMockGif(outputPath: string, label: string) {
  const width = 320;
  const height = 320;
  const gif = GIFEncoder();
  const seed = hash(label);

  const frameCount = 4;

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
