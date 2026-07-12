"use client";

import { useState } from "react";
import { Button } from "@propai/ui";
import { apiClient } from "@/lib/api-client";

/**
 * 통합 보고서 다운로드 메뉴 — 하나의 정본 보고서를 PDF·PPTX·DOCX 중 골라 받는다.
 * 백엔드 POST /api/v1/reports/generate?format 이 같은 데이터·같은 디자인으로 3포맷을 만든다.
 * (기존 ReportPdfDownload = PDF 전용의 상위호환. 응답 확장자는 서버가 파일명으로 알려준다.)
 */

type Props = {
  projectId: string;
};

// 사용자가 고를 수 있는 포맷(라벨·확장자)
const FORMATS = [
  { key: "pdf", label: "PDF", hint: "인쇄·제출용" },
  { key: "pptx", label: "PPT", hint: "발표용" },
  { key: "docx", label: "Word", hint: "편집용" },
] as const;

type FormatKey = (typeof FORMATS)[number]["key"];
type Status = "idle" | "generating" | "done" | "error";

const STATUS_LABEL: Record<Status, string> = {
  idle: "보고서 다운로드",
  generating: "보고서 생성 중…",
  done: "다운로드 완료",
  error: "오류 — 다시 시도",
};

/** 응답 헤더의 Content-Disposition 에서 파일명을 뽑는다(없으면 기본값). */
function filenameFromResponse(res: Response, projectId: string, fmt: FormatKey): string {
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="?([^"]+)"?/);
  if (m?.[1]) return m[1];
  return `propai-report-${projectId}.${fmt}`;
}

export function ReportDownloadMenu({ projectId }: Props) {
  const [format, setFormat] = useState<FormatKey>("pdf");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleDownload() {
    setStatus("generating");
    setErrorMessage("");
    try {
      const runtimeConfig = apiClient.getRuntimeConfig();
      const baseUrl = runtimeConfig.apiBaseUrl || "/api/proxy";
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("propai_access_token") ?? ""
          : "";

      const res = await fetch(`${baseUrl}/reports/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ project_id: projectId, format }),
      });

      if (!res.ok) {
        // 분석 이력이 없으면 서버가 404 + 안내 메시지(JSON)를 준다 — 정직하게 노출.
        let msg = `생성 실패 (HTTP ${res.status})`;
        try {
          const j = await res.json();
          if (j?.message) msg = j.message;
        } catch {
          /* JSON 아님 — 기본 메시지 유지 */
        }
        throw new Error(msg);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameFromResponse(res, projectId, format);
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);

      setStatus("done");
      setTimeout(() => setStatus("idle"), 3000);
    } catch (error) {
      setStatus("error");
      setErrorMessage(
        error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.",
      );
    }
  }

  const busy = status === "generating";

  return (
    <div className="space-y-3">
      {/* 포맷 선택 — 세그먼트 버튼 */}
      <div
        className="flex gap-1 rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface-soft)] p-1"
        role="radiogroup"
        aria-label="보고서 파일 형식"
      >
        {FORMATS.map((f) => {
          const active = format === f.key;
          return (
            <button
              key={f.key}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={busy}
              onClick={() => setFormat(f.key)}
              className={[
                "flex-1 rounded-[var(--r-input)] px-3 py-1.5 font-[var(--font-mono)] text-sm font-medium transition-colors",
                active
                  ? "bg-[var(--accent-strong)] text-[var(--on-primary)]"
                  : "text-[var(--text-tertiary)] hover:bg-[var(--surface)]",
              ].join(" ")}
              title={f.hint}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      <Button onClick={handleDownload} disabled={busy} className="w-full gap-3">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" x2="12" y1="15" y2="3" />
        </svg>
        <span>{STATUS_LABEL[status]}</span>
      </Button>

      {busy && (
        <div className="overflow-hidden rounded-full bg-[var(--surface-soft)]">
          <div className="h-1.5 w-1/3 animate-pulse rounded-full bg-[var(--accent-strong)]" />
        </div>
      )}

      {status === "error" && errorMessage && (
        <p className="text-xs text-[var(--status-error)]">{errorMessage}</p>
      )}
    </div>
  );
}
