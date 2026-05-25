import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import JSZip from "jszip";
import { NextResponse } from "next/server";
import { getJob } from "@/lib/jobs";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: { jobId: string } }) {
  try {
    const job = await getJob(params.jobId);
    if (job.status !== "completed" || job.finalAssets.length === 0) {
      return NextResponse.json({ error: "아직 다운로드할 최종 GIF가 없습니다." }, { status: 400 });
    }

    const zip = new JSZip();
    for (const asset of job.finalAssets) {
      zip.file(asset.filename, await readFile(asset.path));
      if (asset.mp4Filename && asset.mp4Path && existsSync(asset.mp4Path)) {
        zip.file(asset.mp4Filename, await readFile(asset.mp4Path));
      }
    }

    const buffer = await zip.generateAsync({ type: "nodebuffer" });
    return new NextResponse(new Uint8Array(buffer), {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="imoji-${job.id}.zip"`,
        "Cache-Control": "no-store"
      }
    });
  } catch {
    return NextResponse.json({ error: "ZIP 다운로드를 준비하지 못했습니다." }, { status: 404 });
  }
}
