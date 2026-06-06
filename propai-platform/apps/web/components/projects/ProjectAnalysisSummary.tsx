"use client";

/**
 * 프로젝트 분석 요약 — 재열람용 보고서 스타일 뷰.
 * useProjectContextStore(복원·영속된 단일 데이터원)를 읽어 핵심요약 + 섹션 카드로 표시.
 * (거대 타이포·목업 상수 없이 실데이터 중심의 정보밀도·가독성 우선)
 */

import { useEffect, useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { verifyLedger } from "@/lib/analysis-ledger";
import { SiteScoreCard } from "@/components/projects/SiteScoreCard";
import { BuildableEnvelopeCard } from "@/components/projects/BuildableEnvelopeCard";
import { DataLineageTooltip } from "@/components/common/DataLineageTooltip";
import { formatAnalysisValue } from "@/lib/formatters";

const eok = (won: number | null | undefined): string | null =>
  won != null ? `${(won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억` : null;
const num = (v: number | null | undefined, unit = ""): string => formatAnalysisValue(v, unit);
const pct = (v: number | null | undefined): string =>
  v != null ? `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}%` : "분석 전";

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      <p className={`mt-1.5 text-xl font-[1000] tracking-tight ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}

function Section({
  title,
  rows,
  dataSource,
  fetchedAt,
}: {
  title: string;
  rows: Array<[string, string]>;
  dataSource?: string | null;
  fetchedAt?: string | null;
}) {
  const empty = rows.every(([, v]) => v === "—" || v === "분석 전");
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <h4 className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
          {title}
          <DataLineageTooltip dataSource={dataSource} fetchedAt={fetchedAt} />
        </h4>
        {empty ? <span className="text-[10px] font-bold text-[var(--text-hint)]">분석 전</span> : null}
      </div>
      <dl className="mt-3 divide-y divide-[var(--line)]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between py-2">
            <dt className="text-xs text-[var(--text-secondary)]">{k}</dt>
            <dd className={`text-sm font-semibold ${v === "—" || v === "분석 전" ? "text-[var(--text-hint)]" : "text-[var(--text-primary)]"}`}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function ProjectAnalysisSummary() {
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const design = useProjectContextStore((s) => s.designData);
  const cost = useProjectContextStore((s) => s.costData);
  const feas = useProjectContextStore((s) => s.feasibilityData);
  const esg = useProjectContextStore((s) => s.esgData);
  const comp = useProjectContextStore((s) => s.complianceData);
  const projectId = useProjectContextStore((s) => s.projectId);

  // 분석 원장 무결성 배지(변조방지 해시체인 검증)
  const [integrity, setIntegrity] = useState<{ verified: boolean; version?: number } | null>(null);
  useEffect(() => {
    const addr = site?.address;
    if (!addr) { setIntegrity(null); return; }
    let alive = true;
    void verifyLedger("pipeline", { address: addr, projectId: projectId || undefined }).then((v) => {
      if (alive && v?.ok && v.length) setIntegrity({ verified: !!v.verified, version: v.head_version });
    });
    return () => { alive = false; };
  }, [site?.address, projectId]);

  const hasAny = !!(site || design || cost || feas || esg);
  if (!hasAny) return null; // 분석 전 프로젝트는 표시하지 않음(아래 파이프라인이 실행 CTA 담당)

  // 핵심 요약
  const totalCost = feas?.totalCostWon ?? cost?.totalConstructionCostWon ?? null;
  const netProfit =
    feas?.totalRevenueWon != null && feas?.totalCostWon != null
      ? feas.totalRevenueWon - feas.totalCostWon
      : null;
  const violations = comp?.violations?.length ?? null;

  // 입지 인프라(안전 파싱)
  const infra = (site?.infrastructure ?? {}) as Record<string, any>;
  const subway = infra.nearest_subway as { name?: string; distance_m?: number } | undefined;
  const school = (Array.isArray(infra.schools) ? infra.schools[0] : undefined) as { name?: string; distance_m?: number } | undefined;
  const officialPrice = site?.officialPrices?.[0]?.pricePerSqm ?? null;

  return (
    <section className="rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-7 shadow-[var(--shadow-lg)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-lg">📋</span>
          <div>
            <h3 className="text-base font-bold text-[var(--text-primary)]">프로젝트 분석 요약</h3>
            <p className="text-[11px] text-[var(--text-secondary)]">저장된 분석 결과(단일 데이터원) — 모든 모듈에서 동일하게 활용됩니다.</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {integrity && (
            <span
              title={`분석 원장 해시체인 검증 — 버전 v${integrity.version}`}
              className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${
                integrity.verified
                  ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/30"
                  : "bg-rose-500/10 text-rose-500 border border-rose-500/30"
              }`}
            >
              {integrity.verified ? `🔒 원장 검증됨 · v${integrity.version}` : "⚠ 무결성 이상"}
            </span>
          )}
          {feas?.grade ? (
            <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-black text-[var(--accent-strong)]">
              수익률 {pct(feas?.profitRatePct)} ({feas.grade})
            </span>
          ) : null}
        </div>
      </div>

      {/* 핵심 요약 */}
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Tile label="수익률" value={pct(feas?.profitRatePct)} sub={feas?.grade ? `등급 ${feas.grade}` : undefined} accent />
        <Tile label="총사업비" value={eok(totalCost) ?? "—"} />
        <Tile label="순이익" value={eok(netProfit) ?? "—"} accent />
        <Tile label="탄소밀도" value={esg?.totalCarbonPerSqm != null ? `${num(esg.totalCarbonPerSqm)} kgCO₂/㎡` : "—"} />
        <Tile label="법규준수" value={violations != null ? (violations === 0 ? "적합" : `위반 ${violations}건`) : "—"} />
      </div>

      {/* 입지점수(SiteScore) + 빌더블 인벨로프(정북일조) */}
      <div className="mt-5 space-y-3">
        <SiteScoreCard />
        <BuildableEnvelopeCard />
      </div>

      {/* 섹션 카드 */}
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <Section
          title="1. 사업개요·입지"
          dataSource={site?.dataSource}
          fetchedAt={site?.fetchedAt}
          rows={[
            ["주소", site?.address ?? "—"],
            ["PNU", site?.pnu ?? "—"],
            ["용도지역", site?.zoneCode ?? "—"],
            ["대지면적", site?.landAreaSqm != null ? num(site.landAreaSqm, " ㎡") : "—"],
            ["공시지가(㎡)", officialPrice != null ? num(officialPrice, " 원") : "—"],
            ["최근접 지하철", subway?.name ? `${subway.name} (${num(subway.distance_m, "m")})` : "—"],
            ["최근접 학교", school?.name ? `${school.name} (${num(school.distance_m, "m")})` : "—"],
          ]}
        />
        <Section
          title="2. 건축계획"
          rows={[
            ["건축유형", design?.buildingType ?? "—"],
            ["연면적", design?.totalGfaSqm != null ? num(design.totalGfaSqm, " ㎡") : "—"],
            ["층수", design?.floorCount != null ? num(design.floorCount, "층") : "—"],
            ["건폐율", pct(design?.bcr)],
            ["용적률", pct(design?.far)],
            ["법정 한도(건폐/용적)", site?.ordinance ? `${pct(site.ordinance.effectiveBcr)} / ${pct(site.ordinance.effectiveFar)}` : "—"],
          ]}
        />
        <Section
          title="3. 공사비"
          dataSource={cost?.source ? `공사비 산정(${cost.source})` : undefined}
          fetchedAt={site?.fetchedAt}
          rows={[
            ["총공사비", eok(cost?.totalConstructionCostWon) ?? "—"],
            ["평당", cost?.perPyeongWon != null ? num(cost.perPyeongWon, " 원") : "—"],
            ["직접공사비", eok(cost?.directWon) ?? "—"],
            ["간접공사비", eok(cost?.indirectWon) ?? "—"],
            ["범위(최저~최대)", cost?.rangeMinWon != null && cost?.rangeMaxWon != null ? `${eok(cost.rangeMinWon)} ~ ${eok(cost.rangeMaxWon)}` : "—"],
          ]}
        />
        <Section
          title="4. 수지·사업성"
          rows={[
            ["총사업비", eok(feas?.totalCostWon) ?? "—"],
            ["분양매출", eok(feas?.totalRevenueWon) ?? "—"],
            ["순이익", eok(netProfit) ?? "—"],
            ["수익률", pct(feas?.profitRatePct)],
            ["등급", feas?.grade ?? "—"],
          ]}
        />
        <Section
          title="5. ESG·탄소"
          rows={[
            ["내재 탄소", esg?.embodiedCarbonKg != null ? `${(esg.embodiedCarbonKg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO₂e` : "분석 전"],
            ["운영 탄소(연)", esg?.operationalCarbonKg != null ? `${(esg.operationalCarbonKg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO₂e` : "분석 전"],
            ["단위면적당", esg?.totalCarbonPerSqm != null ? `${num(esg.totalCarbonPerSqm)} kgCO₂/㎡` : "분석 전"],
          ]}
        />
        <Section
          title="6. 법규 검토"
          rows={[
            ["건폐율 적합", comp?.bcrCompliant == null ? "—" : comp.bcrCompliant ? "적합" : "위반"],
            ["용적률 적합", comp?.farCompliant == null ? "—" : comp.farCompliant ? "적합" : "위반"],
            ["높이 적합", comp?.heightCompliant == null ? "—" : comp.heightCompliant ? "적합" : "위반"],
            ["위반 사항", violations != null ? (violations === 0 ? "없음" : `${violations}건`) : "—"],
          ]}
        />
      </div>
    </section>
  );
}
