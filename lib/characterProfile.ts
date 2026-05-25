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
          "Analyze this user-uploaded hand-drawn sketch as a reference for emoticon generation.",
          "Return a detailed English character profile focused ONLY on PRESERVING this exact drawing.",
          "List observable visual traits that make this character unique and must be preserved:",
          "- Exact silhouette outline and body proportions",
          "- Face shape, eye placement, eye shape, pupil direction",
          "- Mouth shape and expression",
          "- Facial asymmetry, quirks, and hand-drawn imperfections",
          "- Head-to-body ratio and limb proportions",
          "- Posture and stance",
          "- Any distinctive accessories, marks, or details",
          "- Line quality and sketch style (rough vs clean, thick vs thin)",
          "CRITICAL: This profile is used to ensure ALL generated emoticons look like the SAME CHARACTER.",
          "Do not suggest design improvements or variations.",
          "Do not mention the background or context.",
          "Do not add personality description beyond visual traits.",
          "Keep the profile under 1000 characters and format as a clear, scannable list."
        ].join(" ")
      }
    ]
  });

  const text = response.text?.trim();
  if (!text) throw new Error("첨부 스케치의 캐릭터 특징을 분석하지 못했습니다.");
  return text;
}
