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
  title = "분석 항목 선택",
  subtitle = "필요한 분석만 선택하세요. 선택한 항목만 실행·과금됩니다.",
}: AnalysisModuleSelectorProps) {
  // required는 항상 선택된 것으로 간주. locked는 선택 불가.
  const isOn = (m: AnalysisModuleOption) => m.required || (!m.locked && !!selected[m.key]);

  // 선택분 합계 코인·예상시간 실시간 계산.
  const activeModules = modules.filter((m) => isOn(m));
  const totalCoin = activeModules.reduce((acc, m) => acc + (m.coinCost || 0), 0);
  const totalSeconds = activeModules.reduce((acc, m) => acc + (m.estimatedSeconds || 0), 0);
  const selectedCount = activeModules.length;

  const toggle = (m: AnalysisModuleOption, checked: boolean) => {
    if (m.required || m.locked) return; // 필수/잠금은 변경 불가
    onChange({ ...selected, [m.key]: checked });
  };

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-5">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="text-sm font-bold text-[var(--text-primary)]">{title}</p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{subtitle}</p>
          </div>
          <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-[11px] font-bold text-[var(--text-secondary)]">
            선택 {selectedCount}개
          </span>
        </div>

        {/* 모듈 카탈로그 그리드 */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {modules.map((m) => {
            const checked = isOn(m);
            const interactive = !m.required && !m.locked;
            const base =
              "flex items-start gap-3 rounded-xl border p-3 transition-colors";
            const stateClass = m.required
              ? "cursor-not-allowed border-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_6%,transparent)]"
              : m.locked
                ? "cursor-not-allowed border-[var(--line-strong)] bg-[var(--surface-card)] opacity-60"
                : "cursor-pointer border-[var(--line-strong)] bg-[var(--surface-soft)] hover:border-[var(--accent-strong)]";
            return (
              <label key={m.key} className={`${base} ${stateClass}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  readOnly={!interactive}
                  disabled={!interactive}
                  onChange={(e) => toggle(m, e.target.checked)}
                  className={`mt-0.5 h-4 w-4 accent-[var(--accent-strong)] ${m.required ? "opacity-70" : ""}`}
                  aria-label={m.label}
                />
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
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
            예상 소모{" "}
            <b className="text-[var(--text-primary)]">{unlimited ? "무제한(관리자)" : won(totalCoin)}</b>
            {" · "}예상 소요 <b className="text-[var(--text-primary)]">{formatSeconds(totalSeconds)}</b>
            <span className="ml-1 text-[var(--text-hint)]">(미선택 모듈은 호출 자체를 생략)</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {onSelectAll && (
              <button
                type="button"
                onClick={onSelectAll}
                disabled={runDisabled}
                className="whitespace-nowrap rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-bold text-[var(--accent-strong)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)] disabled:opacity-50"
              >
                ⚡ 전체 자동분석
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
