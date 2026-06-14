"use client";

/**
 * SP4-2 플랫폼 내부 문서 뷰어 모달 — 형식별 라우팅(이미지/PDF/그 외 다운로드).
 *
 * 이미지는 <img>, PDF는 react-pdf(dynamic, ssr:false). 미지원 형식은 정직하게 다운로드 안내.
 * 설계파일(DXF)의 CAD 뷰어는 SP4-3에서 design 분기로 추가된다.
 */

import dynamic from "next/dynamic";
import type { CollabDocument } from "@/store/use-collaboration-store";
import { CadDocViewer } from "./CadDocViewer";

const PdfDocViewer = dynamic(
  () => import("./PdfDocViewer").then((m) => m.PdfDocViewer),
  { ssr: false, loading: () => <p className="py-8 text-xs text-[var(--text-hint)]">뷰어 로딩…</p> },
);

function isImage(ct: string | null | undefined, name: string): boolean {
  return (ct ?? "").startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(name);
}
function isPdf(ct: string | null | undefined, name: string): boolean {
  return (ct ?? "").includes("pdf") || /\.pdf$/i.test(name);
}
function isDxf(name: string): boolean {
  return /\.dxf$/i.test(name);
}

export function DocumentViewerModal({
  doc,
  onClose,
}: {
  doc: CollabDocument | null;
  onClose: () => void;
}) {
  if (!doc) return null;
  const url = doc.file_url ?? "";
  const name = doc.original_filename;

  return (
    <div
      data-testid="doc-viewer-modal"
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-3">
          <p className="truncate text-sm font-black text-[var(--text-primary)]">{name}</p>
          <div className="flex shrink-0 items-center gap-3">
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] font-bold text-[var(--accent-strong)]"
              >
                새 탭
              </a>
            )}
            <button
              type="button"
              aria-label="닫기"
              data-testid="doc-viewer-close"
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--line)] text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="flex flex-1 items-center justify-center overflow-auto p-4">
          {!url ? (
            <p className="py-8 text-sm text-[var(--text-hint)]">파일 URL이 없습니다.</p>
          ) : isImage(doc.content_type, name) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={name} className="max-h-[78vh] max-w-full rounded-lg" />
          ) : isPdf(doc.content_type, name) ? (
            <PdfDocViewer url={url} />
          ) : isDxf(name) ? (
            <CadDocViewer projectId={doc.project_id} docId={doc.id} />
          ) : (
            <div className="py-8 text-center text-sm text-[var(--text-hint)]">
              이 형식은 내장 미리보기를 지원하지 않습니다.
              <br />
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block font-bold text-[var(--accent-strong)]"
              >
                다운로드 / 새 탭에서 열기
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
