"use client";

/**
 * 실데이터(RAW) 표 모음 — 시장·시세 분석 보고서의 "분석 이전" 원천 데이터 구간.
 *
 * 사용자 핵심지침: "실데이터 표를 먼저 나열 → 분석은 그 다음".
 * 백엔드 report.raw_data(P2에서 신설)를 받아 표(table)로만 보여주는 표시 전용 컴포넌트.
 *
 * 정직성 원칙(가짜값 금지):
 * - provider가 안 준 값(null)은 "-"로 표기(임의 추정 금지).
 * - 표 전체가 비었거나 모든 값이 null이면 "데이터 없음/연동 예정"을 정직하게 안내(빈 표 금지).
 * - 추정값(estimated=true)은 작은 "추정" 표기로 명시.
 * - 데이터 출처(data_source)는 DataSourceBadge로 그대로 노출.
 *
 * 스타일: 기존 데이터 인텔리전스 클래스(sa-di-*)만 재사용 → 보고서 전체 톤 통일.
 * 색상은 전부 토큰(하드코딩 금지), 숫자는 sa-di-num(우측정렬·mono)·천단위 콤마.
 */

import { BarChart3, Home, Users, Wallet } from "lucide-react";
import type { DataSource } from "./marketTypes";
import { DataSourceBadge } from "./DataSourceBadge";
import { formatManwon as man, formatYm } from "@/lib/formatters";

/* ------------------------------------------------------------------ */
/*  raw_data 타입 (백엔드 P2 스키마)                                   */
/* ------------------------------------------------------------------ */

export interface RawTradeRow {
  type: string;
  count: number;
  avg_10k: number;
  min_10k: number;
  max_10k: number;
  avg_area_m2: number;
  per_pyeong_manwon: number | null;
}

export interface RawRentRow {
  type: string;
  count: number;
  avg_10k: number;
  min_10k: number;
  max_10k: number;
}

export interface RawTrendPoint {
  ym: string;
  per_pyeong_manwon: number | null;
  mom_pct: number | null; // 전월대비% (첫 항목 null)
}

/** 경쟁 단지 집계 행 — 주변 실거래를 단지명별로 묶은 것(백엔드 /market/report 산출). */
export interface RawCompetitorComplex {
  name?: string;
  deal_count?: number;
  avg_per_pyeong_manwon?: number | null;
  price_basis?: string;
  recent_deal_ym?: string | null;
  build_year?: number | null;
}

export interface RawRealEstate {
  trade_table: RawTradeRow[];
  rent_table: RawRentRow[];
  trend_series: RawTrendPoint[];
  source: string;
  data_source: DataSource | string;
  competitor_complexes?: RawCompetitorComplex[];
}

export interface RawPopulation {
  summary: {
    total_population: number | null;
    household_count: number | null;
    avg_household_size: number | null;
  };
  age_distribution: { label: string; count: number }[];
  household_types: { label: string; ratio: number; estimated?: boolean }[];
  migration: {
    total_inflow: number | null;
    total_outflow: number | null;
    net_migration: number | null;
  };
  source: string;
  data_source: string;
  migration_data_source: string;
}

export interface RawIncome {
  avg_income_10k: number | null;
  median_income_10k: number | null;
  median_estimated?: boolean;
  basis: { persons: number | null; total_salary_10k: number | null };
  bracket_ratio: null | Record<string, number>;
  source: string;
  data_source: string;
}

export interface RawData {
  real_estate: RawRealEstate;
  population?: RawPopulation;
  income?: RawIncome;
}

/* ------------------------------------------------------------------ */
/*  헬퍼 (이 컴포넌트 내부 전용 — 기존 formatPrice 패턴 참고)          */
/* ------------------------------------------------------------------ */

/** 평당가(만원/평) → "N,NNN만원/평". null이면 "-". */
function perPyeong(v: number | null): string {
  if (v == null || v <= 0) return "-";
  return `${Math.round(v).toLocaleString()}만원/평`;
}

