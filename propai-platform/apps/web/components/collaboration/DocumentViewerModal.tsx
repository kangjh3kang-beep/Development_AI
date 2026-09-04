"use client";

/**
 * SP4-2 플랫폼 내부 문서 뷰어 모달 — 형식별 라우팅(이미지/PDF/그 외 다운로드).
 *
 * 이미지는 <img>, PDF는 react-pdf(dynamic, ssr:false). 미지원 형식은 정직하게 다운로드 안내.
 * 설계파일(DXF)의 CAD 뷰어는 SP4-3에서 design 분기로 추가된다.
 */

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { DISMISS_Z, useDismissible } from "@/lib/satong-dismiss";
import { useModalFocus } from "@/hooks/useModalFocus";
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
  // 포털은 클라이언트에서만 — SSR 단계엔 `document` 가 없다(ConfirmDeleteModal 과 같은 관례).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // ESC 로 닫기 — 조정기가 **열린 표면 중 가장 위 하나만** 닫는다.
  // ★이 뷰어 안에서 삭제 확인창(ConfirmDeleteModal)이 열릴 수 있다. 그때 ESC 는 확인창만
  //   닫아야 하므로 확인창은 `nestedOverModal`, 이 뷰어는 `appModal` 로 등록한다.
  useDismissible(DISMISS_Z.appModal, Boolean(doc) && mounted, onClose);

  // ★포커스 생명주기 — 미룬 사유였던 *"iframe 포커스 정책"* 은 **실측으로 기각**했다:
  //   이 뷰어엔 `<iframe>` 이 **0개**다(이미지=<img>, PDF=react-pdf, DXF=CAD 뷰어 — 전부 캔버스/DOM).
  //   내부 스크롤 컨테이너는 포커스 대상이 아니라 트랩에 영향이 없다.
  //   ★남은 진짜 제약은 **트랩 중첩**이다 — 훅은 `useDismissible` 과 달리 z 조정이 없어
  //     포커스 배선된 모달 안에 또 배선된 모달이 열리면 두 트랩이 겹친다.
  //     현재 이 서브트리엔 `ConfirmDeleteModal` 이 없다(실측). 아래 계약 테스트가 그 침범을 막는다.
  const bodyRef = useRef<HTMLDivElement>(null);
  useModalFocus(bodyRef, Boolean(doc) && mounted);

  if (!doc || !mounted) return null;
  const url = doc.file_url ?? "";
  const name = doc.original_filename;

  /**
   * ★`createPortal` + `z-[1000]` — 종전에는 인라인 렌더 + `z-[120]` 이었고,
   *   그래서 **닫기 버튼이 페이지 요소에 덮였다**(실측 2026-08-16).
   *
   *   `fixed` 는 조상에 `transform`·`filter`·`z-index` 가 있으면 그 **쌓임맥락 안에**
   *   갇힌다. 이 모달은 문서교환 패널 내부에 인라인으로 렌더돼, 자기 `z-[120]` 이
   *   페이지 전역과 겨루지 못했다. 실측: 닫기 버튼 중앙에서 `elementFromPoint` 가
   *   심의 카테고리 칩(`<label>`)을 반환했다 — 사용자가 ✕ 를 눌러도 칩이 먹는다.
   *
   *   ★좌표가 겹치는지가 아니라 **무엇이 위에 그려지는지**로 판정했다
   *   (`rect` 교차가 아니라 `elementFromPoint` — CLAUDE.md §D.18).
   *
   *   층위·포털 관례는 `components/common/ConfirmDeleteModal.tsx` 를 따른다(새 규약 발명 금지).
   */
  return createPortal(
    <div
      data-testid="doc-viewer-modal"
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        ref={bodyRef}
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
    </div>,
    document.body,
  );
}
