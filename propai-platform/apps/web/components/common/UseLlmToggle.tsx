"use client";

/**
 * UseLlmToggle — "AI 분석 포함(LLM)" 옵트인 체크박스 공용 컴포넌트.
 *
 * 신설 이유(전파방지): SeniorConsultPanel·MarketInsightsWorkspaceClient 등 화면마다
 * 같은 use_llm 옵트인 체크박스를 각자 복제하고 있었다. 한 곳(이 파일)으로 모아
 * 시각·동작을 통일하고, 새 화면은 이 컴포넌트만 쓰면 된다.
 *
 * 정책: 기본 미체크(무과금 기본 — 관리자 미설정 시 무료·자동 전체 실행 금지).
 * 색상은 디자인 토큰만 사용(bare 색상 금지).
 */

import { Bot } from "lucide-react";

export function UseLlmToggle({
  checked,
  onChange,
  label = "AI 분석 포함",
  hint,
  disabled = false,
  className = "",
}: {
  /** 현재 체크 상태(상위 state가 SSOT). */
  checked: boolean;
  /** 체크 변경 콜백 — 상위 setState를 그대로 전달하면 된다. */
  onChange: (checked: boolean) => void;
  /** 체크박스 라벨(기본 "AI 분석 포함"). */
  label?: string;
  /** 라벨 뒤 보조 설명(회색 괄호 표기) — 무엇을 LLM이 작성하는지 안내. */
  hint?: string;
  /** 실행 중 등 조작 금지 상태. */
  disabled?: boolean;
  /** 배치 여백 등 상위 레이아웃 보정용(레이아웃 훼손 방지). */
  className?: string;
}) {
  return (
    <label
      className={`inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-[var(--text-secondary)] ${className}`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="h-4 w-4 accent-[var(--accent-strong)]"
      />
      <span className="inline-flex items-center gap-1.5">
        <Bot className="size-4" aria-hidden />
        {label}
      </span>
      {hint && <span className="font-normal text-[var(--text-tertiary)]">({hint})</span>}
    </label>
  );
}
