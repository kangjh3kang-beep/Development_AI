"use client";

/**
 * 인구·가구·소득 시각화 패널 (SGIS 센서스 + KOSIS 거시소득).
 *
 * 백엔드 DemographicProfile(population/macro_income)을 Recharts 차트로 시각화한다.
 * - 연령 분포: 가로 막대(연령대별 인구) — 인구 피라미드 형태.
 * - 가구 유형: 파이 차트(1인/2인/3인/4인+).
 * - 거시 소득: 평균·중위 연소득 타일.
 *
 * 정직성: 데이터 출처(data_source)를 DataSourceBadge로 노출.
 *   'unavailable'이면 차트 대신 "데이터 없음" 안내(가짜 차트 금지).
 *   'fallback'(합성·추정)이면 "추정" 배지로 명시.
 * 색상은 토큰만 사용(하드코딩 금지), WCAG AA 대비 유지.
 */

import { Home, Users, Wallet } from "lucide-react";
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList } from "recharts";
import type { DemographicProfile, DataSource, UnitMixRecommendation } from "./marketTypes";
import { DataSourceBadge } from "./DataSourceBadge";

/* eslint-disable @typescript-eslint/no-explicit-any */

// 연령 키 → 한국어 라벨(백엔드 mock/실데이터 키와 통일).
const AGE_LABELS: Record<string, string> = {
  "0s": "10세 미만", "10s": "10대", "20s": "20대", "30s": "30대",
  "40s": "40대", "50s": "50대", "60s_over": "60대+",
};
// 가구 키 → 한국어 라벨.
const HH_LABELS: Record<string, string> = {
  "1_person": "1인 가구", "2_person": "2인 가구", "3_person": "3인 가구", "4_over": "4인 이상",
};

// 파이 색상은 토큰 채널 사용(하드코딩 hex 금지).
const PIE_COLORS = [
  "var(--accent-strong)",
  "var(--data-accent)",
  "color-mix(in srgb, var(--accent-strong) 55%, transparent)",
  "color-mix(in srgb, var(--data-accent) 45%, transparent)",
];

/** age_distribution 값이 숫자 또는 {남:..,여:..} 중첩 맵일 수 있어 안전하게 합산. */
function toCount(v: number | Record<string, number> | undefined): number {
  if (typeof v === "number") return v;
  if (v && typeof v === "object") return Object.values(v).reduce((a, b) => a + (Number(b) || 0), 0);
  return 0;
}

function formatMan(man?: number): string {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const uk = Math.floor(man / 10000);
    const rest = man % 10000;
    return rest > 0 ? `${uk}억 ${rest.toLocaleString()}만원` : `${uk}억원`;
  }
  return `${man.toLocaleString()}만원`;
}

