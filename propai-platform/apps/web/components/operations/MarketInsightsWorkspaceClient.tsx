"use client";

import { useState, useCallback } from "react";
import { Card, CardContent } from "@propai/ui";
import {
  AddressSearchWithRadius,
  type AddressSearchResult,
} from "@/components/ui/AddressSearchWithRadius";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NearbyTransactionsMap } from "@/components/map/NearbyTransactionsMap";
import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/* eslint-disable @typescript-eslint/no-explicit-any */
// PDF/PPTX 바이너리 다운로드용 API 베이스 (api-client 로직 미러)
function marketApiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
}

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type AVMEstimateResponse = {
  estimated_price?: number;
  price_per_sqm?: number;
  confidence_score?: number;
  comparable_count?: number;
  model_version?: string;
};

type TransactionItem = {
  deal_amount?: number;
  deal_year?: string;
  deal_month?: string;
  deal_day?: string;
  area_sqm?: number;
  floor?: number;
  apt_name?: string;
  dong?: string;
  distance_m?: number;
  [key: string]: unknown;
};

type TransactionsResponse = {
  items?: TransactionItem[];
  total_count?: number;
};

type SearchResults = {
  avm: AVMEstimateResponse | null;
  transactions: TransactionItem[];
  totalCount: number;
  searchAddress: string;
  months: number;
  radius: number;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function formatPrice(value: number): string {
  if (value >= 10000) {
    const uk = Math.floor(value / 10000);
    const remainder = value % 10000;
    return remainder > 0
      ? `${uk}억 ${remainder.toLocaleString()}만원`
      : `${uk}억원`;
  }
  return `${value.toLocaleString()}만원`;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function periodToMonths(period: "3m" | "6m" | "1y"): number {
  if (period === "3m") return 3;
  if (period === "6m") return 6;
  return 12;
}

function generateDealYms(months: number): string[] {
  const result: string[] = [];
  const now = new Date();
  for (let i = 0; i < months; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    result.push(`${y}${m}`);
  }
  return result;
}

function groupByRadius(items: TransactionItem[]) {
  const buckets = [
    { label: "반경 500m", max: 500, items: [] as TransactionItem[] },
    { label: "반경 1km", max: 1000, items: [] as TransactionItem[] },
    { label: "반경 3km", max: 3000, items: [] as TransactionItem[] },
    { label: "반경 5km+", max: Infinity, items: [] as TransactionItem[] },
  ];

  for (const tx of items) {
    const dist = tx.distance_m ?? 1000; // 기본 1km 가정
    for (const bucket of buckets) {
      if (dist <= bucket.max) {
        bucket.items.push(tx);
        break;
      }
    }
  }

  return buckets.filter((b) => b.items.length > 0);
}

function averagePrice(items: TransactionItem[]): number {
  const prices = items
    .map((t) => t.deal_amount)
    .filter((v): v is number => v != null);
  if (prices.length === 0) return 0;
  return Math.round(prices.reduce((a, b) => a + b, 0) / prices.length);
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-lg font-bold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function MarketInsightsWorkspaceClient() {
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchAddr, setSearchAddr] = useState("");
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [report, setReport] = useState<any | null>(null);
  const [genState, setGenState] = useState<"" | "report" | "pdf" | "pptx">("");
  const [useLlm, setUseLlm] = useState(true); // LLM AI 분석 포함 여부(사용자 선택)

  // 시장조사보고서: 구조화 미리보기
  const generateReport = useCallback(async () => {
    const addr = siteAnalysis?.address || searchAddr;
    if (!addr) return;
    setGenState("report");
    try {
      const r = await apiClient.post<any>("/market/report", {
        body: { address: addr, pnu: siteAnalysis?.pnu || undefined, use_llm: useLlm },
        useMock: false, timeoutMs: 120000,
      });
      setReport(r);
    } catch {
      setError("보고서 생성에 실패했습니다.");
    } finally {
      setGenState("");
    }
  }, [siteAnalysis, searchAddr, useLlm]);

  // PDF/PPTX 다운로드(바이너리)
  const downloadReport = useCallback(async (fmt: "pdf" | "pptx") => {
    const addr = siteAnalysis?.address || searchAddr;
    if (!addr) return;
    setGenState(fmt);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${marketApiBase()}/market/report/${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ address: addr, pnu: siteAnalysis?.pnu || undefined, use_llm: useLlm }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `시장조사보고서_${addr}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(`${fmt.toUpperCase()} 다운로드에 실패했습니다.`);
    } finally {
      setGenState("");
    }
  }, [siteAnalysis, searchAddr, useLlm]);

  // 검색입력(카카오) 주소 선택 시: AVM 시세추정 조회(지도는 store 주소로 자동 갱신)
  const onAddress = useCallback(async (addr: string) => {
    setSearchAddr(addr);
    if (!addr) return;
    try {
      const avm = await apiClient.post<AVMEstimateResponse>("/avm/estimate", {
        body: { address: addr, area_sqm: 84 }, useMock: false,
      });
      setResults({ avm, transactions: [], totalCount: 0, searchAddress: addr, months: 6, radius: 1000 });
    } catch {
      setResults({ avm: null, transactions: [], totalCount: 0, searchAddress: addr, months: 6, radius: 1000 });
    }
  }, []);

  const handleSearch = useCallback(
    async ({ address, lawdCd, radius, period }: AddressSearchResult) => {
      setLoading(true);
      setError("");
      setResults(null);

      const months = periodToMonths(period);

      try {
        // 1. AVM 시세 추정
        let avm: AVMEstimateResponse | null = null;
        try {
          avm = await apiClient.post<AVMEstimateResponse>("/avm/estimate", {
            body: { address, area_sqm: 84 },
          });
        } catch {
          // AVM 실패 시에도 거래 데이터는 조회 시도
        }

        // 2. 실거래 데이터 조회 (기간별 복수 월)
        const dealYms = generateDealYms(months);
        const allTransactions: TransactionItem[] = [];

        // 최근 월부터 순차 조회 (최대 3개 요청으로 제한)
        const ymBatches = dealYms.slice(0, Math.min(dealYms.length, 3));
        const txPromises = ymBatches.map((ym) =>
          apiClient
            .get<TransactionsResponse>(
              `/external/transactions/apt?lawd_cd=${lawdCd}&deal_ym=${ym}`,
            )
            .catch(() => null),
        );
        const txResults = await Promise.all(txPromises);

        for (const res of txResults) {
          if (res?.items) {
            allTransactions.push(...res.items);
          }
        }

        setResults({
          avm,
          transactions: allTransactions,
          totalCount: allTransactions.length,
          searchAddress: address,
          months,
          radius,
        });
      } catch (err) {
        if (err instanceof ApiClientError) {
          setError(`요청 실패 (${err.status}): API 서버에 연결할 수 없습니다.`);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("요청 처리에 실패했습니다.");
        }
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const radiusGroups = results ? groupByRadius(results.transactions) : [];

  return (
    <section className="grid gap-6">
      {/* 헤더 */}
      <div>
        <h2 className="text-2xl font-black text-[var(--text-primary)]">
          시장 동향 분석
        </h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          주소를 입력하면 주변 실거래가, 시세 추이, 시장 동향을 분석합니다.
        </p>
      </div>

      {/* 검색입력(카카오) — 직접입력 → 주소 검색으로 보강 */}
      <ProjectAddressInput
        value={searchAddr}
        onChange={onAddress}
        label="시장 분석 주소"
        placeholder="주소를 검색하세요 (예: 서울 강남구 역삼동)"
      />

      {/* 필지 구획도 (경계·용도지역·면적) */}
      {(siteAnalysis?.address || searchAddr) && (
        <ParcelBoundaryMap parcels={[siteAnalysis?.address || searchAddr]} />
      )}

      {/* 주변 실거래 지도 — 대상지 강조(깜빡임)·반경·유형별 시세 */}
      <NearbyTransactionsMap />

      {/* 시장조사보고서 생성 (PDF / PPT) */}
      {(siteAnalysis?.address || searchAddr) && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold text-[var(--text-primary)]">📑 시장조사보고서</p>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">주변 실거래·시세·입지를 통합한 심층 보고서를 PDF/PPT로 생성합니다.</p>
                <label className="mt-2 inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
                  <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)}
                    className="h-4 w-4 accent-[var(--accent-strong)]" disabled={!!genState} />
                  🤖 AI 분석 포함 <span className="font-normal text-[var(--text-tertiary)]">(LLM이 시장요약·기회·리스크·가격동향을 작성)</span>
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button onClick={generateReport} disabled={!!genState}
                  className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {genState === "report" ? "생성 중…" : "미리보기 생성"}
                </button>
                <button onClick={() => downloadReport("pdf")} disabled={!!genState}
                  className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pdf" ? "PDF 생성 중…" : "PDF 다운로드"}
                </button>
                <button onClick={() => downloadReport("pptx")} disabled={!!genState}
                  className="rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pptx" ? "PPT 생성 중…" : "PPT 다운로드"}
                </button>
              </div>
            </div>

            {report && (
              <div className="mt-5 space-y-3 border-t border-[var(--line)] pt-4">
                <div>
                  <p className="text-xs font-bold text-[var(--accent-strong)]">시장 요약</p>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{report.narrative?.summary || "-"}</p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="text-xs font-bold text-[var(--accent-strong)]">기회 요인</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                      {(report.narrative?.opportunities || []).map((o: string, i: number) => <li key={i}>· {o}</li>)}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs font-bold text-amber-500">리스크 요인</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                      {(report.narrative?.risks || []).map((r: string, i: number) => <li key={i}>· {r}</li>)}
                    </ul>
                  </div>
                </div>
                {report.narrative?.price_trend && (
                  <div>
                    <p className="text-xs font-bold text-[var(--accent-strong)]">가격 동향</p>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{report.narrative.price_trend}</p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* AI 검증 + 전문가 패널 (보고서 생성 시) */}
      {report && (
        <VerificationBadge analysisType="market" context={report as unknown as Record<string, unknown>} />
      )}
      {report && (
        <ExpertPanelCard
          analysisType="market"
          address={siteAnalysis?.address || searchAddr}
          context={report as unknown as Record<string, unknown>}
        />
      )}

      {/* 에러 */}
      {error && (
        <div className="rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
          {error}
        </div>
      )}

      {/* 결과 */}
      {results && (
        <>
          {/* AVM 시세 추정 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                AI 시세 추정
              </p>
              {results.avm ? (
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricTile
                    label="추정 시세"
                    value={
                      results.avm.estimated_price != null
                        ? formatCurrency(results.avm.estimated_price)
                        : "-"
                    }
                  />
                  <MetricTile
                    label="평당 가격"
                    value={
                      results.avm.price_per_sqm != null
                        ? formatCurrency(results.avm.price_per_sqm)
                        : "-"
                    }
                  />
                  <MetricTile
                    label="신뢰도"
                    value={
                      results.avm.confidence_score != null
                        ? `${(results.avm.confidence_score * 100).toFixed(1)}%`
                        : "-"
                    }
                  />
                  <MetricTile
                    label="비교 사례"
                    value={
                      results.avm.comparable_count != null
                        ? `${results.avm.comparable_count}건`
                        : "-"
                    }
                  />
                </div>
              ) : (
                <p className="mt-4 text-sm text-[var(--text-secondary)]">
                  AI 시세 추정 데이터가 없습니다.
                </p>
              )}
            </CardContent>
          </Card>

          {/* 주변 실거래 현황 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                주변 실거래 현황
              </p>
              <div className="mt-3 flex flex-wrap items-baseline gap-4">
                <p className="text-lg font-bold text-[var(--text-primary)]">
                  최근 {results.months}개월간{" "}
                  <span className="text-[var(--accent-strong)]">
                    {results.totalCount}건
                  </span>{" "}
                  거래
                </p>
                {results.totalCount > 0 && (
                  <p className="text-sm text-[var(--text-secondary)]">
                    평균 거래가:{" "}
                    {formatPrice(averagePrice(results.transactions))}
                  </p>
                )}
              </div>

              {/* 반경별 분류 */}
              {radiusGroups.length > 0 && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {radiusGroups.map((group) => (
                    <div
                      key={group.label}
                      className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4"
                    >
                      <p className="text-xs font-semibold text-[var(--text-tertiary)]">
                        {group.label}
                      </p>
                      <p className="mt-1 text-sm font-bold text-[var(--text-primary)]">
                        {group.items.length}건
                      </p>
                      <p className="text-xs text-[var(--text-secondary)]">
                        평균 {formatPrice(averagePrice(group.items))}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {results.totalCount === 0 && (
                <p className="mt-4 text-sm text-[var(--text-secondary)]">
                  조건에 맞는 실거래 데이터가 없습니다.
                </p>
              )}
            </CardContent>
          </Card>

          {/* 실거래 상세 내역 */}
          {results.transactions.length > 0 && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                  실거래 상세 내역
                </p>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                        <th className="pb-3 pr-4">거래일</th>
                        <th className="pb-3 pr-4">단지명</th>
                        <th className="pb-3 pr-4">면적</th>
                        <th className="pb-3 pr-4">층</th>
                        <th className="pb-3">거래가</th>
                      </tr>
                    </thead>
                    <tbody>
                      {results.transactions.slice(0, 50).map((tx, idx) => (
                        <tr
                          key={idx}
                          className="border-t border-[var(--line)]"
                        >
                          <td className="py-3 pr-4 text-[var(--text-secondary)]">
                            {tx.deal_year ?? ""}.{tx.deal_month ?? ""}.
                            {tx.deal_day ?? ""}
                          </td>
                          <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                            {tx.apt_name ?? "-"}
                          </td>
                          <td className="py-3 pr-4 text-[var(--text-secondary)]">
                            {tx.area_sqm != null
                              ? `${tx.area_sqm}m\u00B2`
                              : "-"}
                          </td>
                          <td className="py-3 pr-4 text-[var(--text-secondary)]">
                            {tx.floor != null ? `${tx.floor}층` : "-"}
                          </td>
                          <td className="py-3 font-semibold text-[var(--text-primary)]">
                            {tx.deal_amount != null
                              ? formatPrice(tx.deal_amount)
                              : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {results.transactions.length > 50 && (
                    <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                      상위 50건만 표시 (전체 {results.transactions.length}건)
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* 초기 상태 안내 */}
      {!results && !loading && !error && (
        <Card className="rounded-[var(--radius-2xl)]">
          <CardContent className="p-8 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              주소를 검색하면 AI 시세 추정과 주변 실거래 현황이 표시됩니다.
            </p>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
