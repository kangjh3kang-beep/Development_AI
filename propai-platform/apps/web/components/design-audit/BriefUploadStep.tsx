"use client";

/**
 * BriefUploadStep — 설계심사(DA-7) 2단계 ⑵개요: 건축개요 PDF/텍스트 업로드 → 필드 추출.
 *
 * POST /design-audit/extract-brief (multipart FormData: file?, text?)를 호출해
 * 개요 필드(BriefField[])를 추출하고 부모(DesignAuditWorkspace)에 전달한다.
 * 필드 편집·출처 배지는 ParamConfirmStep이 담당(이 컴포넌트는 업로드/추출만).
 *
 * 정직성 원칙:
 *  - 추출 결과가 비어 있으면 "추출된 필드 없음"을 그대로 표기(가짜 필드 생성 금지).
 *  - 서버 오류는 메시지 그대로 노출(임의 성공 처리 금지).
 *
 * apiClient v1 POST 패턴(lib/api-client.ts) — FormData body는 Content-Type 자동 생략.
 * 디자인 토큰(CSS 변수)만 사용.
 */

import { useRef, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* ── 공유 타입(설계심사 개요 필드) — ParamConfirmStep·Workspace가 import ── */

export type BriefFieldSource = "extracted" | "user";

export interface BriefField {
  key: string;
  label: string;
  /** 편집 가능한 현재 값(문자열 보관 — 숫자도 입력 그대로). */
  value: string;
  /** 추출 직후 원본 값 — 사용자가 원래 값으로 되돌리면 source가 extracted로 복귀. */
  extractedValue: string;
  unit?: string | null;
  /** 개요서 원문 인용(추출 근거) — quote 툴팁에 사용. 없으면 미표기. */
  quote?: string | null;
  source: BriefFieldSource;
}

/** 백엔드 extract-brief 응답 필드(방어적 — 표기 변형 graceful 수용). */
interface ExtractBriefApiField {
  key?: string | null;
  name?: string | null;
  label?: string | null;
  value?: string | number | null;
  unit?: string | null;
  quote?: string | null;
  source_quote?: string | null;
}

export interface ExtractBriefResponse {
  ok?: boolean;
  message?: string | null;
  brief_id?: string | null;
  fields?: ExtractBriefApiField[] | null;
}

/** 응답 필드 정규화 — 비정상 항목은 건너뛴다(가짜값 금지). */
export function normalizeBriefFields(raw: ExtractBriefResponse | null): BriefField[] {
  const list = Array.isArray(raw?.fields) ? raw.fields : [];
  const out: BriefField[] = [];
  list.forEach((f, i) => {
    if (!f || typeof f !== "object") return;
    const key = String(f.key ?? f.name ?? `field_${i}`).trim() || `field_${i}`;
    const label = String(f.label ?? f.key ?? f.name ?? `항목 ${i + 1}`).trim() || `항목 ${i + 1}`;
    // null/undefined 값은 빈 문자열(미추출) — 사용자가 직접 채울 수 있게 유지.
    const value = f.value == null ? "" : String(f.value);
    const rawQuote = f.quote ?? f.source_quote;
    const quote =
      typeof rawQuote === "string" && rawQuote.trim() ? rawQuote.trim() : null;
    out.push({
      key,
      label,
      value,
      extractedValue: value,
      unit: typeof f.unit === "string" ? f.unit : null,
      quote,
      source: "extracted",
    });
  });
  return out;
}

/** ApiClientError payload(detail/message) 우선 추출 — 없으면 fallback. */
export function apiErrorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    const p = e.payload as { detail?: unknown; message?: unknown } | null;
    if (typeof p?.detail === "string" && p.detail.trim()) return p.detail;
    if (typeof p?.message === "string" && p.message.trim()) return p.message;
    return e.message || fallback;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20MB — 과대 업로드 클라이언트 차단

export function BriefUploadStep({
  disabled = false,
  onExtracted,
}: {
  disabled?: boolean;
  /** 추출 성공 시 정규화된 필드와 메타(brief_id·서버 메시지)를 부모에 전달. */
  onExtracted: (
    fields: BriefField[],
    meta: { briefId: string | null; message: string | null },
  ) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  function handlePickFile(picked: File | null) {
    setError("");
    if (!picked) {
      setFile(null);
      return;
    }
    if (picked.size > MAX_FILE_BYTES) {
      setError("파일이 너무 큽니다(최대 20MB). 텍스트 직접 입력을 이용하세요.");
      return;
    }
    setFile(picked);
  }

  async function extract() {
    if (!file && !text.trim()) {
      setError("개요 PDF를 업로드하거나 개요 텍스트를 입력하세요.");
      return;
    }
    setLoading(true);
    setError("");
    setInfo("");
    try {
      const fd = new FormData();
      if (file) fd.append("file", file);
      if (text.trim()) fd.append("text", text.trim());
      const r = await apiClient.post<ExtractBriefResponse>(
        "/design-audit/extract-brief",
        { body: fd, timeoutMs: 180_000 },
      );
      const fields = normalizeBriefFields(r ?? null);
      const serverMsg = typeof r?.message === "string" ? r.message : null;
      if (r?.ok === false) {
        // 서버가 명시적으로 실패를 알린 경우 — 메시지 그대로(정직).
        setError(serverMsg || "개요 추출에 실패했습니다. 파일 내용을 확인해 주세요.");
        return;
      }
      onExtracted(fields, { briefId: r?.brief_id ?? null, message: serverMsg });
      setInfo(
        fields.length > 0
          ? `${fields.length}개 필드를 추출했습니다 — 아래 그리드에서 확인·수정하세요.`
          : serverMsg || "추출된 필드가 없습니다 — 개요 내용을 확인하거나 다음 단계로 진행하세요.",
      );
    } catch (e) {
      setError(apiErrorMessage(e, "개요 추출에 실패했습니다. 잠시 후 다시 시도하세요."));
    } finally {
      setLoading(false);
    }
  }

  const busy = disabled || loading;

  return (
    <div className="grid gap-3">
      {/* 파일 업로드 슬롯 */}
      <div className="rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,application/pdf,.txt,text/plain"
            className="hidden"
            disabled={busy}
            onChange={(e) => handlePickFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
          >
            📄 건축개요 PDF 선택
          </button>
          {file ? (
            <span className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
              <span className="max-w-[240px] truncate font-semibold text-[var(--text-primary)]" title={file.name}>
                {file.name}
              </span>
              <span className="text-[var(--text-hint)]">{(file.size / 1024 / 1024).toFixed(1)}MB</span>
              <button
                type="button"
                onClick={() => {
                  setFile(null);
                  if (fileRef.current) fileRef.current.value = "";
                }}
                disabled={busy}
                title="선택한 파일 제거"
                className="text-[var(--status-error)] disabled:opacity-50"
              >
                ✕
              </button>
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-hint)]">
              사업계획·건축개요 PDF(또는 텍스트)에서 면적·층수·세대수 등 설계 파라미터를 추출합니다.
            </span>
          )}
        </div>
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowText((v) => !v)}
            className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline"
          >
            {showText ? "− 개요 텍스트 직접 입력 닫기" : "+ 개요 텍스트 직접 입력 (PDF 없이)"}
          </button>
          {showText && (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={5}
              disabled={busy}
              placeholder="건축개요 내용을 붙여넣으세요 (예: 대지면적 1,250㎡ / 용적률 199.8% / 지상 15층 / 84㎡ 60세대 …)"
              className="mt-2 w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void extract()}
          disabled={busy}
          className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "개요 추출 중…" : "🧾 개요 필드 추출"}
        </button>
        {info && <span className="text-xs text-[var(--text-secondary)]">{info}</span>}
        {error && <span className="text-xs font-semibold text-[var(--status-error)]">{error}</span>}
      </div>
    </div>
  );
}
