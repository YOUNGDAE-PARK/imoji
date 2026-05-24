import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

export function storageRoot() {
  return path.resolve(process.env.STORAGE_DIR ?? "./storage");
}

export function jobDir(jobId: string) {
  return path.join(storageRoot(), "jobs", jobId);
}

export function jobFile(jobId: string) {
  return path.join(jobDir(jobId), "job.json");
}

export async function ensureJobDirs(jobId: string) {
  await mkdir(path.join(jobDir(jobId), "uploads"), { recursive: true });
  await mkdir(path.join(jobDir(jobId), "preview"), { recursive: true });
  await mkdir(path.join(jobDir(jobId), "final"), { recursive: true });
  await mkdir(path.join(jobDir(jobId), "tmp"), { recursive: true });
}

export async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

export async function writeJson(filePath: string, value: unknown) {
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}
