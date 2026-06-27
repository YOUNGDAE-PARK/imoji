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
    const kakaoFolder = zip.folder("kakao");   // 카카오 스튜디오 제출용 GIF (360×360)
    const pngFolder   = zip.folder("png");     // 정적 PNG 썸네일 (스티콘 제출 또는 GIF 대체용)
    const mp4Folder   = zip.folder("mp4");     // 개인 SNS 공유용 MP4

    for (const asset of job.finalAssets) {
      if (existsSync(asset.path)) {
        kakaoFolder!.file(asset.filename, await readFile(asset.path));
      }
      if (asset.thumbPath && existsSync(asset.thumbPath)) {
        pngFolder!.file(asset.thumbFilename!, await readFile(asset.thumbPath));
      }
      if (asset.mp4Filename && asset.mp4Path && existsSync(asset.mp4Path)) {
        mp4Folder!.file(asset.mp4Filename, await readFile(asset.mp4Path));
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
