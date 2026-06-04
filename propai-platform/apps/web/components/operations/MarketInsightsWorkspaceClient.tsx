"use client";

import { useCallback, useMemo, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NearbyTransactionsMap, type NearbyMapPayload } from "@/components/map/NearbyTransactionsMap";
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

type AvmSummary = {
  estimated_price: number; // 원
  price_per_sqm: number;   // 원/㎡
  confidence_score: number;
  comparable_count: number;
};

type TxItem = {
  deal_amount?: number; // 만원
  deal_year?: string; deal_month?: string; deal_day?: string;
  area_sqm?: number; floor?: number | string; apt_name?: string; distance_m?: number;
};

type RadiusBucket = { label: string; count: number; avgPrice: number /* 만원 */ };

type MarketResults = {
  avm: AvmSummary | null;
  totalCount: number;
  avgPrice: number; // 만원
  radiusGroups: RadiusBucket[];
  transactions: TxItem[];
  months: number;
  radius: number;
  searchAddress: string;
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

const PYEONG = 3.305785;

function formatPrice(man: number): string {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const uk = Math.floor(man / 10000);
    const rest = man % 10000;
    return rest > 0 ? `${uk}억 ${rest.toLocaleString()}만원` : `${uk}억원`;
  }
  return `${man.toLocaleString()}만원`;
}

function formatCurrency(won: number): string {
  return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(won);
}

function distanceM(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const R = 6371000, toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat), dLon = toRad(bLon - aLon);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

function parseDealDate(s?: string): { deal_year?: string; deal_month?: string; deal_day?: string } {
  if (!s) return {};
  const m = s.match(/(\d{4})\D+(\d{1,2})(?:\D+(\d{1,2}))?/);
  if (!m) return {};
  return { deal_year: m[1], deal_month: m[2], deal_day: m[3] };
}

