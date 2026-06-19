"use client";

/**
 * RunModeSwitcher — 4실행모드 탭(가이드/별도/선택/프로필).
 *
 * Phase B 블루프린트 §3-B·§2-C 정합. [graft C] 모드 전환 UI.
 * 활성: 별도(standalone)·선택(selective)·프로필(profile, B5). 가이드(guided)=B4라
 * 비활성 + "준비중(B4)" 표기로 정직하게 잠근다(가짜 동작 금지).
 *
 * 색상은 토큰만 사용(하드코딩 금지). cc-* 유틸·--accent-strong 채택.
 */

import type { RunMode } from "@/store/useOrchestrationStore";

interface ModeTab {
  mode: RunMode;
  label: string;
  hint: string;
  /** B3에서 활성 여부(가이드/프로필은 false). */
  enabled: boolean;
  /** 비활성 시 정직 표기(준비 단계). */
  pendingLabel?: string;
}

/** 4모드 정의 — standalone·selective·profile 활성(guided=B4 준비중). */
const MODE_TABS: ModeTab[] = [
  {
    mode: "guided",
    label: "가이드",
    hint: "토지→금융까지 단계별 안내",
    enabled: false,
    pendingLabel: "준비중(B4)",
  },
  {
    mode: "standalone",
    label: "별도",
    hint: "원하는 분석 하나만 단독 실행(상류 자동해소)",
    enabled: true,
  },
  {
    mode: "selective",
    label: "선택",
    hint: "필요한 분석만 골라 실행·과금",
    enabled: true,
  },
  {
    mode: "profile",
    label: "프로필",
    hint: "저장한 워크플로우로 실행",
    enabled: true,
  },
];

export interface RunModeSwitcherProps {
  value: RunMode;
  onChange: (mode: RunMode) => void;
}

export function RunModeSwitcher({ value, onChange }: RunModeSwitcherProps) {
  return (
    <div>
      <div
        role="tablist"
        aria-label="분석 실행 모드"
        className="flex flex-wrap gap-2 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-1.5"
      >
        {MODE_TABS.map((tab) => {
          const active = value === tab.mode && tab.enabled;
          const base =
            "flex flex-col items-start gap-0.5 rounded-xl px-3.5 py-2 text-left transition-colors";
          const cls = !tab.enabled
            ? "cursor-not-allowed opacity-50"
            : active
              ? "bg-[var(--accent-strong)] text-white"
              : "text-[var(--text-secondary)] hover:bg-[var(--surface-card)]";
          return (
            <button
              key={tab.mode}
              type="button"
              role="tab"
              aria-selected={active}
              disabled={!tab.enabled}
              onClick={() => tab.enabled && onChange(tab.mode)}
              className={`${base} ${cls}`}
            >
              <span className="flex items-center gap-1.5 text-sm font-bold">
                {tab.label}
                {!tab.enabled && tab.pendingLabel && (
                  <span className="rounded-full bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--text-tertiary)]">
                    {tab.pendingLabel}
                  </span>
                )}
              </span>
              <span
                className={`text-[10px] font-normal ${active ? "text-white/80" : "text-[var(--text-tertiary)]"}`}
              >
                {tab.hint}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
