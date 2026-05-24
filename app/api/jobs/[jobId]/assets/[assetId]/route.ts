import { readFile } from "node:fs/promises";
import { NextResponse } from "next/server";
import { getJob } from "@/lib/jobs";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: { jobId: string; assetId: string } }) {
  try {
    const job = await getJob(params.jobId);
    const asset = job.finalAssets.find((item) => item.id === params.assetId);
    if (!asset) return NextResponse.json({ error: "파일을 찾을 수 없습니다." }, { status: 404 });

    const file = await readFile(asset.path);
    return new NextResponse(new Uint8Array(file), {
      headers: {
        "Content-Type": "image/gif",
        "Content-Disposition": `inline; filename="${asset.filename}"`,
        "Cache-Control": "no-store"
      }
    });
  } catch {
    return NextResponse.json({ error: "파일을 읽지 못했습니다." }, { status: 404 });
  }
}
