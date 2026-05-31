"use client";

import React, { useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface ImageUploadProps {
  value?: string;
  onChange: (base64: string) => void;
  className?: string;
  label?: string;
}

export function ImageUpload({ value, onChange, className, label = "클릭하거나 이미지를 드래그하여 업로드하세요" }: ImageUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) {
      alert("이미지 파일만 업로드할 수 있습니다.");
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result;
      if (typeof result === "string") {
        onChange(result);
      }
    };
    reader.readAsDataURL(file);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const onClick = () => {
    inputRef.current?.click();
  };

  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 transition-all cursor-pointer overflow-hidden group",
        isDragging
          ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/10"
          : "border-[var(--line-strong)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]",
        className
      )}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={onClick}
    >
      <input
        type="file"
        accept="image/*"
        className="hidden"
        ref={inputRef}
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            handleFile(e.target.files[0]);
          }
        }}
      />
      
      {value ? (
        <div className="relative w-full h-48 sm:h-64 rounded-xl overflow-hidden group">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={value}
            alt="Uploaded Preview"
            className="w-full h-full object-cover transition-transform group-hover:scale-105"
          />
          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <span className="text-white text-sm font-bold bg-black/50 px-4 py-2 rounded-lg backdrop-blur-md">
              클릭하여 변경
            </span>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 text-[var(--text-tertiary)] group-hover:text-[var(--text-secondary)] transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mb-4 opacity-50 group-hover:opacity-100 transition-opacity">
            <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
            <circle cx="9" cy="9" r="2"/>
            <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
          </svg>
          <span className="text-sm font-medium text-center px-4 leading-relaxed">
            {label}
          </span>
          <span className="text-xs mt-2 opacity-50">JPG, PNG (Max 5MB 권장)</span>
        </div>
      )}
    </div>
  );
}