/** 면적(㎡) → "N.N㎡". 값 없으면 "-". */
function area(v?: number | null): string {
  if (v == null || v <= 0) return "-";
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}㎡`;
}

/** 인원·건수 등 정수 → 천단위 콤마. null이면 "-". */
function num(v?: number | null, unit = ""): string {
  if (v == null) return "-";
  return `${v.toLocaleString()}${unit}`;
}

/** 비율(%) → "N.N%". null이면 "-". */
function pct(v?: number | null): string {
  if (v == null) return "-";
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

/** 작은 "추정" 표기 — 추정값임을 정직하게 알린다. */
function EstimatedTag() {
  return (
    <span
      className="ml-1 rounded px-1 py-0.5 text-[9px] font-bold"
      style={{ color: "var(--status-warning)", backgroundColor: "color-mix(in srgb, var(--status-warning) 12%, transparent)" }}
    >
      추정
    </span>
  );
}

/** 표 전체가 비었을 때 정직 안내(가짜 빈 표 금지). */
function EmptyNote({ children }: { children: React.ReactNode }) {
  return <p className="sa-di-empty">{children}</p>;
}

/** data_source 문자열 → DataSourceBadge가 받는 DataSource 유니온으로 안전 매핑. */
function asSource(s?: string): DataSource | undefined {
  if (s === "live" || s === "fallback" || s === "mock" || s === "unavailable") return s;
  return undefined;
}

/* ------------------------------------------------------------------ */
/*  메인 컴포넌트                                                      */
/* ------------------------------------------------------------------ */

export function RawDataTables({ raw, section }: { raw: RawData | undefined; section?: "real_estate" | "demand" }) {
  // raw 자체가 없으면(보고서 미생성·구버전 응답) 아무것도 렌더하지 않는다.
  if (!raw) return null;

  // section: 'real_estate'면 매매·전월세·추이 표만, 'demand'면 인구·소득 표만 렌더.
  //   워크스페이스가 '가격·시세'/'수요·인구' 그룹에 각각 접힘 원자료로 인접 배치하기 위한 분할.
  //   (미지정이면 전체 — 하위호환.)
  const showRE = !section || section === "real_estate";
  const showDemand = !section || section === "demand";

  const re = raw.real_estate;
  const pop = raw.population;
  const inc = raw.income;

  const tradeRows = re?.trade_table ?? [];
  const rentRows = re?.rent_table ?? [];
  const trendRows = re?.trend_series ?? [];

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {showRE && (<>
      {/* 1) 유형별 매매 시세 */}
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden>≣</span>
          <span className="sa-di-block__title">유형별 매매 시세</span>
          <DataSourceBadge source={asSource(re?.data_source as string)} />
        </header>
        <div className="sa-di-block__body">
          {tradeRows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="sa-di-table">
                <thead>
                  <tr>
                    <th>유형</th>
                    <th className="sa-di-num">거래건수</th>
                    <th className="sa-di-num">평균가</th>
                    <th className="sa-di-num">평당가</th>
                    <th className="sa-di-num">평균면적</th>
                  </tr>
                </thead>
                <tbody>
                  {tradeRows.map((r, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{r.type}</td>
                      <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{num(r.count, "건")}</td>
                      <td className="sa-di-num">{man(r.avg_10k)}</td>
                      <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{perPyeong(r.per_pyeong_manwon)}</td>
                      <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{area(r.avg_area_m2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyNote>유형별 매매 실거래 데이터가 없습니다. (연동 예정 또는 조회 결과 없음)</EmptyNote>
          )}
        </div>
      </div>

      {/* 2) 전월세 시세 */}
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden>≣</span>
          <span className="sa-di-block__title">전월세 시세</span>
          <DataSourceBadge source={asSource(re?.data_source as string)} />
        </header>
        <div className="sa-di-block__body">
          {rentRows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="sa-di-table">
                <thead>
                  <tr>
                    <th>유형</th>
                    <th className="sa-di-num">건수</th>
                    <th className="sa-di-num">평균 보증금</th>
                  </tr>
                </thead>
                <tbody>
                  {rentRows.map((r, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{r.type}</td>
                      <td className="sa-di-num" style={{ color: "var(--text-secondary)" }}>{num(r.count, "건")}</td>
                      <td className="sa-di-num">{man(r.avg_10k)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyNote>전월세 실거래 데이터가 없습니다. (연동 예정 또는 조회 결과 없음)</EmptyNote>
          )}
        </div>
      </div>

      {/* 3) 시세 추이 (월별 평당가) */}
      <div className="sa-di-block">
        <header className="sa-di-block__head" style={{ cursor: "default" }}>
          <span className="sa-di-block__icon" aria-hidden>≣</span>
          <span className="sa-di-block__title">시세 추이 (월별 평당가)</span>
          <DataSourceBadge source={asSource(re?.data_source as string)} />
        </header>
        <div className="sa-di-block__body">
          {trendRows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="sa-di-table">
                <thead>
                  <tr>
                    <th>연월</th>
                    <th className="sa-di-num">평당가</th>
                    <th className="sa-di-num">전월대비</th>
                  </tr>
                </thead>
                <tbody>
                  {trendRows.map((r, i) => {
                    // 전월대비: +면 상승(성공색)·-면 하락(위험색)·null이면 "-"(첫 항목).
                    const mom = r.mom_pct;
                    const momColor =
                      mom == null ? "var(--text-tertiary)" : mom > 0 ? "var(--status-success)" : mom < 0 ? "var(--status-error)" : "var(--text-secondary)";
                    const momText = mom == null ? "-" : `${mom > 0 ? "+" : ""}${mom.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
                    return (
                      <tr key={i}>
                        <td className="sa-di-num" style={{ textAlign: "left", color: "var(--text-secondary)" }}>{formatYm(r.ym)}</td>
                        <td className="sa-di-num">{perPyeong(r.per_pyeong_manwon)}</td>
                        <td className="sa-di-num" style={{ color: momColor, fontWeight: 700 }}>{momText}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyNote>월별 시세 추이 데이터가 없습니다. (연동 예정 또는 조회 결과 없음)</EmptyNote>
          )}
        </div>
      </div>

      </>)}
      {showDemand && (<>
      {/* 4) 인구 규모·가구 (population 선택 시에만 키 존재) */}
      {pop && (
        <>
          <div className="sa-di-block">
            <header className="sa-di-block__head" style={{ cursor: "default" }}>
              <span className="sa-di-block__icon" aria-hidden><Users className="size-3.5" /></span>
              <span className="sa-di-block__title">인구 규모·가구</span>
              <DataSourceBadge source={asSource(pop.data_source)} />
            </header>
            <div className="sa-di-block__body">
              {pop.summary.total_population != null || pop.summary.household_count != null || pop.summary.avg_household_size != null ? (
                <div className="sa-di-tiles sa-di-tiles--3">
                  <div className="sa-di-tile">
                    <span className="sa-di-tile__label">총 인구</span>
                    <span className="sa-di-tile__value">{num(pop.summary.total_population, "명")}</span>
                  </div>
                  <div className="sa-di-tile">
                    <span className="sa-di-tile__label">가구 수</span>
                    <span className="sa-di-tile__value">{num(pop.summary.household_count, "가구")}</span>
                  </div>
                  <div className="sa-di-tile">
                    <span className="sa-di-tile__label">평균 가구원수</span>
                    <span className="sa-di-tile__value">
                      {pop.summary.avg_household_size != null
                        ? `${pop.summary.avg_household_size.toLocaleString(undefined, { maximumFractionDigits: 2 })}인`
                        : "-"}
                    </span>
                  </div>
                </div>
              ) : (
                <EmptyNote>인구 규모·가구 데이터가 없습니다. (연동 예정)</EmptyNote>
              )}
            </div>
          </div>

          {/* 연령대 분포 — 라벨·인원 + 간단 가로 막대(width %) */}
          <div className="sa-di-block">
            <header className="sa-di-block__head" style={{ cursor: "default" }}>
              <span className="sa-di-block__icon" aria-hidden><BarChart3 className="size-3.5" /></span>
              <span className="sa-di-block__title">연령대 분포</span>
              <DataSourceBadge source={asSource(pop.data_source)} />
            </header>
            <div className="sa-di-block__body">
              {(pop.age_distribution?.length ?? 0) > 0 ? (
                <div className="overflow-x-auto">
                  <table className="sa-di-table">
                    <thead>
                      <tr>
                        <th>연령대</th>
                        <th className="sa-di-num">인원</th>
                        <th style={{ width: "40%" }}>비중</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        // 가로 막대 폭 계산용 최댓값(상대 비교). 0 방어.
                        const maxCount = Math.max(1, ...pop.age_distribution.map((a) => a.count || 0));
                        return pop.age_distribution.map((a, i) => (
                          <tr key={i}>
                            <td style={{ fontWeight: 600 }}>{a.label}</td>
                            <td className="sa-di-num">{num(a.count, "명")}</td>
                            <td>
                              <div className="relative h-3 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
                                <div
                                  className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent-strong)]"
                                  style={{ width: `${Math.min(100, ((a.count || 0) / maxCount) * 100)}%` }}
                                />
                              </div>
                            </td>
                          </tr>
                        ));
                      })()}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyNote>연령대 분포 데이터가 없습니다. (연동 예정)</EmptyNote>
              )}
            </div>
          </div>

          {/* 가구원수 분포 — 라벨·비율% (estimated=true면 "추정" 표기) */}
          <div className="sa-di-block">
            <header className="sa-di-block__head" style={{ cursor: "default" }}>
              <span className="sa-di-block__icon" aria-hidden><Home className="size-3.5" /></span>
              <span className="sa-di-block__title">가구원수 분포</span>
              <DataSourceBadge source={asSource(pop.data_source)} />
            </header>
            <div className="sa-di-block__body">
              {(pop.household_types?.length ?? 0) > 0 ? (
                <div className="overflow-x-auto">
                  <table className="sa-di-table">
                    <thead>
                      <tr>
                        <th>가구 유형</th>
                        <th className="sa-di-num">비율</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pop.household_types.map((h, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>
                            {h.label}
                            {h.estimated ? <EstimatedTag /> : null}
                          </td>
                          <td className="sa-di-num">{pct(h.ratio)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyNote>가구원수 분포 데이터가 없습니다. (연동 예정)</EmptyNote>
              )}
            </div>
          </div>

          {/* 인구 이동 블록 제거(중복 해소) — 워크스페이스의 '인구 이동망' 패널이 정본.
              RawData(표)에서는 순이동 타일 중복을 없앤다(전입·전출·순이동은 인구 이동망 참조). */}
        </>
      )}

      {/* 5) 소득 (income 선택 시에만 키 존재) */}
      {inc && (
        <div className="sa-di-block">
          <header className="sa-di-block__head" style={{ cursor: "default" }}>
            <span className="sa-di-block__icon" aria-hidden><Wallet className="size-3.5" /></span>
            <span className="sa-di-block__title">평균·중위 연소득</span>
            <DataSourceBadge source={asSource(inc.data_source)} />
          </header>
          <div className="sa-di-block__body">
            {inc.avg_income_10k != null || inc.median_income_10k != null ? (
              <div className="sa-di-tiles sa-di-tiles--2">
                <div className="sa-di-tile sa-di-tile--accent">
                  <span className="sa-di-tile__label">평균 연소득</span>
                  <span className="sa-di-tile__value">{man(inc.avg_income_10k)}</span>
                </div>
                <div className="sa-di-tile">
                  <span className="sa-di-tile__label">
                    중위 연소득
                    {inc.median_estimated ? <EstimatedTag /> : null}
                  </span>
                  <span className="sa-di-tile__value">{man(inc.median_income_10k)}</span>
                </div>
              </div>
            ) : (
              <EmptyNote>연소득 데이터가 없습니다. (연동 예정)</EmptyNote>
            )}

            {/* 소득 산출 근거 — 인원·총급여(둘 다 null이면 정직하게 "원자료 미제공") */}
            <div className="sa-di-sub mt-3">
              <p className="sa-di-eyebrow mb-2">소득 산출 근거</p>
              {inc.basis.persons == null && inc.basis.total_salary_10k == null ? (
                <p className="text-xs text-[var(--text-tertiary)]">원자료 미제공 (provider가 산출 근거를 내려주지 않음)</p>
              ) : (
                <div className="sa-di-tiles sa-di-tiles--2">
                  <div className="sa-di-tile">
                    <span className="sa-di-tile__label">근로소득 인원</span>
                    <span className="sa-di-tile__value">{num(inc.basis.persons, "명")}</span>
                  </div>
                  <div className="sa-di-tile">
                    <span className="sa-di-tile__label">총급여</span>
                    <span className="sa-di-tile__value">{man(inc.basis.total_salary_10k)}</span>
                  </div>
                </div>
              )}
            </div>

            {/* 소득 구간 분포 — null이면 회색 "데이터 없음" */}
            <div className="mt-3">
              <p className="sa-di-eyebrow mb-2">소득 구간 분포</p>
              {inc.bracket_ratio && Object.keys(inc.bracket_ratio).length > 0 ? (
                <ul className="space-y-1.5 text-xs text-[var(--text-secondary)]">
                  {Object.entries(inc.bracket_ratio).map(([k, v]) => (
                    <li key={k} className="flex items-center justify-between border-b border-[var(--line-subtle)] pb-1">
                      <span>{k}</span>
                      <span className="font-bold text-[var(--text-primary)]">{pct(Number(v))}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-[var(--text-tertiary)]">소득 구간 분포: 데이터 없음</p>
              )}
            </div>
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}
