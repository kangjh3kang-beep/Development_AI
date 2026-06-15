"use client";

/**
 * SP3 회의방 자료교환 — 협력업체 업로드자료 업로드/목록/삭제 + 정직 8엔진 결과·표기용 심의상태.
 *
 * 정직 type-routing: 설계파일(DXF/IFC)은 업로드 시 8엔진 자동검증(audit_summary 표시), 문서(PDF 등)는
 * '자동검증 미지원 형식'이며 심의는 사람(심의자) 주도 review_state(요청→확인→처리완료) 표기용 — 자동
 * 판정이 아님을 배지로 명시(과대표기 금지).
 */

import { useEffect, useRef, useState } from "react";
import { useCollaborationStore, type CollabDocument } from "@/store/use-collaboration-store";
import { DocumentViewerModal } from "@/components/collaboration/DocumentViewerModal";
import { ReviewCommentThread } from "@/components/collaboration/ReviewCommentThread";
import { useReviewCommentStore } from "@/store/use-review-comment-store";
import {
  REVIEW_CATEGORIES,
  categoryLabel,
  isDesignKind,
  purposeLabel,
  auditStatusBadge,
  reviewStateBadge,
  nextReviewState,
  formatBytes,
  type StatusTone,
} from "@/lib/collaboration";

const TONE_CLASS: Record<StatusTone, string> = {
  ok: "text-[var(--status-success)]",
  warn: "text-[var(--status-warning)]",
  muted: "text-[var(--text-hint)]",
};

function AuditView({ doc }: { doc: CollabDocument }) {
  if (!isDesignKind(doc.doc_kind)) {
    return (
      <span className="text-[11px] text-[var(--text-hint)]">
        문서형식 — 8엔진 자동검증 미지원(심의자 표기용)
      </span>
    );
  }
  const badge = auditStatusBadge(doc.audit_status);
  const s = (doc.audit_summary ?? {}) as Record<string, unknown>;
  const verdict = typeof s.verdict === "string" ? s.verdict : null;
  const findings = typeof s.findings_count === "number" ? s.findings_count : null;
  const run = typeof s.engines_run === "number" ? s.engines_run : null;
  return (
    <span className="text-[11px]">
      {badge && <span className={`font-black ${TONE_CLASS[badge.tone]}`}>{badge.label}</span>}
      {doc.audit_status === "completed" && (
        <span className="text-[var(--text-hint)]">
          {" · "}판정 {verdict ?? "—"}
          {findings != null ? ` · 지적 ${findings}` : ""}
          {run != null ? ` · 엔진 ${run} 적용` : ""}
        </span>
      )}
    </span>
  );
}

