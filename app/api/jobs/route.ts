import { NextResponse } from "next/server";
import { createJob, listJobs, publicJob } from "@/lib/jobs";

export const runtime = "nodejs";

export async function GET() {
  try {
    const jobs = await listJobs();
    return NextResponse.json({ jobs: jobs.map(publicJob) });
  } catch {
    return NextResponse.json({ error: "작업 목록을 불러오지 못했습니다." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const job = await createJob(await request.formData());
    return NextResponse.json({ job: publicJob(job) }, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "작업을 생성하지 못했습니다." },
      { status: 400 }
    );
  }
}
