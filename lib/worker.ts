import path from "node:path";
import { statSync } from "node:fs";
import { analyzeCharacterProfile } from "./characterProfile";
import { extractCharacterInfo, generateBaseCharacter, generateEmotionGif } from "./generator_v2";
import { generateMp4FromGif } from "./generator";
import { listQueuedJobs, saveJob, selectedSituationsForJob } from "./jobs";
import { jobDir } from "./storage";
import { GeneratedAsset, GenerationJob } from "./types";
import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";

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

  // 1. Generate Base Character (POC Pipeline)
  const baseCharacterPath = path.join(jobDir(job.id), "base_character.png");
  if (!existsSync(baseCharacterPath)) {
    await generateBaseCharacter(
      job.uploadPath,
      job.uploadMimeType,
      characterProfile,
      baseCharacterPath,
      job.styleId,
      job.modeId
    );
  }

  // 2. Extract character colors + description (once per job)
  const charInfo = await extractCharacterInfo(baseCharacterPath);
  console.log(`[worker] 캐릭터 정보:`, charInfo);

  const situations = selectedSituationsForJob(job);
  const tmpDir = path.join(jobDir(job.id), "tmp");

  for (let index = 0; index < situations.length; index += 1) {
    const situation = situations[index];
    const id = `${job.id}:final:A:${situation.id}`;
    const basename = `emoticon_${String(index + 1).padStart(2, "0")}_${situation.id}`;
    const filename = `${basename}.gif`;
    const mp4Filename = `${basename}.mp4`;
    const outputPath = path.join(jobDir(job.id), "final", filename);
    const mp4Path = path.join(jobDir(job.id), "final", mp4Filename);

    const displayText = pickDisplayText(job.id, situation.id, situation.textVariants);
    console.log(`[worker] ${situation.id} (${index + 1}/${situations.length}): "${displayText}"`);

    // 3. POC 파이프라인 - AI 키프레임 기반 GIF 생성
    await generateEmotionGif(
      baseCharacterPath,
      situation,
      charInfo,
      displayText,
      outputPath,
      tmpDir,
      job.id,
      job.modeId ?? "general",
    );

    await generateMp4FromGif(outputPath, mp4Path);

    const thumbFilename = `${basename}.png`;
    const thumbPath = path.join(jobDir(job.id), "final", thumbFilename);
    const fileSizeKb = existsSync(outputPath)
      ? Math.round(statSync(outputPath).size / 1024)
      : undefined;

    assets.push({
      id,
      kind: "final",
      situationId: situation.id,
      situationLabel: situation.label,
      displayText,
      typeId: "A",
      filename,
      path: outputPath,
      mp4Filename,
      mp4Path,
      thumbFilename: existsSync(thumbPath) ? thumbFilename : undefined,
      thumbPath: existsSync(thumbPath) ? thumbPath : undefined,
      fileSizeKb,
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
