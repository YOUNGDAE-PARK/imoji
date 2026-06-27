import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export async function generateBaseCharacter(
  sketchPath: string,
  mimeType: string,
  profile: string,
  outputPath: string,
  stylePrompt: string,
  modeId: string = "general"
): Promise<string> {
  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY! });
  
  const sketchBase64 = (await readFile(sketchPath)).toString("base64");
  
  const prompt = [
    "You are a master character artist. Transform the attached rough sketch into a high-quality base character sticker.",
    "STRICT REQUIREMENTS:",
    "- 100% FAITHFUL to the character's unique form, proportions, and quirky asymmetry seen in the sketch.",
    "- Keep the same facial feature placement (eyes, mouth, ears) as the sketch.",
    "- Preserve any unique details like tails, patterns, or accessories exactly as drawn.",
    "- Style: Clean, professional sticker art, vibrant colors, clear outlines.",
    "- Pose: Front-facing, neutral expression.",
    "- Background: Perfectly transparent or pure white.",
    "- No extra background elements, scenery, or shadows.",
    "- The result must be recognizable as the EXACT SAME character from the sketch, just more polished.",
    ...(modeId === "tennis" ? [
      "TENNIS MODE — ADD THESE to the character (preserve the character's identity exactly):",
      "- Outfit: tennis polo shirt (short sleeve), tennis shorts or skirt",
      "- Footwear: white tennis shoes",
      "- Equipment: holding a tennis racket in the RIGHT hand (full racket visible, gripped at handle)",
      "- Optional: sweatband on forehead or wrist",
      "- The tennis racket and outfit must look natural for this character's specific body shape.",
      "- Keep the character's face, proportions, and unique quirky features EXACTLY as in the sketch.",
    ] : []),
  ].join("\n");

  const modelName = process.env.GEMINI_IMAGE_MODEL ?? "gemini-2.0-flash-exp";
  
  try {
    const response: any = await ai.models.generateContent({
      model: modelName,
      contents: [
        { inlineData: { data: sketchBase64, mimeType } },
        { text: prompt }
      ],
      config: {
        responseModalities: ["IMAGE"],
        safetySettings: [
          { category: "HARM_CATEGORY_HARASSMENT", threshold: "BLOCK_NONE" },
          { category: "HARM_CATEGORY_HATE_SPEECH", threshold: "BLOCK_NONE" },
          { category: "HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold: "BLOCK_NONE" },
          { category: "HARM_CATEGORY_DANGEROUS_CONTENT", threshold: "BLOCK_NONE" }
        ] as any
      }
    });

    const imageBytes = extractInlineImageBytes(response);
    if (!imageBytes) {
      throw new Error("Base character generation failed (no image data in response).");
    }

    const bytes = typeof imageBytes === "string" ? Buffer.from(imageBytes, "base64") : Buffer.from(imageBytes);
    await writeFile(outputPath, bytes);
    
    return outputPath;
  } catch (err) {
    console.error(`Gemini Base Character generation failed with ${modelName}:`, err);
    throw err;
  }
}

// ─── 상황별 텍스트 스타일 매핑 ────────────────────────────────────────────────

type TextStyle = { color: string; rotation: number; anchor: "bottom_right" | "bottom_center" | "bottom_left"; size: number };