export function DemographicPanel({ data, unitMix }: { data?: DemographicProfile | null; unitMix?: UnitMixRecommendation | null }) {
  if (!data) return null;
  const pop = data.population || {};
  const income = data.macro_income || {};
  // 출처: 프로파일 전체 → 인구 데이터 순으로 추론(명시값 우선).
  const popSource = (data.data_source || (pop as any).data_source) as DataSource | undefined;
  const incomeSource = ((income as any).data_source) as DataSource | undefined;

  // 연령 분포 → 차트 데이터(값이 있는 항목만).
  const ageData = Object.entries(pop.age_distribution || {})
    .map(([k, v]) => ({ label: AGE_LABELS[k] || k, count: toCount(v as any) }))
    .filter((d) => d.count > 0);

  // 가구 유형 → 파이 데이터.
  const hhData = Object.entries(pop.household_types || {})
    .map(([k, v]) => ({ label: HH_LABELS[k] || k, value: Number(v) || 0 }))
    .filter((d) => d.value > 0);

  const hasPop = ageData.length > 0 || hhData.length > 0;
  const hasIncome = (income.avg_income_10k || 0) > 0;

  // 인구·소득 모두 없으면 정직하게 "데이터 없음".
  if (!hasPop && !hasIncome) {
    return (
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden><Users className="size-3.5" /></span>
          <span className="sa-di-block__title">인구·가구·소득 분석</span>
          <DataSourceBadge source="unavailable" />
        </header>
        <div className="sa-di-block__body">
          <p className="sa-di-empty">인구·소득 데이터가 없습니다. (SGIS/KOSIS 미선택 또는 미연동)</p>
        </div>
      </div>
    );
  }

  // I6 수요기반 평형 MD 추천(가구원수 분포 → 권장 전용면적 배분).
  const mix = unitMix?.recommended_mix;
  const hasMix = mix && Object.keys(mix).length > 0;

  return (
    <>
    <div className="grid gap-6 md:grid-cols-2">
      {/* 인구·가구 구조(SGIS) */}
      {hasPop && (
        <div className="sa-di-block">
          <header className="sa-di-block__head" style={{ cursor: "default" }}>
            <span className="sa-di-block__icon" aria-hidden><Users className="size-3.5" /></span>
            <span className="sa-di-block__title">인구·가구 구조</span>
            <DataSourceBadge source={popSource} />
          </header>
          <div className="sa-di-block__body">
            {pop.total_population ? (
              <p className="mb-3 text-xs text-[var(--text-secondary)]">
                총 인구 <b className="text-[var(--text-primary)]">{pop.total_population.toLocaleString()}명</b>
                {popSource === "fallback" && <span className="ml-1 text-[var(--status-warning)]">(추정 분포)</span>}
              </p>
            ) : null}

            {/* 연령 분포 — 가로 막대(인구 피라미드 형태) */}
            {ageData.length > 0 && (
              <div className="mb-4">
                <p className="sa-di-eyebrow mb-2">연령대별 인구</p>
                <ResponsiveContainer width="100%" height={Math.max(140, ageData.length * 28)}>
                  <BarChart data={ageData} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="label" width={56}
                      tick={{ fontSize: 11, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: "color-mix(in srgb, var(--accent-strong) 8%, transparent)" }}
                      formatter={(v: any) => [`${Number(v).toLocaleString()}명`, "인구"]}
                      contentStyle={{ background: "var(--surface-strong)", border: "1px solid var(--line-strong)", borderRadius: 8, fontSize: 12 }}
                    />
                    <Bar dataKey="count" fill="var(--accent-strong)" radius={[0, 4, 4, 0]}>
                      <LabelList dataKey="count" position="right" formatter={(v: any) => Number(v).toLocaleString()}
                        style={{ fontSize: 10, fill: "var(--text-tertiary)" }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* 가구 유형 — 파이 */}
            {hhData.length > 0 && (
              <div>
                <p className="sa-di-eyebrow mb-2">가구원수별 구성</p>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={hhData} dataKey="value" nameKey="label" cx="50%" cy="50%"
                      innerRadius={40} outerRadius={70} paddingAngle={2}
                      label={(p: any) => `${p.label} ${((p.percent ?? 0) * 100).toFixed(0)}%`}
                      labelLine={false} style={{ fontSize: 10 }}>
                      {hhData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip
                      formatter={(v: any, n: any) => [`${Number(v).toLocaleString()}`, n]}
                      contentStyle={{ background: "var(--surface-strong)", border: "1px solid var(--line-strong)", borderRadius: 8, fontSize: 12 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 거시 소득(KOSIS) */}
      {hasIncome && (
        <div className="sa-di-block">
          <header className="sa-di-block__head" style={{ cursor: "default" }}>
            <span className="sa-di-block__icon" aria-hidden><Wallet className="size-3.5" /></span>
            <span className="sa-di-block__title">지역 거시 소득</span>
            <DataSourceBadge source={incomeSource} />
          </header>
          <div className="sa-di-block__body">
            <div className="sa-di-tiles sa-di-tiles--2">
              <div className="sa-di-tile sa-di-tile--accent">
                <span className="sa-di-tile__label">시/군/구 평균 연소득</span>
                <span className="sa-di-tile__value">{formatMan(income.avg_income_10k)}</span>
              </div>
              <div className="sa-di-tile">
                <span className="sa-di-tile__label">중위 연소득</span>
                <span className="sa-di-tile__value">{formatMan(income.median_income_10k)}</span>
              </div>
            </div>

            {/* 소득 구간 비율 */}
            {income.income_bracket_ratio && Object.keys(income.income_bracket_ratio).length > 0 && (
              <div className="mt-3">
                <p className="sa-di-eyebrow mb-2">소득 구간 비율</p>
                <ul className="space-y-1.5 text-xs text-[var(--text-secondary)]">
                  {Object.entries(income.income_bracket_ratio).map(([k, v]) => (
                    <li key={k} className="flex items-center justify-between border-b border-[var(--line-subtle)] pb-1">
                      <span>{k.replace("under_30m", "3천만원 미만").replace("30m_to_70m", "3천~7천만원").replace("over_70m", "7천만원 이상")}</span>
                      <span className="font-bold text-[var(--text-primary)]">{Number(v).toFixed(1)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-3 text-[11px] text-[var(--text-hint)]">
              ※ KOSIS 시/군/구 단위 거시 소득(단위: 만원).
              {incomeSource === "fallback" && " 통계표 확정 전 추정값입니다."}
            </p>
          </div>
        </div>
      )}
    </div>

    {/* I6: 수요기반 평형 MD 추천 */}
    {hasMix && (
      <div className="sa-di-block mt-6">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden><Home className="size-3.5" /></span>
          <span className="sa-di-block__title">수요기반 평형 MD 추천</span>
          <DataSourceBadge source={unitMix?.data_source} />
        </header>
        <div className="sa-di-block__body">
          {unitMix?.rationale && (
            <p className="mb-3 text-sm font-bold text-[var(--text-primary)]">{unitMix.rationale}</p>
          )}
          <p className="sa-di-eyebrow mb-2">권장 전용면적 공급배분</p>
          <div className="space-y-2">
            {Object.entries(mix!).sort((a, b) => b[1] - a[1]).map(([band, pct]) => (
              <div key={band} className="flex items-center gap-2">
                <span className="w-24 shrink-0 text-xs font-semibold text-[var(--text-secondary)]">{band}</span>
                <div className="relative h-4 flex-1 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                  <div className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent-strong)]"
                    style={{ width: `${Math.min(100, pct)}%` }} />
                </div>
                <span className="w-12 shrink-0 text-right text-xs font-bold text-[var(--text-primary)]">{pct}%</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ {unitMix?.basis} 정밀 수익최적 배분은 별도 엔진(SLSQP) 사용.</p>
        </div>
      </div>
    )}
    </>
  );
}