/** nearby-map 단일 데이터원 → 실거래 현황 + AI 시세(실거래 비교 기반). */
function deriveResults(payload: NearbyMapPayload | null, fallbackAddr: string): MarketResults | null {
  if (!payload) return null;
  const center = payload.center;
  const cats = payload.categories || {};
  const tradeEntries = Object.entries(cats).filter(([k]) => k.endsWith("_trade"));

  const totalCount = tradeEntries.reduce((a, [, c]) => a + (c.count || 0), 0);

  const buckets = [
    { label: "반경 500m", max: 500, count: 0, pSum: 0, pN: 0 },
    { label: "반경 1km", max: 1000, count: 0, pSum: 0, pN: 0 },
    { label: "반경 3km", max: 3000, count: 0, pSum: 0, pN: 0 },
    { label: "반경 5km+", max: Infinity, count: 0, pSum: 0, pN: 0 },
  ];
  const transactions: TxItem[] = [];
  let allPSum = 0, allPN = 0;

  for (const [, c] of tradeEntries) {
    for (const g of c.groups || []) {
      const dist = center?.lat && g.lat ? distanceM(center.lat, center.lon as number, g.lat, g.lon) : 1000;
      const cnt = g.count || 0;
      if (g.avg_price_10k) { allPSum += g.avg_price_10k * (cnt || 1); allPN += cnt || 1; }
      for (const b of buckets) {
        if (dist <= b.max) {
          b.count += cnt;
          if (g.avg_price_10k) { b.pSum += g.avg_price_10k * (cnt || 1); b.pN += cnt || 1; }
          break;
        }
      }
      for (const d of g.deals || []) {
        transactions.push({
          deal_amount: d.price_10k_won, area_sqm: d.area_m2, floor: d.floor,
          apt_name: g.name, distance_m: Math.round(dist), ...parseDealDate(d.deal_date),
        });
      }
    }
  }

  const radiusGroups: RadiusBucket[] = buckets
    .filter((b) => b.count > 0)
    .map((b) => ({ label: b.label, count: b.count, avgPrice: b.pN ? Math.round(b.pSum / b.pN) : 0 }));

  // AI 시세: 아파트 매매 실거래 평당가 가중평균 → 84㎡ 기준 추정
  const apt = cats["apt_trade"];
  let avm: AvmSummary | null = null;
  if (apt?.groups?.length) {
    let ppSum = 0, ppN = 0;
    for (const g of apt.groups) {
      if (g.avg_price_10k && g.avg_area_m2 > 0) {
        const perPyeong = g.avg_price_10k / (g.avg_area_m2 / PYEONG);
        ppSum += perPyeong * (g.count || 1); ppN += g.count || 1;
      }
    }
    if (ppN > 0) {
      const perPyeong = ppSum / ppN;        // 만원/평
      const perM2man = perPyeong / PYEONG;  // 만원/㎡
      avm = {
        estimated_price: Math.round(perM2man * 84 * 10000),
        price_per_sqm: Math.round(perM2man * 10000),
        confidence_score: Math.min(0.95, 0.5 + Math.log10((apt.count || 0) + 1) / 4),
        comparable_count: apt.count || 0,
      };
    }
  }

  return {
    avm, totalCount,
    avgPrice: allPN ? Math.round(allPSum / allPN) : 0,
    radiusGroups, transactions,
    months: payload.months?.length || 3,
    radius: payload.radius_m || 1000,
    searchAddress: center?.address || fallbackAddr,
  };
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{label}</p>
      <p className="mt-2 text-lg font-bold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function MarketInsightsWorkspaceClient() {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const [searchAddr, setSearchAddr] = useState("");
  const [mapPayload, setMapPayload] = useState<NearbyMapPayload | null>(null);
  const [mapLoading, setMapLoading] = useState(false);
  const [report, setReport] = useState<any | null>(null);
  const [genState, setGenState] = useState<"" | "report" | "pdf" | "pptx">("");
  const [useLlm, setUseLlm] = useState(true);
  const [error, setError] = useState("");

  const address = siteAnalysis?.address || searchAddr;
  const results = useMemo(() => deriveResults(mapPayload, address), [mapPayload, address]);

  // 주소 선택/변경 → store 주소 갱신(지도·산출 단일화). 지도가 nearby-map을 재조회한다.
  const onAddress = useCallback((addr: string) => {
    setSearchAddr(addr);
    if (addr && addr !== siteAnalysis?.address) {
      setMapPayload(null);
      updateSiteAnalysis({ address: addr });
    }
  }, [siteAnalysis?.address, updateSiteAnalysis]);

  // 시장조사보고서: 구조화 미리보기
  const generateReport = useCallback(async () => {
    if (!address) return;
    setGenState("report");
    try {
      const r = await apiClient.post<any>("/market/report", {
        body: { address, pnu: siteAnalysis?.pnu || undefined, use_llm: useLlm },
        useMock: false, timeoutMs: 120000,
      });
      setReport(r);
    } catch {
      setError("보고서 생성에 실패했습니다.");
    } finally {
      setGenState("");
    }
  }, [address, siteAnalysis?.pnu, useLlm]);

  // PDF/PPTX 다운로드(바이너리)
  const downloadReport = useCallback(async (fmt: "pdf" | "pptx") => {
    if (!address) return;
    setGenState(fmt);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${marketApiBase()}/market/report/${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ address, pnu: siteAnalysis?.pnu || undefined, use_llm: useLlm }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `시장조사보고서_${address}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(`${fmt.toUpperCase()} 다운로드에 실패했습니다.`);
    } finally {
      setGenState("");
    }
  }, [address, siteAnalysis?.pnu, useLlm]);

  return (
    <section className="grid gap-6">
      {/* 헤더 */}
      <div>
        <h2 className="text-2xl font-black text-[var(--text-primary)]">시장 동향 분석</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          주소를 입력하면 주변 실거래가·시세 추이·시장 동향을 <b className="text-[var(--text-primary)]">자동으로 분석</b>합니다. (별도 실행 버튼 없이 주소 기준 즉시 분석)
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
      {address && <ParcelBoundaryMap parcels={[address]} />}

      {/* 주변 실거래 지도 — 단일 데이터원(payload를 부모와 공유) */}
      <NearbyTransactionsMap onPayload={setMapPayload} onLoading={setMapLoading} />

      {/* 시장조사보고서 생성 (PDF / PPT) */}
      {address && (
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
                  className="whitespace-nowrap rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                  {genState === "report" ? "생성 중…" : "미리보기 생성"}
                </button>
                <button onClick={() => downloadReport("pdf")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                  {genState === "pdf" ? "PDF 생성 중…" : "PDF 다운로드"}
                </button>
                <button onClick={() => downloadReport("pptx")} disabled={!!genState}
                  className="whitespace-nowrap rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
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
      {report && <VerificationBadge analysisType="market" context={report as unknown as Record<string, unknown>} />}
      {report && (
        <ExpertPanelCard analysisType="market" address={address} context={report as unknown as Record<string, unknown>} />
      )}

      {/* 에러 */}
      {error && (
        <div className="rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
          {error}
        </div>
      )}

      {/* AI 시세 추정 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">AI 시세 추정</p>
          {results?.avm ? (
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricTile label="추정 시세 (84㎡)" value={formatCurrency(results.avm.estimated_price)} />
              <MetricTile label="㎡당 시세" value={formatCurrency(results.avm.price_per_sqm)} />
              <MetricTile label="신뢰도" value={`${(results.avm.confidence_score * 100).toFixed(0)}%`} />
              <MetricTile label="비교 사례" value={`${results.avm.comparable_count.toLocaleString()}건`} />
            </div>
          ) : mapLoading || (address && !mapPayload) ? (
            <p className="mt-4 text-sm text-[var(--text-secondary)]">주변 실거래를 수집해 시세를 추정하는 중…</p>
          ) : (
            <p className="mt-4 text-sm text-[var(--text-secondary)]">
              {address ? "주변 아파트 실거래가 없어 시세를 추정할 수 없습니다." : "주소를 입력하면 AI 시세가 표시됩니다."}
            </p>
          )}
          {results?.avm && (
            <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 주변 아파트 실거래 평당가 가중평균을 84㎡ 기준으로 환산한 참고 추정치입니다.</p>
          )}
        </CardContent>
      </Card>

      {/* 주변 실거래 현황 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">주변 실거래 현황</p>
          {mapLoading || (address && !mapPayload) ? (
            <p className="mt-4 text-sm text-[var(--text-secondary)]">주변 실거래를 수집하는 중…</p>
          ) : results ? (
            <>
              <div className="mt-3 flex flex-wrap items-baseline gap-4">
                <p className="text-lg font-bold text-[var(--text-primary)]">
                  최근 {results.months}개월간{" "}
                  <span className="text-[var(--accent-strong)]">{results.totalCount.toLocaleString()}건</span> 거래
                </p>
                {results.avgPrice > 0 && (
                  <p className="text-sm text-[var(--text-secondary)]">매매 평균 거래가: {formatPrice(results.avgPrice)}</p>
                )}
              </div>

              {results.radiusGroups.length > 0 && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {results.radiusGroups.map((group) => (
                    <div key={group.label} className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                      <p className="text-xs font-semibold text-[var(--text-tertiary)]">{group.label}</p>
                      <p className="mt-1 text-sm font-bold text-[var(--text-primary)]">{group.count.toLocaleString()}건</p>
                      <p className="text-xs text-[var(--text-secondary)]">평균 {formatPrice(group.avgPrice)}</p>
                    </div>
                  ))}
                </div>
              )}

              {results.totalCount === 0 && (
                <p className="mt-4 text-sm text-[var(--text-secondary)]">조건에 맞는 실거래 데이터가 없습니다.</p>
              )}
            </>
          ) : (
            <p className="mt-4 text-sm text-[var(--text-secondary)]">주소를 입력하면 주변 실거래 현황이 표시됩니다.</p>
          )}
        </CardContent>
      </Card>

      {/* 실거래 상세 내역 */}
      {results && results.transactions.length > 0 && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">실거래 상세 내역</p>
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
                    <tr key={idx} className="border-t border-[var(--line)]">
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {tx.deal_year ?? ""}{tx.deal_month ? `.${tx.deal_month}` : ""}{tx.deal_day ? `.${tx.deal_day}` : ""}
                      </td>
                      <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">{tx.apt_name ?? "-"}</td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">{tx.area_sqm != null ? `${tx.area_sqm}㎡` : "-"}</td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">{tx.floor != null ? `${tx.floor}층` : "-"}</td>
                      <td className="py-3 font-semibold text-[var(--text-primary)]">{tx.deal_amount != null ? formatPrice(tx.deal_amount) : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {results.transactions.length > 50 && (
                <p className="mt-3 text-xs text-[var(--text-tertiary)]">상위 50건만 표시 (표본 {results.transactions.length}건 · 전체 {results.totalCount.toLocaleString()}건)</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
