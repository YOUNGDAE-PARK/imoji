import { readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import {
  ALLOWED_IMAGE_TYPES,
  FINAL_SITUATIONS,
  LETTERING_STYLES,
  MAX_UPLOAD_BYTES,
  MODES,
  STYLE_PRESETS,
  TENNIS_SITUATIONS
} from "./constants";
import { GenerationJob, ModeId, TextOverlayMap } from "./types";
import { ensureJobDirs, jobDir, jobFile, readJson, storageRoot, writeJson } from "./storage";
import { ensureWorker } from "./worker";

const HEX_COLOR_RE = /^#[0-9a-f]{6}$/i;

export async function createJob(formData: FormData) {
  const file = formData.get("sketch");
  const styleId = String(formData.get("styleId") ?? "");
  const letteringStyleId = String(formData.get("letteringStyleId") ?? LETTERING_STYLES[0].id);
  const modeId = (String(formData.get("modeId") ?? "general")) as ModeId;
  const mode = MODES.find((m) => m.id === modeId) ?? MODES[0];
  const selectedSituationIds = parseSelectedSituationIds(formData, mode.id);
  const textOverlays = parseTextOverlays(formData.get("textOverlays"), selectedSituationIds);
  const style = STYLE_PRESETS.find((item) => item.id === styleId);
  const letteringStyle = LETTERING_STYLES.find((item) => item.id === letteringStyleId);

  if (!style) throw new Error("지원하지 않는 스타일입니다.");
  if (!letteringStyle) throw new Error("지원하지 않는 글꼴 스타일입니다.");
  if (!(file instanceof File)) throw new Error("스케치 파일을 첨부해주세요.");
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) throw new Error("PNG, JPG, WEBP, GIF 이미지만 업로드할 수 있습니다.");
  if (file.size > MAX_UPLOAD_BYTES) throw new Error("파일은 8MB 이하만 업로드할 수 있습니다.");

  const nowStr = new Date().toISOString().replace(/[-:T]/g, "").split(".")[0];
  const rand = crypto.randomUUID().slice(0, 6);
  const id = `${nowStr}_${rand}`;
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
    modeId: mode.id,
    modeLabel: mode.label,
    selectedSituationIds,
    textOverlays,
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

export async function listJobs() {
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
      jobs.push(await getJob(id));
    } catch {
      // Ignore partial job folders.
    }
  }
  return jobs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function listQueuedJobs() {
  const jobs = await listJobs();
  return jobs.filter((job) => job.status === "queued").sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export function publicJob(job: GenerationJob) {
  return {
    id: job.id,
    status: job.status,
    styleId: job.styleId,
    styleLabel: job.styleLabel,
    letteringStyleId: job.letteringStyleId,
    letteringStyleLabel: job.letteringStyleLabel,
    modeId: job.modeId,
    modeLabel: job.modeLabel,
    characterProfile: job.characterProfile,
    error: job.error,
    finalAssets: job.finalAssets.map(assetForClient),
    finalCount: selectedSituationsForJob(job).length,
    selectedSituationIds: job.selectedSituationIds,
    textOverlays: job.textOverlays,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt
  };
}

export function selectedSituationsForJob(job: Pick<GenerationJob, "selectedSituationIds" | "modeId">) {
  const situations = job.modeId === "tennis" ? TENNIS_SITUATIONS : FINAL_SITUATIONS;
  const selectedIds = job.selectedSituationIds?.length ? job.selectedSituationIds : [situations[0].id];
  const selected = selectedIds
    .map((id) => situations.find((situation) => situation.id === id))
    .filter((situation): situation is (typeof situations)[number] => Boolean(situation));

  return selected.length ? selected : [situations[0]];
}

function parseSelectedSituationIds(formData: FormData, modeId: ModeId) {
  const situationsSource = modeId === "tennis" ? TENNIS_SITUATIONS : FINAL_SITUATIONS;
  const rawValues = formData.getAll("situationIds").flatMap((value) =>
    String(value)
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean)
  );
  const selectedIds = rawValues;
  const uniqueIds = new Set(selectedIds);

  if (selectedIds.length < 1) {
    throw new Error(`이모지는 최소 1개 이상 선택해주세요.`);
  }
  if (selectedIds.length > situationsSource.length) {
    throw new Error(`이모지는 최대 ${situationsSource.length}개까지 선택할 수 있습니다.`);
  }
  if (uniqueIds.size !== selectedIds.length) {
    throw new Error("중복된 이모지 상황이 포함되어 있습니다.");
  }

  const validIds = new Set<string>(situationsSource.map((situation) => situation.id));
  const invalidId = selectedIds.find((id) => !validIds.has(id));
  if (invalidId) throw new Error(`지원하지 않는 이모지 상황입니다: ${invalidId}`);

  return selectedIds;
}

function parseTextOverlays(value: FormDataEntryValue | null, selectedSituationIds: string[]): TextOverlayMap | undefined {
  if (!value) return undefined;

  let parsed: unknown;
  try {
    parsed = JSON.parse(String(value));
  } catch {
    throw new Error("텍스트 오버레이 설정을 읽지 못했습니다.");
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("텍스트 오버레이 형식이 올바르지 않습니다.");
  }

  const selected = new Set(selectedSituationIds);
  const result: TextOverlayMap = {};
  for (const [situationId, overlay] of Object.entries(parsed as Record<string, unknown>)) {
    if (!selected.has(situationId)) continue;
    if (!overlay || typeof overlay !== "object" || Array.isArray(overlay)) continue;
    const candidate = overlay as Record<string, unknown>;
    const mode = candidate.mode === "custom" ? "custom" : "default";
    const rawItems = Array.isArray(candidate.items) ? candidate.items : [];
    const items = rawItems.slice(0, 6).flatMap((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return [];
      const raw = item as Record<string, unknown>;
      const text = String(raw.text ?? "").trim().slice(0, 24);
      if (!text) return [];
      const color = String(raw.color ?? "#261f19");
      return [{
        id: String(raw.id ?? crypto.randomUUID()).slice(0, 80),
        text,
        x: clampNumber(raw.x, 0, 320, 160),
        y: clampNumber(raw.y, 0, 320, 270),
        rotation: clampNumber(raw.rotation, -45, 45, 0),
        fontSize: clampNumber(raw.fontSize, 18, 72, 44),
        color: HEX_COLOR_RE.test(color) ? color : "#261f19"
      }];
    });
    result[situationId] = { mode, items };
  }

  return Object.keys(result).length ? result : undefined;
}

function clampNumber(value: unknown, min: number, max: number, fallback: number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, numeric));
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
    mp4Filename: asset.mp4Filename,
    fileSizeKb: asset.fileSizeKb,
    url: `/api/jobs/${asset.id.split(":")[0]}/assets/${encodeURIComponent(asset.id)}`
  };
}

function extensionFor(mimeType: string) {
  if (mimeType === "image/png") return "png";
  if (mimeType === "image/webp") return "webp";
  if (mimeType === "image/gif") return "gif";
  return "jpg";
}