const SITUATION_TEXT_STYLES: Record<string, TextStyle> = {
  love:       { color: "#FF69B4", rotation: -8,  anchor: "bottom_right",  size: 50 },
  heart:      { color: "#FF69B4", rotation: -8,  anchor: "bottom_right",  size: 50 },
  please:     { color: "#FF69B4", rotation: -6,  anchor: "bottom_right",  size: 48 },
  laugh:      { color: "#FF6E00", rotation: -8,  anchor: "bottom_right",  size: 52 },
  congrats:   { color: "#FF8C00", rotation: -10, anchor: "bottom_right",  size: 54 },
  "cheer-up": { color: "#FF8C00", rotation: -8,  anchor: "bottom_right",  size: 50 },
  best:       { color: "#FF8C00", rotation: -6,  anchor: "bottom_right",  size: 50 },
  thanks:     { color: "#E07000", rotation: -6,  anchor: "bottom_right",  size: 48 },
  hello:      { color: "#00A878", rotation: -6,  anchor: "bottom_right",  size: 48 },
  ok:         { color: "#00A878", rotation: -5,  anchor: "bottom_right",  size: 50 },
  morning:    { color: "#E07000", rotation: -8,  anchor: "bottom_right",  size: 50 },
  "go-work":  { color: "#2E8B8B", rotation: -6,  anchor: "bottom_right",  size: 46 },
  "off-work": { color: "#6A5ACD", rotation: -6,  anchor: "bottom_right",  size: 50 },
  busy:       { color: "#CC6600", rotation: -8,  anchor: "bottom_right",  size: 46 },
  hungry:     { color: "#CC4400", rotation: -6,  anchor: "bottom_right",  size: 48 },
  surprised:  { color: "#D61E1E", rotation: -12, anchor: "bottom_right",  size: 58 },
  angry:      { color: "#D61E1E", rotation: -10, anchor: "bottom_right",  size: 54 },
  nope:       { color: "#D61E1E", rotation: -8,  anchor: "bottom_right",  size: 52 },
  sorry:      { color: "#3778C8", rotation:  5,  anchor: "bottom_center", size: 46 },
  sad:        { color: "#3778C8", rotation:  5,  anchor: "bottom_center", size: 46 },
  tears:      { color: "#3778C8", rotation:  4,  anchor: "bottom_center", size: 46 },
  sleepy:     { color: "#6A5ACD", rotation:  6,  anchor: "bottom_center", size: 44 },
  "good-night": { color: "#4B0082", rotation: 5, anchor: "bottom_center", size: 44 },
  wait:       { color: "#888888", rotation: -5,  anchor: "bottom_right",  size: 46 },
  // Tennis situations
  serve_ace:       { color: "#00A000", rotation: -10, anchor: "bottom_right",  size: 54 },
  forehand:        { color: "#00A000", rotation: -8,  anchor: "bottom_right",  size: 52 },
  backhand:        { color: "#007AFF", rotation: -8,  anchor: "bottom_right",  size: 52 },
  smash:           { color: "#FF4500", rotation: -12, anchor: "bottom_right",  size: 58 },
  volley:          { color: "#007AFF", rotation: -6,  anchor: "bottom_right",  size: 50 },
  point_celebrate: { color: "#FF8C00", rotation: -10, anchor: "bottom_right",  size: 56 },
  double_fault:    { color: "#3778C8", rotation:  5,  anchor: "bottom_center", size: 46 },
  drop_shot:       { color: "#9B59B6", rotation: -8,  anchor: "bottom_right",  size: 50 },
  ready_match:     { color: "#00A878", rotation: -6,  anchor: "bottom_right",  size: 50 },
  blame_racket:    { color: "#CC6600", rotation: -8,  anchor: "bottom_right",  size: 48 },
  cheer:           { color: "#FF8C00", rotation: -8,  anchor: "bottom_right",  size: 50 },
  protest:         { color: "#D61E1E", rotation: -10, anchor: "bottom_right",  size: 54 },
  return_ace:      { color: "#00A000", rotation: -10, anchor: "bottom_right",  size: 52 },
  exhausted:       { color: "#3778C8", rotation:  5,  anchor: "bottom_center", size: 44 },
  six_love:        { color: "#FF4500", rotation: -14, anchor: "bottom_right",  size: 60 },
  walk_baseline:   { color: "#555555", rotation: -5,  anchor: "bottom_right",  size: 46 },
};

function getSituationTextStyle(situationId: string): TextStyle {
  if (SITUATION_TEXT_STYLES[situationId]) return SITUATION_TEXT_STYLES[situationId];
  return { color: "#333333", rotation: -6, anchor: "bottom_right", size: 48 };
}

// ─── 캐릭터 정보 추출 (색상 + 특징 설명) ────────────────────────────────────

