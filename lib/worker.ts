import path from "node:path";
import { analyzeCharacterProfile } from "./characterProfile";
import { generateGif } from "./generator";
import { listQueuedJobs, saveJob, selectedSituationsForJob } from "./jobs";
import { buildGenerationPrompt } from "./prompts";
import { jobDir } from "./storage";
import { GeneratedAsset, GenerationJob } from "./types";

let running = false;

export function ensureWorker() {
  if (running) return;
  running = true;
  void runWorker().finally(() => {
    running = false;
  });
}

async function runWorker() {
  while (true) {
    const [job] = await listQueuedJobs();
    if (!job) return;

    try {
      await generateFinal(job);
    } catch (error) {
      job.status = "failed";
      job.error = error instanceof Error ? error.message : "생성 중 알 수 없는 오류가 발생했습니다.";
      await saveJob(job);
    }
  }
}

async function generateFinal(job: GenerationJob) {
  job.status = "generating_final";
  job.error = undefined;
  await saveJob(job);

  const assets: GeneratedAsset[] = [];
  const characterProfile = job.characterProfile ?? (await analyzeCharacterProfile(job.uploadPath, job.uploadMimeType));
  job.characterProfile = characterProfile;
  await saveJob(job);

  const situations = selectedSituationsForJob(job);
  for (let index = 0; index < situations.length; index += 1) {
    const situation = situations[index];
    const labelEnabled =
      process.env.LABEL_TEXT_ENABLED === "1" || process.env.LABEL_TEXT_ENABLED === "true";
    const displayText = pickDisplayText(job.id, situation.id, situation.textVariants);
    const gifLabel = labelEnabled ? displayText : "";
    const id = `${job.id}:final:A:${situation.id}`;
    const filename = `emoticon_${String(index + 1).padStart(2, "0")}_${situation.id}.gif`;
    const outputPath = path.join(jobDir(job.id), "final", filename);
    const prompt = buildGenerationPrompt({
      styleId: job.styleId,
      characterProfile,
      letteringStylePrompt: job.letteringStylePrompt,
      situationLabel: situation.label,
      situationPrompt: situation.prompt,
      situationAnimationPrompt: situation.animationPrompt,
      situationFrames: situation.frames
    });

    await generateGif({
      prompt,
      situationLabel: situation.label,
      motionPreset: situation.motionPreset,
      referenceImagePath: job.uploadPath,
      referenceMimeType: job.uploadMimeType,
      outputGifPath: outputPath,
      tempDir: path.join(jobDir(job.id), "tmp"),
      label: gifLabel
    });

    assets.push({
      id,
      kind: "final",
      situationId: situation.id,
      situationLabel: situation.label,
      displayText,
      typeId: "A",
      filename,
      path: outputPath
    });
  }

  job.finalAssets = assets;
  job.status = "completed";
  await saveJob(job);
}

function pickDisplayText(jobId: string, situationId: string, variants: string[]) {
  if (variants.length === 0) return situationId;
  let hash = 0;
  for (const char of `${jobId}:${situationId}`) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return variants[hash % variants.length];
}
