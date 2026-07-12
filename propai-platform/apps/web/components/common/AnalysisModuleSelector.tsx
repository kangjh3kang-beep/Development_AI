"use client";

/**
 * 선택형 분석 모듈 선택기 (전 시스템 공용).
 *
 * 사용자 핵심지침 "선택형 상세분석을 전 시스템 기본으로"를 구현한 재사용 컴포넌트.
 * 시장분석을 시작으로 부지·수지·인허가·ESG 등 전 모듈이 동일 패턴을 채택할 수 있도록
 * 도메인 비종속(모듈 카탈로그를 props로 주입)으로 일반화했다.
 *
 * - 기본 진입 = 선택형(이 패널이 디폴트). 사용자가 필요한 모듈만 체크 → 선택분만 실행·과금.
 * - "전체 자동분석"은 별도 버튼(디폴트 아님).
 * - 선택 수 → 합계 코인·예상 소요시간을 실시간 계산해 투명하게 표시.
 * - locked 모듈은 더미수치 노출 금지 → 잠금 배지 + 비활성.
 *
 * 색상은 토큰만 사용(하드코딩 금지), WCAG AA 대비 유지.
 */

import { Zap, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@propai/ui";

/** 단일 분석 모듈 정의. */
export interface AnalysisModuleOption {
  /** 선택 상태 맵의 키. */
  key: string;
  /** 모듈 라벨(한국어). */
  label: string;
  /** 한 줄 설명. */
  description?: string;
  /** 이 모듈 실행 시 소모 코인(원 단위 추정). 0이면 기본 포함/무료. */
  coinCost?: number;
  /** 이 모듈 예상 소요시간(초). 합산해 예상 시간 표시. */
  estimatedSeconds?: number;
  /** 항상 포함(해제 불가) 모듈. 기본 필수 항목에 사용. */
  required?: boolean;
  /** 프리미엄 잠금 모듈. 체크 불가 + 잠금 배지. 더미수치 금지. */
  locked?: boolean;
  /** 잠금 해제 CTA 문구(locked일 때만). */
  lockedCtaLabel?: string;
  /** 카드 헤더 아이콘(직관). 문자열(이모지/짧은 기호) 또는 lucide 아이콘 컴포넌트. 순수 표시용. */
  icon?: string | LucideIcon;
  /**
   * 하위 항목(1단계 깊이만). 있으면 이 모듈은 "분류"가 되고 자식은 "항목"이 된다.
   * 부모 체크박스는 3-state(전체선택/부분/해제)로 동작한다.
   */
  children?: AnalysisModuleOption[];
}

export interface AnalysisModuleSelectorProps {
  /** 모듈 카탈로그. */
  modules: AnalysisModuleOption[];
  /** 선택 상태 맵 { key: boolean }. required 모듈은 항상 true로 간주. */
  selected: Record<string, boolean>;
  /** 선택 변경 콜백(새 선택 상태 맵 전체 전달). */
  onChange: (next: Record<string, boolean>) => void;
  /** "전체 자동분석" 버튼 클릭 콜백(미전달 시 버튼 숨김). */
  onSelectAll?: () => void;
  /** "분석 시작" 버튼 클릭 콜백(미전달 시 버튼 숨김 — 부모가 별도 패널로 실행할 때). */
  onRun?: () => void;
  /** 실행 비활성(주소 미입력·코인 부족 등). */
  runDisabled?: boolean;
  /** 무제한 등급 — 코인 합계 대신 "무제한" 표기. */
  unlimited?: boolean;
  /** 패널 제목(기본: "분석 항목 선택"). */
  title?: string;
  /** 패널 부제. */
  subtitle?: string;
  /** 선택 기능 비활성화 여부 (나열 및 정보 제공 전용) */
  readOnly?: boolean;
}

const won = (n: number) => `${(n ?? 0).toLocaleString("ko-KR")}원`;

/** 초 → "약 N초" / "약 N분 N초" 사람이 읽기 쉬운 표기. */
function formatSeconds(sec: number): string {
  if (sec <= 0) return "즉시";
  if (sec < 60) return `약 ${sec}초`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s > 0 ? `약 ${m}분 ${s}초` : `약 ${m}분`;
}

export function AnalysisModuleSelector({
  modules,
  selected,
  onChange,
  onSelectAll,
  onRun,
  runDisabled = false,
  unlimited = false,
  readOnly = false,
  title = readOnly ? "분석 항목" : "분석 항목 선택",
  subtitle = readOnly ? "본 보고서에 포함되는 분석 모듈 목록입니다." : "필요한 분석만 선택하세요. 선택한 항목만 실행·과금됩니다.",
}: AnalysisModuleSelectorProps) {
  // required는 항상 선택된 것으로 간주. locked는 선택 불가. readOnly일 때는 잠기지 않은 모든 모듈을 활성으로 간주.
  const isOn = (m: AnalysisModuleOption) => m.required || (!m.locked && (readOnly || !!selected[m.key]));

  // 말단(leaf) 모듈만 모은다 — 자식이 있으면 자식들이 말단, 없으면 자신이 말단.
  // 코인·시간 합계와 "선택 N개"는 모두 이 말단 기준으로 계산한다.
  const leafModules: AnalysisModuleOption[] = [];
  for (const m of modules) {
    if (m.children && m.children.length > 0) {
      leafModules.push(...m.children);
    } else {
      leafModules.push(m);
    }
  }

  // 선택분 합계 코인·예상시간 실시간 계산(말단 기준).
  const activeLeaves = leafModules.filter((m) => isOn(m));
  const totalCoin = activeLeaves.reduce((acc, m) => acc + (m.coinCost || 0), 0);
  const totalSeconds = activeLeaves.reduce((acc, m) => acc + (m.estimatedSeconds || 0), 0);
  const selectedCount = activeLeaves.length;

  // 단일(자식 없는) 모듈 토글 — 기존 동작 100% 동일.
  const toggle = (m: AnalysisModuleOption, checked: boolean) => {
    if (m.required || m.locked) return; // 필수/잠금은 변경 불가
    onChange({ ...selected, [m.key]: checked });
  };

  // 자식 항목 토글 — 해당 자식 키만 갱신(부모 상태는 자식들에서 파생).
  const toggleChild = (child: AnalysisModuleOption, checked: boolean) => {
    if (child.required || child.locked) return;
    onChange({ ...selected, [child.key]: checked });
  };

  // 부모(분류) 토글 — 모든 (잠기지 않은) 자식을 동반 토글한다.
  const toggleParent = (parent: AnalysisModuleOption, checked: boolean) => {
    if (parent.locked) return;
    const next = { ...selected };
    for (const c of parent.children || []) {
      if (c.locked || c.required) continue;
      next[c.key] = checked;
    }
    onChange(next);
  };

  // 아코디언 — 분류(자식 보유) 카드의 펼침 상태. 기본 전체 펼침(처음 진입 시 모든 항목 노출).
  const parentKeys = modules.filter((m) => (m.children?.length ?? 0) > 0).map((m) => m.key);
  const [expanded, setExpanded] = useState<Record<string, boolean>>(
    () => Object.fromEntries(parentKeys.map((k) => [k, true])),
  );
  const toggleExpand = (key: string) => setExpanded((prev) => ({ ...prev, [key]: prev[key] === false }));
  const isExpanded = (key: string) => expanded[key] !== false;

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-5">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="text-sm font-bold text-[var(--text-primary)]">{title}</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{subtitle}</p>
          </div>
          {!readOnly && (
            <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-[11px] font-bold text-[var(--text-secondary)]">
              선택 {selectedCount}개
            </span>
          )}
        </div>

        {/* 모듈 카탈로그 — 균형 2열 그리드(분류·단일 모두 1칸, 시선축 단일화). 분류는 아코디언. */}
        <div className="grid items-start gap-3 sm:grid-cols-2">
          {modules.map((m) => {
            const kids = m.children || [];
            // 분류(자식 있음)는 아코디언 카드(헤더 클릭 펼침/접힘). 단일 칸을 차지해 좌우 균형 유지.
            if (kids.length > 0) {
              return (
                <ParentModuleCard
                  key={m.key}
                  module={m}
                  isOn={isOn}
                  won={won}
                  expanded={isExpanded(m.key)}
                  onToggleExpand={() => toggleExpand(m.key)}
                  onToggleParent={toggleParent}
                  onToggleChild={toggleChild}
                  readOnly={readOnly}
                />
              );
            }
            // 단일 모듈(자식 없음) — 기존 동작 100% 동일.
            const checked = isOn(m);
            const interactive = !m.required && !m.locked && !readOnly;
            const base =
              "flex items-start gap-3 rounded-xl border p-3 transition-colors";
            const stateClass = readOnly
              ? "border-[var(--line-strong)] bg-[var(--surface-soft)]"
              : m.required
                ? "cursor-not-allowed border-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_6%,transparent)]"
                : m.locked
                  ? "cursor-not-allowed border-[var(--line-strong)] bg-[var(--surface-strong)] opacity-60"
                  : "cursor-pointer border-[var(--line-strong)] bg-[var(--surface-soft)] hover:border-[var(--accent-strong)]";
            return (
              <label key={m.key} className={`${base} ${stateClass}`}>
                {!readOnly && (
                  <input
                    type="checkbox"
                    checked={checked}
                    readOnly={!interactive}
                    disabled={!interactive}
                    onChange={(e) => toggle(m, e.target.checked)}
                    className={`mt-0.5 h-4 w-4 accent-[var(--accent-strong)] ${m.required ? "opacity-70" : ""}`}
                    aria-label={m.label}
                  />
                )}
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
                    {m.icon && (typeof m.icon === "string"
                      ? <span aria-hidden className="text-[var(--text-secondary)]">{m.icon}</span>
                      : <m.icon className="size-4 text-[var(--text-secondary)]" aria-hidden />)}
                    {m.label}
                    {m.locked && (
                      <span className="rounded-full bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">
                        잠금
                      </span>
                    )}
                  </p>
                  {m.description && (
                    <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-secondary)]">{m.description}</p>
                  )}
                  {/* 코인·시간 메타(필수=기본 포함, 잠금=프리미엄, 그 외=+코인) */}
                  <p className="mt-1 text-[10px] font-semibold text-[var(--text-tertiary)]">
                    {m.required
                      ? "기본 포함"
                      : m.locked
                        ? (m.lockedCtaLabel || "프리미엄 전용")
                        : m.coinCost
                          ? `+${won(m.coinCost)}`
                          : "추가 비용 없음"}
                  </p>
                </div>
              </label>
            );
          })}
        </div>

        {/* 합계 요약 + 실행 버튼 */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4">
          <div className="text-xs text-[var(--text-secondary)]">
            {readOnly ? (
              <span>
                분석 예상 소요 시간: <b className="text-[var(--text-primary)]">{formatSeconds(totalSeconds)}</b>
              </span>
            ) : (
              <span>
                예상 소모{" "}
                <b className="text-[var(--text-primary)]">{unlimited ? "무제한(관리자)" : won(totalCoin)}</b>
                {" · "}예상 소요 <b className="text-[var(--text-primary)]">{formatSeconds(totalSeconds)}</b>
                <span className="ml-1 text-[var(--text-hint)]">(미선택 모듈은 호출 자체를 생략)</span>
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {!readOnly && onSelectAll && (
              <button
                type="button"
                onClick={onSelectAll}
                disabled={runDisabled}
                className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-bold text-[var(--accent-strong)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)] disabled:opacity-50"
              >
                <Zap className="size-4" aria-hidden />전체 자동분석
              </button>
            )}
            {onRun && (
              <button
                type="button"
                onClick={onRun}
                disabled={runDisabled}
                className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 py-2 text-xs font-black text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                분석 시작
              </button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** indeterminate(부분선택)를 지원하는 체크박스 — input.indeterminate는 DOM 속성이라 ref로 설정. */
function IndeterminateCheckbox({
  checked,
  indeterminate,
  disabled,
  onChange,
  ariaLabel,
  className,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
  ariaLabel?: string;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  // indeterminate는 React prop이 없어 effect에서 DOM에 직접 반영(동기 setState 아님 — set-state-in-effect 무관).
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = !!indeterminate && !checked;
  }, [indeterminate, checked]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      readOnly={!onChange}
      onChange={(e) => onChange?.(e.target.checked)}
      className={className}
      aria-label={ariaLabel}
    />
  );
}

/** 분류(자식 있음) 카드 — 부모 3-state 체크박스 + 아코디언(헤더 우측 chevron 펼침/접힘) + 자식 목록.
 *  선택용 체크박스와 펼침용 chevron을 분리해, 체크는 선택만·chevron은 펼침만 담당(혼동 방지). */
function ParentModuleCard({
  module: m,
  isOn,
  won,
  expanded,
  onToggleExpand,
  onToggleParent,
  onToggleChild,
  readOnly = false,
}: {
  module: AnalysisModuleOption;
  isOn: (m: AnalysisModuleOption) => boolean;
  won: (n: number) => string;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleParent: (parent: AnalysisModuleOption, checked: boolean) => void;
  onToggleChild: (child: AnalysisModuleOption, checked: boolean) => void;
  readOnly?: boolean;
}) {
  const kids = m.children || [];
  // 토글 가능한 자식(잠금/필수 제외) 기준으로 부모 3-state 파생.
  const toggleable = kids.filter((c) => !c.locked && !c.required);
  const onCount = toggleable.filter((c) => isOn(c)).length;
  const allOn = toggleable.length > 0 && onCount === toggleable.length;
  const someOn = onCount > 0 && !allOn;
  const parentDisabled = m.locked || toggleable.length === 0;

  return (
    <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3">
      {/* 부모(분류) 헤더 — 좌측 3-state 체크박스(전체선택/부분/해제) + 우측 펼침 chevron */}
      <div className="flex items-start gap-3">
        {!readOnly && (
          <IndeterminateCheckbox
            checked={allOn}
            indeterminate={someOn}
            disabled={parentDisabled}
            onChange={parentDisabled ? undefined : (c) => onToggleParent(m, c)}
            ariaLabel={m.label}
            className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent-strong)]"
          />
        )}
        <button
          type="button"
          onClick={onToggleExpand}
          aria-expanded={expanded}
          className="flex min-w-0 flex-1 items-start justify-between gap-2 text-left"
        >
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
              {m.icon && (typeof m.icon === "string"
                ? <span aria-hidden className="text-[var(--text-secondary)]">{m.icon}</span>
                : <m.icon className="size-4 text-[var(--text-secondary)]" aria-hidden />)}
              {m.label}
              {!readOnly && (
                <span className="rounded-full bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--text-tertiary)]">
                  {onCount}/{toggleable.length}
                </span>
              )}
              {m.locked && (
                <span className="rounded-full bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">
                  잠금
                </span>
              )}
            </p>
            {m.description && (
              <p className="mt-0.5 text-[11px] leading-snug text-[var(--text-secondary)]">{m.description}</p>
            )}
          </div>
          <span aria-hidden className="mt-0.5 shrink-0 text-xs text-[var(--text-tertiary)] transition-transform">
            {expanded ? "▾" : "▸"}
          </span>
        </button>
      </div>

      {/* 자식(항목) 목록 — 펼침 상태에서만 노출(아코디언) */}
      {expanded && (
      <div className="mt-2.5 space-y-1.5 border-l border-[var(--line)] pl-3 ml-2">
        {kids.map((c) => {
          const checked = isOn(c);
          const interactive = !c.required && !c.locked && !readOnly;
          return (
            <label
              key={c.key}
              className={`flex items-start gap-2.5 ${interactive ? "cursor-pointer" : "cursor-default opacity-90"}`}
            >
              {!readOnly && (
                <input
                  type="checkbox"
                  checked={checked}
                  readOnly={!interactive}
                  disabled={!interactive}
                  onChange={(e) => onToggleChild(c, e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-[var(--accent-strong)]"
                  aria-label={c.label}
                />
              )}
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-[13px] font-semibold text-[var(--text-primary)]">
                  {c.label}
                  {c.locked && (
                    <span className="rounded-full bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">
                      잠금
                    </span>
                  )}
                </p>
                {c.description && (
                  <p className="mt-0.5 text-[10px] leading-snug text-[var(--text-secondary)]">{c.description}</p>
                )}
                <p className="mt-0.5 text-[10px] font-semibold text-[var(--text-tertiary)]">
                  {c.required
                    ? "기본 포함"
                    : c.locked
                      ? (c.lockedCtaLabel || "프리미엄 전용")
                      : c.coinCost
                        ? `+${won(c.coinCost)}`
                        : "추가 비용 없음"}
                </p>
              </div>
            </label>
          );
        })}
      </div>
      )}
    </div>
  );
}
