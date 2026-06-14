"use client";

/**
 * M3 적정 분양가 패널 — 거래사례비교(1차 핵심) + 지불여력(2차 검증).
 *
 * ★분양가 산정 우선순위: ①주변 동일종목 실거래 시세 + ②주변 신규 분양가(거래사례비교)가
 *   적정 분양가의 1차 앵커(헤드라인). 지불여력(PIR/DSR/LTV)은 "그 시장가를 타깃 수요가
 *   감당 가능한가(미분양 위험)"를 검증하는 2차 보조 지표.
 *
 * 정직성: 비교 데이터 없으면 "데이터 없음"(가짜 분양가 금지). 출처(data_source) 그대로 노출.
 * 색상 토큰만 사용.
 */

import type { PricingBand } from "./marketTypes";
import { DataSourceBadge } from "./DataSourceBadge";

// 만원 → "N억 N,NNN만원".
function man(v?: number | null): string {
  if (!v || v <= 0) return "-";
  if (v >= 10000) {
    const uk = Math.floor(v / 10000);
    const rest = v % 10000;
    return rest > 0 ? `${uk}억 ${rest.toLocaleString()}만원` : `${uk}억원`;
  }
  return `${v.toLocaleString()}만원`;
}

const VERDICT: Record<string, { label: string; color: string; bg: string }> = {
  within_conservative: { label: "수요 감당 가능 (보수 상한 이내) — 안전", color: "var(--status-success)", bg: "color-mix(in srgb, var(--status-success) 12%, transparent)" },
  within_optimistic: { label: "수용 가능하나 부담 (낙관 상한 이내)", color: "var(--status-warning)", bg: "color-mix(in srgb, var(--status-warning) 12%, transparent)" },
  over_band: { label: "지불여력 초과 — 미분양 위험", color: "var(--status-danger)", bg: "color-mix(in srgb, var(--status-danger) 12%, transparent)" },
};

export function PricingBandPanel({ data }: { data?: PricingBand | null }) {
  if (!data) return null;

  // 비교 데이터 없음(주변 실거래·분양가 없음) → 정직 안내(가짜 분양가 금지).
  if (data.data_source === "unavailable" || data.fair_price_10k == null) {
    return (
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden>🏷️</span>
          <span className="sa-di-block__title">적정 분양가 (거래사례비교)</span>
          <DataSourceBadge source="unavailable" />
        </header>
        <div className="sa-di-block__body">
          <p className="sa-di-empty">주변 실거래·분양가 비교 데이터가 없어 적정 분양가를 산출할 수 없습니다. (가짜값 미표시)</p>
        </div>
      </div>
    );
  }

  const mr = data.market_reference || {};
  const af = data.affordability;
  const verdict = data.affordability_verdict && data.affordability_verdict !== "unavailable"
    ? VERDICT[data.affordability_verdict] : null;

  return (
    <div className="sa-di-block">
      <header className="sa-di-block__head" style={{ cursor: "default" }}>
        <span className="sa-di-block__icon" aria-hidden>🏷️</span>
        <span className="sa-di-block__title">적정 분양가 (거래사례비교 + 지불여력)</span>
        <DataSourceBadge source={data.data_source} />
      </header>
      <div className="sa-di-block__body">
        {/* 1차(핵심): 시장 비교 적정 분양가 */}
        <div className="sa-di-tiles sa-di-tiles--3">
          <div className="sa-di-tile">
            <span className="sa-di-tile__label">주변 실거래 기준 (84㎡)</span>
            <span className="sa-di-tile__value">{man(mr.comparable_trade_10k)}</span>
          </div>
          <div className="sa-di-tile sa-di-tile--accent">
            <span className="sa-di-tile__label">적정 분양가 (시장 비교)</span>
            <span className="sa-di-tile__value">{man(data.fair_price_10k)}</span>
          </div>
          <div className="sa-di-tile">
            <span className="sa-di-tile__label">주변 신규 분양가</span>
            <span className="sa-di-tile__value">{man(mr.nearby_presale_10k)}</span>
          </div>
        </div>
        {mr.method && (
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">산정 방식: {mr.method}</p>
        )}

        {/* 2차(보조): 지불여력 검증 */}
        {af?.band_10k ? (
          <div className="mt-4 border-t border-[var(--line)] pt-3">
            <p className="sa-di-eyebrow mb-2">지불여력 검증 (타깃 가구 소득 기준) <DataSourceBadge source={af.data_source} /></p>
            <div className="relative h-3 rounded-full bg-[var(--surface-muted)]">
              <div className="absolute inset-y-0 left-0 w-full rounded-full"
                style={{ background: "linear-gradient(90deg, color-mix(in srgb, var(--status-success) 40%, transparent), color-mix(in srgb, var(--status-warning) 45%, transparent))" }} />
              {/* 적정 분양가 위치 마커 */}
              {(() => {
                const [low, high] = af.band_10k!;
                const span = Math.max(1, high - low);
                const pct = Math.min(100, Math.max(0, (((data.fair_price_10k as number) - low) / span) * 100));
                return <div className="absolute -top-1 h-5 w-[3px] rounded bg-[var(--text-primary)]"
                  style={{ left: `calc(${pct}% - 1.5px)` }} title={`적정 분양가 ${man(data.fair_price_10k)}`} />;
              })()}
            </div>
            <div className="mt-1 flex justify-between text-[10px] text-[var(--text-tertiary)]">
              <span>보수 {man(af.affordable_by_pir_10k)}</span>
              <span>낙관 {man(af.affordable_by_dsr_ltv_10k)}</span>
            </div>
            {verdict && (
              <div className="mt-3 rounded-xl px-3 py-2 text-xs font-bold" style={{ color: verdict.color, backgroundColor: verdict.bg }}>
                적정 분양가 {man(data.fair_price_10k)} → {verdict.label}
              </div>
            )}
          </div>
        ) : (
          <p className="mt-3 text-[11px] text-[var(--text-hint)]">지불여력 검증은 「거시 소득 지표(KOSIS)」 선택 시 표시됩니다.</p>
        )}

        <p className="mt-3 text-[11px] leading-snug text-[var(--text-hint)]">※ {data.basis} 전문 감정·분양 검토 필수.</p>
      </div>
    </div>
  );
}
