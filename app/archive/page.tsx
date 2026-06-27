"use client";

/* eslint-disable @next/next/no-img-element */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronLeft, ChevronRight, Download, Loader2, RefreshCcw } from "lucide-react";

const PAGE_SIZE = 8;

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
  styleLabel: string;
  letteringStyleLabel: string;
  error?: string;
  finalAssets: ClientAsset[];
  finalCount: number;
  createdAt?: string;
  updatedAt?: string;
};

const statusText: Record<ClientJob["status"], string> = {
  queued: "대기",
  generating_final: "생성 중",
  completed: "완료",
  failed: "실패"
};

export default function ArchivePage() {
  const [jobs, setJobs] = useState<ClientJob[]>([]);
  const [expandedJobId, setExpandedJobId] = useState<string>("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadJobs();
  }, []);

  const sortedJobs = useMemo(
    () => [...jobs].sort((a, b) => new Date(b.createdAt ?? 0).getTime() - new Date(a.createdAt ?? 0).getTime()),
    [jobs]
  );
  const totalPages = Math.max(1, Math.ceil(sortedJobs.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedJobs = sortedJobs.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  async function loadJobs() {
    setLoading(true);
    setError("");
    const response = await fetch("/api/jobs", { cache: "no-store" });
    const data = await response.json();
    setLoading(false);

    if (!response.ok) {
      setError(data.error ?? "보관함을 불러오지 못했습니다.");
      return;
    }

    setJobs(data.jobs ?? []);
  }

  function toggleExpanded(jobId: string) {
    setExpandedJobId((current) => (current === jobId ? "" : jobId));
  }

  return (
    <main className="site-shell archive-shell">
      <TopNav active="archive" />

      <section className="main content-stack">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>보관함</h2>
          <button className="secondary dark-secondary" type="button" onClick={() => void loadJobs()} disabled={loading}>
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCcw size={16} />}
            새로고침
          </button>
        </div>
        <section className="panel archive-page-panel">
          <div className="archive-table-head">
            <span>No.</span>
            <span>제목</span>
            <span>날짜</span>
            <span>상태</span>
            <span>보기</span>
          </div>

          {loading ? <p className="status padded-status">보관함을 불러오는 중입니다.</p> : null}
          {error ? <div className="error">{error}</div> : null}

          {!loading && !sortedJobs.length ? (
            <div className="empty-state">
              <strong>아직 생성한 작업이 없습니다.</strong>
              <p>첫 스케치를 업로드하고 나만의 이모티콘 세트를 만들어보세요.</p>
              <Link className="primary" href="/">
                생성하러 가기
              </Link>
            </div>
          ) : null}

          <div className="archive-list">
            {pagedJobs.map((item, index) => {
              const displayNumber = sortedJobs.length - ((currentPage - 1) * PAGE_SIZE + index);
              const expanded = expandedJobId === item.id;
              return (
                <article className={`archive-item ${expanded ? "expanded" : ""}`} key={item.id}>
                  <button className="archive-row" type="button" onClick={() => toggleExpanded(item.id)} aria-expanded={expanded}>
                    <span className="archive-no">{displayNumber}</span>
                    <span className="archive-title">
                      <strong>{makeTitle(item)}</strong>
                      <small>{item.finalCount}개 · {item.letteringStyleLabel}</small>
                    </span>
                    <span>{formatDate(item.createdAt)}</span>
                    <span className={`status-pill ${item.status}`}>{statusText[item.status]}</span>
                    <ChevronDown className="archive-chevron" size={18} />
                  </button>

                  {expanded ? (
                    <div className="archive-expanded">
                      {item.status === "completed" && item.finalAssets.length ? (
                        <>
                          <div className="asset-grid result-grid archive-asset-grid">
                            {item.finalAssets.map((asset) => (
                              <div className="asset-card" key={asset.id}>
                                <img src={asset.url} alt={asset.displayText} />
                                <div className="asset-meta">
                                  <span>{asset.situationLabel}</span>
                                  <span>{asset.displayText}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                          <div className="actions">
                            <a className="secondary" href={`/api/jobs/${item.id}/download`}>
                              <Download size={18} /> ZIP 다운로드
                            </a>
                          </div>
                        </>
                      ) : (
                        <p className="status">{item.error ?? "완료된 GIF가 아직 없습니다."}</p>
                      )}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>

          {sortedJobs.length > PAGE_SIZE ? (
            <div className="pagination">
              <button className="secondary" type="button" disabled={currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
                <ChevronLeft size={16} /> 이전
              </button>
              <span>{currentPage} / {totalPages}</span>
              <button className="secondary" type="button" disabled={currentPage >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>
                다음 <ChevronRight size={16} />
              </button>
            </div>
          ) : null}
        </section>
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

function makeTitle(job: ClientJob) {
  return `${job.styleLabel} 이모티콘 세트`;
}

function formatDate(value?: string) {
  if (!value) return "날짜 없음";
  return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