export type CharacterInfo = {
  colors: Record<string, string>;
  description: string;
};

export async function extractCharacterInfo(baseCharPath: string): Promise<CharacterInfo> {
  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY! });
  const imgB64 = (await readFile(baseCharPath)).toString("base64");
  try {
    const resp: any = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: [
        { inlineData: { data: imgB64, mimeType: "image/png" } },
        {
          text: [
            "Analyze this cute character sticker. Output ONLY JSON (no other text):",
            '{',
            '  "body": "#hex (dominant body fill color)",',
            '  "outline": "#hex (outline/line color)",',
            '  "background": "#FFFFFF",',
            '  "description": "one sentence describing the character\'s fixed features: shape, ears, tail, limbs, etc."',
            '}'
          ].join("\n")
        }
      ]
    });
    const text: string = resp.candidates?.[0]?.content?.parts?.find((p: any) => p.text)?.text ?? "";
    const m = text.match(/\{[\s\S]*?\}/);
    if (m) {
      const parsed = JSON.parse(m[0]);
      return {
        colors: { body: parsed.body ?? "#F5F0E8", outline: parsed.outline ?? "#2A2A2A", background: "#FFFFFF" },
        description: parsed.description ?? "",
      };
    }
  } catch (e) {
    console.warn("extractCharacterInfo failed:", e);
  }
  return { colors: { body: "#F5F0E8", outline: "#2A2A2A", background: "#FFFFFF" }, description: "" };
}

// ─── POC 파이프라인 GIF 생성 ──────────────────────────────────────────────────

export async function generateEmotionGif(
  baseCharacterPath: string,
  situation: { id: string; animationPrompt: string; motionPreset: string; textVariants: string[] },
  charInfo: CharacterInfo,
  displayText: string,
  outputGifPath: string,
  workDir: string,
  variationId: string = "",
  modeId: string = "general",
): Promise<void> {
  const textStyle = getSituationTextStyle(situation.id);
  const situWorkDir = path.join(workDir, situation.id);
  await mkdir(situWorkDir, { recursive: true });
  await mkdir(path.dirname(outputGifPath), { recursive: true });

  const { stdout, stderr } = await execFileAsync(
    resolvePythonBin(),
    [
      "scripts/poc_pipeline/generate_emotion_gif.py",
      "--base_char",        baseCharacterPath,
      "--animation_prompt", situation.animationPrompt,
      "--motion_preset",    situation.motionPreset,
      "--char_description", charInfo.description,
      "--situation_id",     situation.id,
      "--text",             displayText,
      "--text_color",       textStyle.color,
      "--text_rotation",    String(textStyle.rotation),
      "--text_anchor",      textStyle.anchor,
      "--text_size",        String(textStyle.size),
      "--colors_json",      JSON.stringify(charInfo.colors),
      "--variation_id",     variationId,
      "--mode",             modeId,
      "--output",           outputGifPath,
      "--work_dir",         situWorkDir,
    ],
    {
      cwd: process.cwd(),
      timeout: 360000,
      env: { ...process.env },
    }
  );
  if (stdout) console.log(`[poc:${situation.id}]`, stdout.trim());
  if (stderr) console.warn(`[poc:${situation.id}]`, stderr.trim());
}

function extractInlineImageBytes(response: any) {
  const generatedImage = response.generatedImages?.[0] ?? response.generated_images?.[0];
  if (generatedImage) return generatedImage.image?.imageBytes ?? generatedImage.image?.image_bytes;
  
  // Try candidate/parts for multi-modal response
  const part = response.candidates?.[0]?.content?.parts?.find((p: any) => p.inlineData || p.inline_data);
  const inlineData = part?.inlineData ?? part?.inline_data;
  return inlineData?.data ?? inlineData?.imageBytes ?? inlineData?.image_bytes;
}

function resolvePythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  const localVenvPython = path.join(process.cwd(), ".venv", "bin", "python");
  if (existsSync(localVenvPython)) return localVenvPython;
  return "python3";
}
