import { readFile } from "node:fs/promises";

export async function analyzeCharacterProfile(imagePath: string, mimeType: string) {
  if (process.env.MOCK_GENERATION === "true" || !process.env.GEMINI_API_KEY) {
    return [
      "A simple hand-drawn pencil sketch character uploaded by the user.",
      "Preserve the original rough outline, handmade line feeling, proportions, facial placement, and any quirky asymmetry.",
      "Do not replace it with a generic mascot."
    ].join(" ");
  }

  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });
  const imageBase64 = (await readFile(imagePath)).toString("base64");

  const response = await ai.models.generateContent({
    model: process.env.GEMINI_VISION_MODEL ?? "gemini-2.5-flash",
    contents: [
      {
        inlineData: {
          data: imageBase64,
          mimeType
        }
      },
      {
        text: [
          "Analyze this user-uploaded hand-drawn sketch for an emoticon generator.",
          "Return a concise English character profile for image generation.",
          "Focus only on visually observable traits:",
          "silhouette, body shape, face, eyes, mouth, proportions, line quality, pose, accessories, and unique handmade quirks.",
          "Explicitly list what must be preserved so the generated emoticon still looks like this exact drawing.",
          "Do not invent a backstory. Do not describe the background. Do not mention uncertainty.",
          "Keep it under 900 characters."
        ].join(" ")
      }
    ]
  });

  const text = response.text?.trim();
  if (!text) throw new Error("첨부 스케치의 캐릭터 특징을 분석하지 못했습니다.");
  return text;
}
