"use client";

import { useState } from "react";
import { Button } from "@propai/ui";
type ReportPdfDownloadProps = {
  projectId: string;
};

type DownloadStatus = "idle" | "generating" | "downloading" | "done" | "error";

const STATUS_LABELS: Record<DownloadStatus, string> = {
  idle: "PDF 보고서 다운로드",
  generating: "보고서 생성 중...",
  downloading: "다운로드 준비 중...",
  done: "다운로드 완료",
  error: "오류 발생 — 다시 시도",
};

export function ReportPdfDownload({ projectId }: ReportPdfDownloadProps) {
  const [status, setStatus] = useState<DownloadStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleDownload() {
    setStatus("generating");
    setProgress(0);
    setErrorMessage("");

    // Simulate progress while waiting for the API
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + Math.random() * 15;
      });
    }, 400);

    try {
      const runtimeConfig = ({ mode: "local" as string, hasAccessToken: false });
      const baseUrl = runtimeConfig.apiBaseUrl || "/api/proxy";
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("propai_access_token") ?? ""
          : "";

      const response = await fetch(`${baseUrl}/reports/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          project_id: projectId,
          format: "pdf",
        }),
      });

      clearInterval(progressInterval);

      if (!response.ok) {
        throw new Error(`PDF 생성 실패 (HTTP ${response.status})`);
      }

      setStatus("downloading");
      setProgress(95);

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `propai-report-${projectId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);

      setProgress(100);
      setStatus("done");

      // Reset after 3 seconds
      setTimeout(() => {
        setStatus("idle");
        setProgress(0);
      }, 3000);
    } catch (error) {
      clearInterval(progressInterval);
      setStatus("error");
      setProgress(0);
      setErrorMessage(
        error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.",
      );
    }
  }

  const isDisabled = status === "generating" || status === "downloading";

  return (
    <div className="space-y-3">
      <Button
        onClick={handleDownload}
        disabled={isDisabled}
        className="w-full gap-3"
      >
        {/* Download icon */}
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
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" x2="12" y1="15" y2="3" />
        </svg>
        <span>{STATUS_LABELS[status]}</span>
      </Button>

      {/* Progress bar */}
      {(status === "generating" || status === "downloading") && (
        <div className="overflow-hidden rounded-full bg-[var(--surface-soft)]">
          <div
            className="h-2 rounded-full bg-[var(--accent-strong)] transition-all duration-300 ease-out"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}

      {/* Error message */}
      {status === "error" && errorMessage && (
        <p className="text-xs text-[var(--spot)]">{errorMessage}</p>
      )}
    </div>
  );
}
