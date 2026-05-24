import { readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { ALLOWED_IMAGE_TYPES, FINAL_SITUATIONS, LETTERING_STYLES, MAX_UPLOAD_BYTES, STYLE_PRESETS } from "./constants";
import { GenerationJob } from "./types";
import { ensureJobDirs, jobDir, jobFile, readJson, storageRoot, writeJson } from "./storage";
import { ensureWorker } from "./worker";

export async function createJob(formData: FormData) {
  const file = formData.get("sketch");
  const styleId = String(formData.get("styleId") ?? "");
  const letteringStyleId = String(formData.get("letteringStyleId") ?? LETTERING_STYLES[0].id);
  const style = STYLE_PRESETS.find((item) => item.id === styleId);
  const letteringStyle = LETTERING_STYLES.find((item) => item.id === letteringStyleId);

  if (!style) throw new Error("지원하지 않는 스타일입니다.");
  if (!letteringStyle) throw new Error("지원하지 않는 글꼴 스타일입니다.");
  if (!(file instanceof File)) throw new Error("스케치 파일을 첨부해주세요.");
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) throw new Error("PNG, JPG, WEBP, GIF 이미지만 업로드할 수 있습니다.");
  if (file.size > MAX_UPLOAD_BYTES) throw new Error("파일은 8MB 이하만 업로드할 수 있습니다.");

  const id = crypto.randomUUID();
  await ensureJobDirs(id);

  const ext = extensionFor(file.type);
  const uploadPath = path.join(jobDir(id), "uploads", `sketch.${ext}`);
  await writeFile(uploadPath, Buffer.from(await file.arrayBuffer()));

  const now = new Date().toISOString();
  const job: GenerationJob = {
    id,
    status: "queued",
    styleId: style.id,
    styleLabel: style.label,
    letteringStyleId: letteringStyle.id,
    letteringStyleLabel: letteringStyle.label,
    letteringStylePrompt: letteringStyle.prompt,
    uploadPath,
    uploadMimeType: file.type,
    finalAssets: [],
    createdAt: now,
    updatedAt: now
  };

  await saveJob(job);
  ensureWorker();
  return job;
}

export async function getJob(jobId: string) {
  return readJson<GenerationJob>(jobFile(jobId));
}

export async function saveJob(job: GenerationJob) {
  job.updatedAt = new Date().toISOString();
  await writeJson(jobFile(job.id), job);
}

export async function listQueuedJobs() {
  const root = path.join(storageRoot(), "jobs");
  let ids: string[] = [];
  try {
    ids = await readdir(root);
  } catch {
    return [];
  }

  const jobs: GenerationJob[] = [];
  for (const id of ids) {
    try {
      const job = await getJob(id);
      if (job.status === "queued") jobs.push(job);
    } catch {
      // Ignore partial job folders.
    }
  }
  return jobs.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export function publicJob(job: GenerationJob) {
  return {
    id: job.id,
    status: job.status,
    styleId: job.styleId,
    styleLabel: job.styleLabel,
    letteringStyleId: job.letteringStyleId,
    letteringStyleLabel: job.letteringStyleLabel,
    characterProfile: job.characterProfile,
    error: job.error,
    finalAssets: job.finalAssets.map(assetForClient),
    finalCount: FINAL_SITUATIONS.length,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt
  };
}

function assetForClient(asset: GenerationJob["finalAssets"][number]) {
  return {
    id: asset.id,
    kind: asset.kind,
    situationId: asset.situationId,
    situationLabel: asset.situationLabel,
    typeId: asset.typeId,
    filename: asset.filename,
    url: `/api/jobs/${asset.id.split(":")[0]}/assets/${encodeURIComponent(asset.id)}`
  };
}

function extensionFor(mimeType: string) {
  if (mimeType === "image/png") return "png";
  if (mimeType === "image/webp") return "webp";
  if (mimeType === "image/gif") return "gif";
  return "jpg";
}
