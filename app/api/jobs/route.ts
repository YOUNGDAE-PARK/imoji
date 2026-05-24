import { NextResponse } from "next/server";
import { createJob, publicJob } from "@/lib/jobs";

export const runtime = "nodejs";

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
