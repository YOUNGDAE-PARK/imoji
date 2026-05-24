import { NextResponse } from "next/server";
import { getJob, publicJob } from "@/lib/jobs";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: { jobId: string } }) {
  try {
    const job = await getJob(params.jobId);
    return NextResponse.json({ job: publicJob(job) });
  } catch {
    return NextResponse.json({ error: "작업을 찾을 수 없습니다." }, { status: 404 });
  }
}
