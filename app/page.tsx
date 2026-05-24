"use client";

/* eslint-disable @next/next/no-img-element */

import { ChangeEvent, useEffect, useState } from "react";
import { Download, ImagePlus, Loader2, Sparkles } from "lucide-react";
import { LETTERING_STYLES, STYLE_PRESETS } from "@/lib/constants";

type ClientAsset = {
  id: string;
  kind: "preview" | "final";
  situationId: string;
  situationLabel: string;
  typeId: "A" | "B" | "C";
  filename: string;
  url: string;
};

type ClientJob = {
  id: string;
  status: "queued" | "generating_final" | "completed" | "failed";
  styleId: string;
  styleLabel: string;
  letteringStyleId: string;
  letteringStyleLabel: string;
  characterProfile?: string;
  error?: string;
  finalAssets: ClientAsset[];
  finalCount: number;
};

const statusText: Record<ClientJob["status"], string> = {
  queued: "작업 대기 중",
  generating_final: "스케치를 분석하고 GIF 4개 생성 중",
  completed: "완료",
  failed: "실패"
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [styleId, setStyleId] = useState<string>(STYLE_PRESETS[0].id);
  const [letteringStyleId, setLetteringStyleId] = useState<string>(LETTERING_STYLES[0].id);
  const [job, setJob] = useState<ClientJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;

    const timer = window.setInterval(async () => {
      const response = await fetch(`/api/jobs/${job.id}`, { cache: "no-store" });
      const data = await response.json();
      if (response.ok) setJob(data.job);
    }, 2200);

    return () => window.clearInterval(timer);
  }, [job]);

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setFile(nextFile);
    setError("");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(nextFile ? URL.createObjectURL(nextFile) : "");
  }

  async function createGenerationJob() {
    if (!file) {
      setError("스케치 파일을 첨부해주세요.");
      return;
    }

    setBusy(true);
    setError("");
    const formData = new FormData();
    formData.append("sketch", file);
    formData.append("styleId", styleId);
    formData.append("letteringStyleId", letteringStyleId);

    const response = await fetch("/api/jobs", { method: "POST", body: formData });
    const data = await response.json();
    setBusy(false);

    if (!response.ok) {
      setError(data.error ?? "작업 생성에 실패했습니다.");
      return;
    }

    setJob(data.job);
  }

  const isGenerating = job?.status === "queued" || job?.status === "generating_final";
  const finalAssets = job?.finalAssets ?? [];

  return (
    <main className="page">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">I</div>
          <h1>Imoji</h1>
        </div>
        <div className="steps">
          {["스케치 업로드", "스타일 선택", "GIF 8개 생성", "ZIP 다운로드"].map((item, index) => (
            <div className="step" key={item}>
              <span className="step-index">{index + 1}</span>
              <span>{item}</span>
            </div>
          ))}
        </div>
      </aside>

      <section className="main">
        <div className="toolbar">
          <div>
            <h2>카카오톡 GIF 이모티콘 생성기</h2>
            <div className="status">{job ? statusText[job.status] : "연필 스케치를 업로드해서 시작하세요"}</div>
          </div>
          {isGenerating ? <Loader2 aria-label="생성 중" /> : <Sparkles aria-label="준비됨" />}
        </div>

        {!job && (
          <section className="panel upload-grid">
            <label className="drop">
              {previewUrl ? (
                <img className="preview-img" src={previewUrl} alt="업로드한 스케치 미리보기" />
              ) : (
                <span>
                  <ImagePlus size={34} />
                  <br />
                  스케치 이미지 선택
                </span>
              )}
              <input accept="image/png,image/jpeg,image/webp,image/gif" type="file" hidden onChange={onFileChange} />
            </label>

            <div>
              <div className="style-grid">
                {STYLE_PRESETS.map((style) => (
                  <button
                    className={`style-button ${styleId === style.id ? "active" : ""}`}
                    key={style.id}
                    type="button"
                    onClick={() => setStyleId(style.id)}
                  >
                    {style.label}
                  </button>
                ))}
              </div>
              <div className="section-label">글꼴 스타일</div>
              <div className="style-grid">
                {LETTERING_STYLES.map((style) => (
                  <button
                    className={`style-button ${letteringStyleId === style.id ? "active" : ""}`}
                    key={style.id}
                    type="button"
                    onClick={() => setLetteringStyleId(style.id)}
                  >
                    {style.label}
                  </button>
                ))}
              </div>
              <div className="actions">
                <button className="primary" type="button" disabled={busy} onClick={createGenerationJob}>
                  {busy ? "시작 중" : "GIF 4개 생성"}
                </button>
              </div>
              {error ? <div className="error">{error}</div> : null}
            </div>
          </section>
        )}

        {job && (
          <section className="panel">
            {isGenerating && (
              <div>
                <strong>{statusText[job.status]}</strong>
                <p className="status">
                  첨부 스케치를 Gemini Vision으로 분석한 뒤 상황별 스프라이트 GIF를 생성합니다. 이 화면은 자동으로 갱신됩니다.
                </p>
              </div>
            )}

            {job.status === "completed" && finalAssets.length > 0 && (
              <>
                <div className="asset-grid result-grid">
                  {finalAssets.map((asset) => (
                    <div className="asset-card" key={asset.id}>
                      <img src={asset.url} alt={asset.situationLabel} />
                      <div className="asset-meta">
                        <span>{asset.situationLabel}</span>
                        <span>GIF</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="actions">
                  <a className="secondary" href={`/api/jobs/${job.id}/download`}>
                    <Download size={18} />
                    ZIP 다운로드
                  </a>
                  <button className="primary" type="button" onClick={() => setJob(null)}>
                    새로 만들기
                  </button>
                </div>
              </>
            )}

            {job.status === "failed" && <div className="error">{job.error ?? "생성에 실패했습니다."}</div>}
            {error ? <div className="error">{error}</div> : null}
          </section>
        )}
      </section>
    </main>
  );
}
