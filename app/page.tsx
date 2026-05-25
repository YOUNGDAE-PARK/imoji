"use client";

/* eslint-disable @next/next/no-img-element */

import { ChangeEvent, PointerEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Download, ImagePlus, Loader2, Plus, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { FINAL_SITUATIONS, LETTERING_STYLES, MAX_SELECTED_SITUATIONS, MIN_SELECTED_SITUATIONS, STYLE_PRESETS } from "@/lib/constants";

const CANVAS_SIZE = 320;

type TextOverlayItem = {
  id: string;
  text: string;
  x: number;
  y: number;
  rotation: number;
  fontSize: number;
  color: string;
};

type SituationTextOverlay = {
  mode: "default" | "custom";
  items: TextOverlayItem[];
};

type TextOverlayMap = Record<string, SituationTextOverlay>;

type ClientAsset = {
  id: string;
  kind: "preview" | "final";
  situationId: string;
  situationLabel: string;
  displayText: string;
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
  selectedSituationIds?: string[];
  textOverlays?: TextOverlayMap;
  createdAt?: string;
  updatedAt?: string;
};

const statusText: Record<ClientJob["status"], string> = {
  queued: "작업 대기 중",
  generating_final: "스케치를 분석하고 GIF 생성 중",
  completed: "완료",
  failed: "실패"
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [styleId, setStyleId] = useState<string>(STYLE_PRESETS[0].id);
  const [letteringStyleId, setLetteringStyleId] = useState<string>(LETTERING_STYLES[0].id);
  const [selectedSituationIds, setSelectedSituationIds] = useState<string[]>([FINAL_SITUATIONS[0].id]);
  const [activeSituationId, setActiveSituationId] = useState<string>(FINAL_SITUATIONS[0].id);
  const [textOverlays, setTextOverlays] = useState<TextOverlayMap>({});
  const [activeTextItemId, setActiveTextItemId] = useState<string>("");
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

  useEffect(() => {
    if (!selectedSituationIds.includes(activeSituationId)) {
      setActiveSituationId(selectedSituationIds[0] ?? FINAL_SITUATIONS[0].id);
      setActiveTextItemId("");
    }
  }, [activeSituationId, selectedSituationIds]);

  const activeSituation = useMemo(
    () => FINAL_SITUATIONS.find((situation) => situation.id === activeSituationId) ?? FINAL_SITUATIONS[0],
    [activeSituationId]
  );
  const activeOverlay = textOverlays[activeSituationId] ?? defaultOverlay(activeSituation.label);
  const activeItem = activeOverlay.items.find((item) => item.id === activeTextItemId) ?? activeOverlay.items[0];
  const customOverlayCount = selectedSituationIds.filter((id) => textOverlays[id]?.mode === "custom").length;

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
    if (selectedSituationIds.length < MIN_SELECTED_SITUATIONS || selectedSituationIds.length > MAX_SELECTED_SITUATIONS) {
      setError(`이모지는 ${MIN_SELECTED_SITUATIONS}~${MAX_SELECTED_SITUATIONS}개까지 선택할 수 있습니다.`);
      return;
    }

    setBusy(true);
    setError("");
    const formData = new FormData();
    formData.append("sketch", file);
    formData.append("styleId", styleId);
    formData.append("letteringStyleId", letteringStyleId);
    selectedSituationIds.forEach((id) => formData.append("situationIds", id));
    formData.append("textOverlays", JSON.stringify(textOverlays));

    const response = await fetch("/api/jobs", { method: "POST", body: formData });
    const data = await response.json();
    setBusy(false);

    if (!response.ok) {
      setError(data.error ?? "작업 생성에 실패했습니다.");
      return;
    }

    setJob(data.job);
  }

  function toggleSituation(id: string) {
    setError("");
    setSelectedSituationIds((current) => {
      if (current.includes(id)) {
        if (current.length <= MIN_SELECTED_SITUATIONS) return current;
        const next = current.filter((currentId) => currentId !== id);
        if (activeSituationId === id) setActiveSituationId(next[0]);
        return next;
      }
      if (current.length >= MAX_SELECTED_SITUATIONS) return current;
      setActiveSituationId(id);
      return [...current, id];
    });
  }

  function enableCustomOverlay(situationId = activeSituationId) {
    const situation = FINAL_SITUATIONS.find((item) => item.id === situationId) ?? FINAL_SITUATIONS[0];
    setTextOverlays((current) => {
      const existing = current[situationId];
      const next = existing?.items?.length ? existing : defaultOverlay(situation.label);
      setActiveTextItemId(next.items[0]?.id ?? "");
      return { ...current, [situationId]: { ...next, mode: "custom" } };
    });
  }

  function resetOverlay(situationId = activeSituationId) {
    const situation = FINAL_SITUATIONS.find((item) => item.id === situationId) ?? FINAL_SITUATIONS[0];
    setTextOverlays((current) => ({ ...current, [situationId]: defaultOverlay(situation.label) }));
    setActiveTextItemId("");
  }

  function updateActiveItem(patch: Partial<TextOverlayItem>) {
    if (!activeItem) return;
    setTextOverlays((current) => {
      const overlay = current[activeSituationId] ?? defaultOverlay(activeSituation.label);
      return {
        ...current,
        [activeSituationId]: {
          mode: "custom",
          items: overlay.items.map((item) => (item.id === activeItem.id ? { ...item, ...patch } : item))
        }
      };
    });
  }

  function addTextItem() {
    const item = makeTextItem(activeSituation.label, activeOverlay.items.length);
    setTextOverlays((current) => {
      const overlay = current[activeSituationId] ?? defaultOverlay(activeSituation.label);
      return {
        ...current,
        [activeSituationId]: { mode: "custom", items: [...overlay.items, item].slice(0, 6) }
      };
    });
    setActiveTextItemId(item.id);
  }

  function removeActiveItem() {
    if (!activeItem) return;
    setTextOverlays((current) => {
      const overlay = current[activeSituationId] ?? defaultOverlay(activeSituation.label);
      const nextItems = overlay.items.filter((item) => item.id !== activeItem.id);
      const fallbackItems = nextItems.length ? nextItems : [makeTextItem(activeSituation.label, 0)];
      setActiveTextItemId(fallbackItems[0].id);
      return { ...current, [activeSituationId]: { mode: "custom", items: fallbackItems } };
    });
  }

  function startDrag(event: PointerEvent<HTMLButtonElement>, item: TextOverlayItem) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setActiveTextItemId(item.id);
    if (activeOverlay.mode !== "custom") enableCustomOverlay();
    moveItemToPointer(event, item.id);
  }

  function moveItemToPointer(event: PointerEvent<HTMLButtonElement>, itemId: string) {
    const rect = event.currentTarget.parentElement?.getBoundingClientRect();
    if (!rect) return;
    const x = ((event.clientX - rect.left) / rect.width) * CANVAS_SIZE;
    const y = ((event.clientY - rect.top) / rect.height) * CANVAS_SIZE;
    setTextOverlays((current) => {
      const overlay = current[activeSituationId] ?? defaultOverlay(activeSituation.label);
      return {
        ...current,
        [activeSituationId]: {
          mode: "custom",
          items: overlay.items.map((item) => (item.id === itemId ? { ...item, x: clamp(Math.round(x), 0, 320), y: clamp(Math.round(y), 0, 320) } : item))
        }
      };
    });
  }

  const isGenerating = job?.status === "queued" || job?.status === "generating_final";
  const finalAssets = job?.finalAssets ?? [];
  const selectedCount = selectedSituationIds.length;

  return (
    <main className="site-shell">
      <TopNav active="create" />

      <section className="hero-section">
        <div className="hero-copy">
          <span className="eyebrow">Sketch to KakaoTalk GIF</span>
          <h1>내 캐릭터 스케치를 움직이는 이모티콘 키트로</h1>
          <p>원본 캐릭터의 정체성을 유지하면서 상황별 GIF와 직접 배치한 문구를 한 번에 생성합니다.</p>
        </div>
        <div className="hero-status-card">
          <Sparkles size={22} />
          <strong>{job ? statusText[job.status] : "Ready"}</strong>
          <span>{job ? `${job.finalCount}개 이모티콘 작업` : "스케치를 업로드해 시작하세요"}</span>
        </div>
      </section>

      <section className="workflow-strip" aria-label="생성 단계">
        {["스케치 업로드", "스타일 선택", "문구 편집", "GIF 다운로드"].map((item, index) => (
          <div className="workflow-card" key={item}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{item}</strong>
          </div>
        ))}
      </section>

      <section className="main content-stack">
        {!job && (
          <>
            <section className="panel upload-grid feature-panel">
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
                <div className="section-label">스타일 프리셋</div>
                <div className="style-grid">
                  {STYLE_PRESETS.map((style) => (
                    <button className={`style-button ${styleId === style.id ? "active" : ""}`} key={style.id} type="button" onClick={() => setStyleId(style.id)}>
                      {style.label}
                    </button>
                  ))}
                </div>
                <div className="section-label">글꼴 스타일</div>
                <div className="style-grid">
                  {LETTERING_STYLES.map((style) => (
                    <button className={`style-button ${letteringStyleId === style.id ? "active" : ""}`} key={style.id} type="button" onClick={() => setLetteringStyleId(style.id)}>
                      {style.label}
                    </button>
                  ))}
                </div>
                <div className="section-label">이모지 상황 선택</div>
                <div className="selection-summary">
                  <span>
                    {selectedCount}개 선택됨 / 최대 {MAX_SELECTED_SITUATIONS}개 · 직접 배치 {customOverlayCount}개
                  </span>
                  <button className="text-button" type="button" onClick={() => setSelectedSituationIds(FINAL_SITUATIONS.map((situation) => situation.id))}>
                    전체 선택
                  </button>
                  <button className="text-button" type="button" onClick={() => setSelectedSituationIds([FINAL_SITUATIONS[0].id])}>
                    기본 1개
                  </button>
                </div>
                <div className="situation-grid">
                  {FINAL_SITUATIONS.map((situation) => {
                    const checked = selectedSituationIds.includes(situation.id);
                    const custom = textOverlays[situation.id]?.mode === "custom";
                    return (
                      <label className={`situation-option ${checked ? "active" : ""} ${activeSituationId === situation.id ? "focused" : ""}`} key={situation.id}>
                        <input type="checkbox" checked={checked} onChange={() => toggleSituation(situation.id)} />
                        <button className="situation-picker" type="button" onClick={() => setActiveSituationId(situation.id)}>
                          {situation.label}
                          {custom ? " ✎" : ""}
                        </button>
                      </label>
                    );
                  })}
                </div>
                <div className="actions">
                  <button className="primary" type="button" disabled={busy} onClick={createGenerationJob}>
                    {busy ? "시작 중" : `GIF ${selectedCount}개 생성`}
                  </button>
                  <Link className="secondary" href="/archive">
                    보관함 보기
                  </Link>
                </div>
                {error ? <div className="error">{error}</div> : null}
              </div>
            </section>

            <section className="panel text-editor-panel">
              <div className="editor-heading">
                <div>
                  <div className="section-label">문구 위치/회전 편집</div>
                  <h3>{activeSituation.label}</h3>
                  <p className="status">선택한 상황마다 문구를 직접 추가하고 드래그해서 위치를 정할 수 있습니다.</p>
                </div>
                <div className="actions compact-actions">
                  <button className="secondary" type="button" onClick={() => enableCustomOverlay()}>
                    직접 배치 사용
                  </button>
                  <button className="secondary" type="button" onClick={() => resetOverlay()}>
                    <RotateCcw size={16} /> 기본값
                  </button>
                </div>
              </div>

              <div className="editor-grid">
                <div className="text-canvas" aria-label="텍스트 위치 편집 캔버스">
                  {previewUrl ? <img src={previewUrl} alt="텍스트 배치 참고용 스케치" /> : <div className="canvas-placeholder">320×320 GIF 미리보기 영역</div>}
                  {activeOverlay.items.map((item) => (
                    <button
                      className={`text-chip ${activeItem?.id === item.id ? "active" : ""}`}
                      key={item.id}
                      type="button"
                      style={{
                        left: `${(item.x / CANVAS_SIZE) * 100}%`,
                        top: `${(item.y / CANVAS_SIZE) * 100}%`,
                        transform: `translate(-50%, -50%) rotate(${item.rotation}deg)`,
                        fontSize: `${item.fontSize}px`,
                        color: item.color
                      }}
                      onPointerDown={(event) => startDrag(event, item)}
                      onPointerMove={(event) => {
                        if (event.buttons === 1 && activeTextItemId === item.id) moveItemToPointer(event, item.id);
                      }}
                    >
                      {item.text}
                    </button>
                  ))}
                </div>

                <div className="text-controls">
                  <div className="mode-row">
                    <button className={`type-button ${activeOverlay.mode !== "custom" ? "active" : ""}`} type="button" onClick={() => resetOverlay()}>
                      자동 라벨
                    </button>
                    <button className={`type-button ${activeOverlay.mode === "custom" ? "active" : ""}`} type="button" onClick={() => enableCustomOverlay()}>
                      직접 배치
                    </button>
                  </div>
                  <div className="text-item-list">
                    {activeOverlay.items.map((item) => (
                      <button className={`text-item-button ${activeItem?.id === item.id ? "active" : ""}`} key={item.id} type="button" onClick={() => setActiveTextItemId(item.id)}>
                        {item.text}
                      </button>
                    ))}
                  </div>
                  {activeItem ? (
                    <div className="control-stack">
                      <label>
                        문구
                        <input value={activeItem.text} maxLength={24} onChange={(event) => updateActiveItem({ text: event.target.value })} />
                      </label>
                      <label>
                        X 위치 {Math.round(activeItem.x)}
                        <input type="range" min="0" max="320" value={activeItem.x} onChange={(event) => updateActiveItem({ x: Number(event.target.value) })} />
                      </label>
                      <label>
                        Y 위치 {Math.round(activeItem.y)}
                        <input type="range" min="0" max="320" value={activeItem.y} onChange={(event) => updateActiveItem({ y: Number(event.target.value) })} />
                      </label>
                      <label>
                        회전 {Math.round(activeItem.rotation)}°
                        <input type="range" min="-45" max="45" value={activeItem.rotation} onChange={(event) => updateActiveItem({ rotation: Number(event.target.value) })} />
                      </label>
                      <label>
                        크기 {Math.round(activeItem.fontSize)}px
                        <input type="range" min="18" max="72" value={activeItem.fontSize} onChange={(event) => updateActiveItem({ fontSize: Number(event.target.value) })} />
                      </label>
                      <label>
                        색상
                        <input type="color" value={activeItem.color} onChange={(event) => updateActiveItem({ color: event.target.value })} />
                      </label>
                      <div className="actions compact-actions">
                        <button className="secondary" type="button" onClick={addTextItem}>
                          <Plus size={16} /> 문구 추가
                        </button>
                        <button className="secondary" type="button" onClick={removeActiveItem}>
                          <Trash2 size={16} /> 삭제
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
          </>
        )}

        {job && (
          <section className="panel result-panel">
            {isGenerating && (
              <div className="generation-state">
                <Loader2 className="spin" aria-label="생성 중" />
                <strong>{statusText[job.status]}</strong>
                <p className="status">첨부 스케치를 Gemini Vision으로 분석한 뒤 선택한 {job.finalCount}개 상황의 스프라이트 GIF를 생성합니다. 이 화면은 자동으로 갱신됩니다.</p>
              </div>
            )}

            {job.status === "completed" && finalAssets.length > 0 && (
              <>
                <div className="asset-grid result-grid">
                  {finalAssets.map((asset) => (
                    <div className="asset-card" key={asset.id}>
                      <img src={asset.url} alt={asset.displayText} />
                      <div className="asset-meta">
                        <span>
                          {asset.situationLabel} · {asset.displayText}
                        </span>
                        <span>GIF</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="actions">
                  <a className="secondary" href={`/api/jobs/${job.id}/download`}>
                    <Download size={18} /> ZIP 다운로드
                  </a>
                  <Link className="secondary" href="/archive">
                    보관함에서 보기
                  </Link>
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

function TopNav({ active }: { active: "create" | "archive" }) {
  return (
    <header className="top-nav">
      <Link className="brand-link" href="/">
        <span className="logo">I</span>
        <span>Imoji</span>
      </Link>
      <nav>
        <Link className={active === "create" ? "active" : ""} href="/">
          생성하기
        </Link>
        <Link className={active === "archive" ? "active" : ""} href="/archive">
          보관함
        </Link>
      </nav>
    </header>
  );
}

function makeTextItem(text: string, index: number): TextOverlayItem {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    text,
    x: 160,
    y: clamp(266 - index * 42, 40, 300),
    rotation: 0,
    fontSize: 42,
    color: "#261f19"
  };
}

function defaultOverlay(text: string): SituationTextOverlay {
  return {
    mode: "default",
    items: [makeTextItem(text, 0)]
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