export function ProjectCollaborationDocumentExchange({ projectId }: { projectId: string }) {
  const { documents, docLoading, docError, loadDocuments, uploadDocument, deleteDocument, setDocReviewState } =
    useCollaborationStore();

  const [category, setCategory] = useState("");
  const [purpose, setPurpose] = useState<"storage" | "analysis">("storage");
  const [viewerDoc, setViewerDoc] = useState<CollabDocument | null>(null);
  const [openThreads, setOpenThreads] = useState<Record<string, boolean>>({});
  const commentsByDoc = useReviewCommentStore((s) => s.commentsByDoc);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void loadDocuments(projectId);
  }, [projectId, loadDocuments]);

  const submit = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    await uploadDocument(projectId, f, category || undefined, purpose);
    if (fileRef.current) fileRef.current.value = "";
    setCategory("");
  };

  return (
    <section
      data-testid="collab-docs"
      className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6"
    >
      <h3 className="mb-1 text-sm font-black text-[var(--text-primary)]">자료교환 (협력업체 업로드자료)</h3>
      <p className="mb-4 text-[11px] text-[var(--text-hint)]">
        설계파일(DXF/IFC)은 업로드 시 8엔진 자동검증을 시도하고, 그 외 문서는 심의자가 직접 검토상태를
        표기합니다(자동판정 아님).
      </p>

      {/* 업로드 */}
      <div data-testid="collab-doc-upload" className="mb-2 flex flex-wrap items-center gap-2">
        {/* 용도: 분석용(8엔진·DXF/IFC만) vs 저장·공유용(무제한) */}
        <div className="inline-flex overflow-hidden rounded-lg border border-[var(--line)] text-[11px] font-bold">
          {(["storage", "analysis"] as const).map((p) => (
            <button
              key={p}
              type="button"
              data-testid={`collab-doc-purpose-${p}`}
              onClick={() => setPurpose(p)}
              className={`px-3 py-1.5 ${
                purpose === p
                  ? "bg-[var(--accent-strong)] text-white"
                  : "bg-[var(--surface)] text-[var(--text-secondary)]"
              }`}
            >
              {p === "storage" ? "저장·공유용" : "분석용(8엔진)"}
            </button>
          ))}
        </div>
        <input
          ref={fileRef}
          data-testid="collab-doc-file"
          type="file"
          className="text-xs text-[var(--text-secondary)]"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-xs"
        >
          <option value="">심의 카테고리(선택)</option>
          {REVIEW_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {categoryLabel(c)}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="collab-doc-submit"
          disabled={docLoading}
          onClick={submit}
          className="rounded-lg bg-[var(--accent-strong)] px-4 py-1.5 text-[11px] font-black uppercase tracking-widest text-white disabled:opacity-40"
        >
          {docLoading ? "업로드 중…" : "업로드"}
        </button>
      </div>
      {purpose === "analysis" && (
        <p className="mb-4 text-[11px] text-[var(--text-hint)]">
          ※ 분석용은 DXF/IFC 설계파일만 업로드되어 8엔진 자동검증을 실행합니다(그 외 형식은 거부).
        </p>
      )}

      {/* 목록 */}
      {documents.length === 0 ? (
        <p className="text-xs text-[var(--text-hint)]">
          {docLoading ? "불러오는 중…" : "아직 업로드된 자료가 없습니다."}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {documents.map((d) => {
            const rb = reviewStateBadge(d.review_state);
            const next = nextReviewState(d.review_state);
            return (
              <li
                key={d.id}
                data-testid="collab-doc-item"
                className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-bold text-[var(--text-primary)]">
                      {d.original_filename}
                    </p>
                    <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">
                      {formatBytes(d.size_bytes)}
                      {d.category ? ` · ${categoryLabel(d.category)}` : ""}
                      {` · ${isDesignKind(d.doc_kind) ? "설계파일" : "문서"}`}
                      {` · ${purposeLabel(d.purpose)}`}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`text-[11px] font-black ${TONE_CLASS[rb.tone]}`}>{rb.label}</span>
                    {next && (
                      <button
                        type="button"
                        onClick={() => void setDocReviewState(projectId, d.id, next)}
                        className="rounded-md border border-[var(--line)] px-2 py-1 text-[10px] font-bold text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]"
                      >
                        {next === "acknowledged" ? "확인" : "처리완료"}
                      </button>
                    )}
                    {d.file_url && (
                      <button
                        type="button"
                        data-testid="collab-doc-preview"
                        onClick={() => setViewerDoc(d)}
                        className="text-[10px] font-bold text-[var(--accent-strong)]"
                      >
                        미리보기
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void deleteDocument(projectId, d.id)}
                      className="text-[10px] font-bold text-[var(--status-error)]"
                    >
                      삭제
                    </button>
                  </div>
                </div>
                <div className="mt-1">
                  <AuditView doc={d} />
                </div>
                <div className="mt-1">
                  <button
                    type="button"
                    data-testid="collab-doc-comments-toggle"
                    onClick={() =>
                      setOpenThreads((m) => ({ ...m, [d.id]: !m[d.id] }))
                    }
                    className="text-[10px] font-bold text-[var(--accent-strong)]"
                  >
                    {(() => {
                      const n = (commentsByDoc[d.id] ?? []).filter(
                        (cm) => cm.status === "active",
                      ).length;
                      const open = !!openThreads[d.id];
                      return `의견교환${n > 0 ? ` (${n})` : ""} ${open ? "▲" : "▼"}`;
                    })()}
                  </button>
                  {openThreads[d.id] && (
                    <ReviewCommentThread projectId={projectId} docId={d.id} />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {docError && (
        <p data-testid="collab-doc-error" className="mt-2 text-xs text-[var(--status-error)]">
          {docError}
        </p>
      )}

      <DocumentViewerModal doc={viewerDoc} onClose={() => setViewerDoc(null)} />
    </section>
  );
}
