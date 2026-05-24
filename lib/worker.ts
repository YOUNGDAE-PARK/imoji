import path from "node:path";
import { FINAL_SITUATIONS } from "./constants";
import { analyzeCharacterProfile } from "./characterProfile";
import { generateGif } from "./generator";
import { listQueuedJobs, saveJob } from "./jobs";
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

  for (let index = 0; index < FINAL_SITUATIONS.length; index += 1) {
    const situation = FINAL_SITUATIONS[index];
    const id = `${job.id}:final:A:${situation.id}`;
    const filename = `emoticon_${String(index + 1).padStart(2, "0")}_${situation.id}.gif`;
    const outputPath = path.join(jobDir(job.id), "final", filename);
    const prompt = buildGenerationPrompt({
      styleId: job.styleId,
      characterProfile,
      letteringStylePrompt: job.letteringStylePrompt,
      situationLabel: situation.label,
      situationPrompt: situation.prompt
    });

    await generateGif({
      prompt,
      referenceImagePath: job.uploadPath,
      referenceMimeType: job.uploadMimeType,
      outputGifPath: outputPath,
      tempDir: path.join(jobDir(job.id), "tmp"),
      label: `${job.styleLabel} ${situation.label}`
    });

    assets.push({
      id,
      kind: "final",
      situationId: situation.id,
      situationLabel: situation.label,
      typeId: "A",
      filename,
      path: outputPath
    });
  }

  job.finalAssets = assets;
  job.status = "completed";
  await saveJob(job);
}
