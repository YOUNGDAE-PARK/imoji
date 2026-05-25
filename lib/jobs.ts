import { readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import {
  ALLOWED_IMAGE_TYPES,
  FINAL_SITUATIONS,
  LETTERING_STYLES,
  MAX_SELECTED_SITUATIONS,
  MAX_UPLOAD_BYTES,
  MIN_SELECTED_SITUATIONS,
  STYLE_PRESETS
} from "./constants";
import { GenerationJob } from "./types";
import { ensureJobDirs, jobDir, jobFile, readJson, storageRoot, writeJson } from "./storage";
import { ensureWorker } from "./worker";

export async function createJob(formData: FormData) {
  const file = formData.get("sketch");
  const styleId = String(formData.get("styleId") ?? "");
  const letteringStyleId = String(formData.get("letteringStyleId") ?? LETTERING_STYLES[0].id);
  const selectedSituationIds = parseSelectedSituationIds(formData);
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
    selectedSituationIds,
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
    finalCount: selectedSituationsForJob(job).length,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt
  };
}

export function selectedSituationsForJob(job: Pick<GenerationJob, "selectedSituationIds">) {
  const selectedIds = job.selectedSituationIds?.length ? job.selectedSituationIds : [FINAL_SITUATIONS[0].id];
  const selected = selectedIds
    .map((id) => FINAL_SITUATIONS.find((situation) => situation.id === id))
    .filter((situation): situation is (typeof FINAL_SITUATIONS)[number] => Boolean(situation));

  return selected.length ? selected : [FINAL_SITUATIONS[0]];
}

function parseSelectedSituationIds(formData: FormData) {
  const rawValues = formData.getAll("situationIds").flatMap((value) =>
    String(value)
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean)
  );
  const selectedIds = rawValues;
  const uniqueIds = new Set(selectedIds);

  if (selectedIds.length < MIN_SELECTED_SITUATIONS) {
    throw new Error(`이모지는 최소 ${MIN_SELECTED_SITUATIONS}개 이상 선택해주세요.`);
  }
  if (selectedIds.length > MAX_SELECTED_SITUATIONS) {
    throw new Error(`이모지는 최대 ${MAX_SELECTED_SITUATIONS}개까지 선택할 수 있습니다.`);
  }
  if (uniqueIds.size !== selectedIds.length) {
    throw new Error("중복된 이모지 상황이 포함되어 있습니다.");
  }

  const validIds = new Set<string>(FINAL_SITUATIONS.map((situation) => situation.id));
  const invalidId = selectedIds.find((id) => !validIds.has(id));
  if (invalidId) throw new Error(`지원하지 않는 이모지 상황입니다: ${invalidId}`);

  return selectedIds;
}

function assetForClient(asset: GenerationJob["finalAssets"][number]) {
  return {
    id: asset.id,
    kind: asset.kind,
    situationId: asset.situationId,
    situationLabel: asset.situationLabel,
    displayText: asset.displayText ?? asset.situationLabel,
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
