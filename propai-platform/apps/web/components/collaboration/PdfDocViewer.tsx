"use client";

/**
 * SP4-2 PDF 인라인 뷰어 — react-pdf(pdf.js). 회의방 자료교환 PDF를 플랫폼 내부에서 본다.
 *
 * 텍스트·주석 레이어는 끄고 캔버스 페이지만 렌더(워커·CSS 의존 최소화). 워커는 번들된 pdfjs-dist를
 * 동일 오리진으로 로드(CSP 안전). 클라이언트 전용 — 모달에서 dynamic(ssr:false)로 임포트한다.
 */

import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

// 워커는 설치된 pdfjs-dist와 동일 버전을 CDN에서 로드(Turbopack의 import.meta.url 번들 미해결 회피).
// 워커 로드 실패 시 onLoadError로 graceful degrade(상단 '새 탭'). prod CSP가 unpkg를 막으면
// public/ 동일오리진 워커로 전환(핸드오프 참고).
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export function PdfDocViewer({ url }: { url: string }) {
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState(false);

  if (error) {
    return (
      <p className="py-8 text-center text-sm text-[var(--text-hint)]">
        PDF 미리보기를 불러오지 못했습니다 — 상단 “새 탭”으로 열어주세요.
      </p>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <Document
        file={url}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        onLoadError={() => setError(true)}
        loading={<p className="py-8 text-xs text-[var(--text-hint)]">PDF 불러오는 중…</p>}
        error={<p className="py-8 text-xs text-[var(--status-error)]">PDF 로드 실패</p>}
      >
        <Page
          pageNumber={page}
          width={740}
          renderTextLayer={false}
          renderAnnotationLayer={false}
        />
      </Document>
      {numPages > 1 && (
        <div className="flex items-center gap-3 text-xs">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded-md border border-[var(--line)] px-3 py-1 font-bold text-[var(--text-secondary)] disabled:opacity-40"
          >
            이전
          </button>
          <span className="font-mono text-[var(--text-secondary)]">
            {page} / {numPages}
          </span>
          <button
            type="button"
            disabled={page >= numPages}
            onClick={() => setPage((p) => Math.min(numPages, p + 1))}
            className="rounded-md border border-[var(--line)] px-3 py-1 font-bold text-[var(--text-secondary)] disabled:opacity-40"
          >
            다음
          </button>
        </div>
      )}
    </div>
  );
}
