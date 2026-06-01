"use client";

import React, { useRef, useState, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";

interface ImageUploadProps {
  value?: string;
  onChange: (base64: string) => void;
  className?: string;
  label?: string;
}

const MIN_H = 160;
const MAX_H = 720;
const DEFAULT_H = 256;

export function ImageUpload({ value, onChange, className, label = "클릭하거나 이미지를 드래그하여 업로드하세요" }: ImageUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [previewH, setPreviewH] = useState(DEFAULT_H);
  const [fit, setFit] = useState<"cover" | "contain">("cover");
  const inputRef = useRef<HTMLInputElement>(null);
  const resizeRef = useRef<{ startY: number; startH: number } | null>(null);

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) {
      alert("이미지 파일만 업로드할 수 있습니다.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result;
      if (typeof result === "string") onChange(result);
    };
    reader.readAsDataURL(file);
  };

  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
  };
  const openPicker = () => inputRef.current?.click();

  // ── 높이 리사이즈(드래그 핸들) ──
  const onResizeMove = useCallback((e: MouseEvent) => {
    if (!resizeRef.current) return;
    const delta = e.clientY - resizeRef.current.startY;
    const next = Math.min(MAX_H, Math.max(MIN_H, resizeRef.current.startH + delta));
    setPreviewH(next);
  }, []);

  const onResizeEnd = useCallback(() => {
    resizeRef.current = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    window.removeEventListener("mousemove", onResizeMove);
    window.removeEventListener("mouseup", onResizeEnd);
  }, [onResizeMove]);

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      resizeRef.current = { startY: e.clientY, startH: previewH };
      document.body.style.cursor = "ns-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("mousemove", onResizeMove);
      window.addEventListener("mouseup", onResizeEnd);
    },
    [previewH, onResizeMove, onResizeEnd],
  );

  // 언마운트 시 리스너 정리
  useEffect(() => () => {
    window.removeEventListener("mousemove", onResizeMove);
    window.removeEventListener("mouseup", onResizeEnd);
  }, [onResizeMove, onResizeEnd]);

  // ── 이미지 미리보기(높이 조정 + fit 토글 가능) ──
  if (value) {
    return (
      <div className={cn("relative w-full", className)}>
        <div
          className="relative w-full overflow-hidden rounded-2xl border-2 border-[var(--line-strong)] bg-[var(--surface-muted)] group"
          style={{ height: previewH }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={value}
            alt="Uploaded Preview"
            className={cn(
              "w-full h-full transition-all",
              fit === "cover" ? "object-cover" : "object-contain",
            )}
          />
          {/* 상단 우측: fit 토글 + 변경 */}
          <div className="absolute right-3 top-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setFit((f) => (f === "cover" ? "contain" : "cover")); }}
              className="rounded-lg bg-black/60 px-3 py-1.5 text-[11px] font-bold text-white backdrop-blur-md hover:bg-black/80"
            >
              {fit === "cover" ? "전체 보기" : "채우기"}
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); openPicker(); }}
              className="rounded-lg bg-black/60 px-3 py-1.5 text-[11px] font-bold text-white backdrop-blur-md hover:bg-black/80"
            >
              이미지 변경
            </button>
          </div>
        </div>

        {/* 하단 리사이즈 핸들 — 드래그로 높이 조정 */}
        <div
          onMouseDown={onResizeStart}
          className="mt-1 flex h-5 w-full cursor-ns-resize items-center justify-center rounded-md hover:bg-[var(--surface-strong)] transition-colors group/handle"
          title="드래그하여 표시 높이 조정"
        >
          <div className="flex flex-col items-center gap-[2px]">
            <div className="h-[2px] w-10 rounded-full bg-[var(--line-strong)] group-hover/handle:bg-[var(--accent-strong)] transition-colors" />
            <div className="h-[2px] w-6 rounded-full bg-[var(--line-strong)] group-hover/handle:bg-[var(--accent-strong)] transition-colors" />
          </div>
        </div>
        <p className="text-center text-[10px] text-[var(--text-hint)]">
          핸들을 드래그해 높이 조정 · &quot;전체 보기&quot;로 잘림 없이 표시 ({Math.round(previewH)}px)
        </p>

        <input
          type="file" accept="image/*" className="hidden" ref={inputRef}
          onChange={(e) => { if (e.target.files?.length) handleFile(e.target.files[0]); }}
        />
      </div>
    );
  }

  // ── 빈 업로드 영역 ──
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 transition-all cursor-pointer overflow-hidden group",
        isDragging
          ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/10"
          : "border-[var(--line-strong)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]",
        className,
      )}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={openPicker}
    >
      <input
        type="file" accept="image/*" className="hidden" ref={inputRef}
        onChange={(e) => { if (e.target.files?.length) handleFile(e.target.files[0]); }}
      />
      <div className="flex flex-col items-center justify-center py-8 text-[var(--text-tertiary)] group-hover:text-[var(--text-secondary)] transition-colors">
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mb-4 opacity-50 group-hover:opacity-100 transition-opacity">
          <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
          <circle cx="9" cy="9" r="2" />
          <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
        </svg>
        <span className="text-sm font-medium text-center px-4 leading-relaxed">{label}</span>
        <span className="text-xs mt-2 opacity-50">JPG, PNG (Max 5MB 권장)</span>
      </div>
    </div>
  );
}
