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

import { Tag } from "lucide-react";
import type { PricingBand } from "./marketTypes";
import { DataSourceBadge } from "./DataSourceBadge";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { formatManwon as man } from "@/lib/formatters";

// 비율(0.40 같은 소수) → "40%". 백엔드가 분수로 주는 값을 사람이 읽기 쉬운 %로.
function pct(v?: number | null): string {
  if (v == null || !Number.isFinite(v)) return "-";
  // 0~1 사이면 분수로 보고 100배, 그 외(이미 %로 온 값)는 그대로.
  const p = v > 0 && v <= 1 ? v * 100 : v;
  return `${Math.round(p * 10) / 10}%`;
}

const VERDICT: Record<string, { label: string; color: string; bg: string }> = {
  within_conservative: { label: "수요 감당 가능 (보수 상한 이내) — 안전", color: "var(--status-success)", bg: "color-mix(in srgb, var(--status-success) 12%, transparent)" },
  within_optimistic: { label: "수용 가능하나 부담 (낙관 상한 이내)", color: "var(--status-warning)", bg: "color-mix(in srgb, var(--status-warning) 12%, transparent)" },
  over_band: { label: "지불여력 초과 — 미분양 위험", color: "var(--status-error)", bg: "color-mix(in srgb, var(--status-error) 12%, transparent)" },
};

export function PricingBandPanel({ data }: { data?: PricingBand | null }) {
  if (!data) return null;

  // 비교 데이터 없음(주변 실거래·분양가 없음) → 정직 안내(가짜 분양가 금지).
  if (data.data_source === "unavailable" || data.fair_price_10k == null) {
    return (
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden><Tag className="size-3.5" /></span>
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

  // 산출 근거(EvidencePanel) — 응답 실값만으로 구성(가짜값/가짜URL 0).
  // ① 시장 비교 산정 근거(method·실거래·분양가) → ② 지불여력 가정(assumptions)을
  // 한 줄씩 트레이스. assumptions는 소득 데이터가 있을 때만 백엔드가 채우므로 null 가드.
  const asmp = af?.assumptions;
  const evidenceItems: EvidenceItem[] = [];
  // 1차(핵심): 시장 비교 적정 분양가 산정 방식.
  if (data.fair_price_10k != null) {
    evidenceItems.push({
      label: "적정 분양가(시장 비교)",
      value: man(data.fair_price_10k),
      basis: mr.method
        ? `${mr.method} — 주변 실거래 ${man(mr.comparable_trade_10k)} / 주변 분양가 ${man(mr.nearby_presale_10k)}`
        : "거래사례비교(주변 실거래 시세 + 주변 신규 분양가)",
    });
  }
  // 2차(보조): 지불여력 검증 — 감당 가능 밴드 산출 결과.
  if (af?.band_10k) {
    evidenceItems.push({
      label: "감당 가능 밴드",
      value: `${man(af.band_10k[0])} ~ ${man(af.band_10k[1])}`,
      basis: af.annual_income_10k != null
        ? `타깃 가구 연소득 ${man(af.annual_income_10k)} 기준 — 보수(PIR) ~ 낙관(DSR+LTV) 역산`
        : "타깃 가구 연소득 기준 보수~낙관 역산",
    });
  }
  if (af?.recommended_cap_10k != null) {
    evidenceItems.push({
      label: "권장 수용 상한",
      value: man(af.recommended_cap_10k),
      basis: "보수적 수용 상한(미분양 위험 회피 기준) = 밴드 하한",
    });
  }
  // 지불여력 가정값(assumptions) — DSR·LTV·스트레스금리·만기·PIR. 실값을 사람이 읽기 쉽게 단위 변환.
  if (asmp) {
    evidenceItems.push({ label: "DSR(총부채원리금상환비율)", value: pct(asmp.dsr), basis: "연소득 대비 연 원리금 상환 한도" });
    evidenceItems.push({ label: "LTV(주택담보대출비율)", value: pct(asmp.ltv), basis: "주택가격 대비 대출 한도" });
    evidenceItems.push({ label: "스트레스 금리", value: pct(asmp.stress_rate), basis: "상환능력 보수 평가용 가산 금리" });
    if (asmp.term_years != null) {
      evidenceItems.push({ label: "대출 만기", value: `${asmp.term_years}년`, basis: "월복리 연금현가로 대출원금 환산" });
    }
    if (asmp.pir != null) {
      evidenceItems.push({ label: "PIR(소득 대비 주택가격 배수)", value: `${asmp.pir}배`, basis: "보수 상한 = PIR × 연소득" });
    }
  }
  // 종합 근거 문구(basis 문자열) — 출처·기준시점. 응답값 그대로(가짜 문구 금지).
  if (data.basis) {
    evidenceItems.push({ label: "산정 기준·출처", value: "조사 시점 규제·시장 기준값", basis: data.basis });
  }

  return (
    <div className="sa-di-block">
      <header className="sa-di-block__head" style={{ cursor: "default" }}>
        <span className="sa-di-block__icon" aria-hidden><Tag className="size-3.5" /></span>
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

            {/* 지불여력 가정값(assumptions) 구조화 표시 — 실값을 칩 그리드로(기존 basis 한 줄 → 정량 분해). */}
            {asmp && (
              <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1.5">
                  <span className="block text-[10px] text-[var(--text-tertiary)]">DSR</span>
                  <span className="text-xs font-bold text-[var(--text-primary)]">{pct(asmp.dsr)}</span>
                </div>
                <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1.5">
                  <span className="block text-[10px] text-[var(--text-tertiary)]">LTV</span>
                  <span className="text-xs font-bold text-[var(--text-primary)]">{pct(asmp.ltv)}</span>
                </div>
                <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1.5">
                  <span className="block text-[10px] text-[var(--text-tertiary)]">스트레스 금리</span>
                  <span className="text-xs font-bold text-[var(--text-primary)]">{pct(asmp.stress_rate)}</span>
                </div>
                {asmp.term_years != null && (
                  <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1.5">
                    <span className="block text-[10px] text-[var(--text-tertiary)]">대출 만기</span>
                    <span className="text-xs font-bold text-[var(--text-primary)]">{asmp.term_years}년</span>
                  </div>
                )}
                {asmp.pir != null && (
                  <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1.5">
                    <span className="block text-[10px] text-[var(--text-tertiary)]">PIR</span>
                    <span className="text-xs font-bold text-[var(--text-primary)]">{asmp.pir}배</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="mt-3 text-[11px] text-[var(--text-hint)]">지불여력 검증은 「거시 소득 지표(KOSIS)」 선택 시 표시됩니다.</p>
        )}

        {/* 산출 근거 트레이스(공용 EvidencePanel) — 산정방식·가정값·출처를 label=value(basis)로. 응답 실값만. */}
        <EvidencePanel className="mt-3" items={evidenceItems} title="적정 분양가 산출 근거" />

        <p className="mt-3 text-[11px] leading-snug text-[var(--text-hint)]">※ 전문 감정·분양 검토 필수.</p>
      </div>
    </div>
  );
}
