"use client";

/**
 * 프로젝트 분석 요약 — 재열람용 보고서 스타일 뷰.
 * useProjectContextStore(복원·영속된 단일 데이터원)를 읽어 핵심요약 + 섹션 카드로 표시.
 * (거대 타이포·목업 상수 없이 실데이터 중심의 정보밀도·가독성 우선)
 *
 * IA 재설계(2026-06-22):
 *  · 모든 섹션 필드를 <DataField>로 교체 → 값 없는 필드는 사라진다("—"/"분석 전" 나열 제거).
 *  · 해당 단계 데이터가 하나도 없는 섹션은 <StagePreview>(무엇을 분석하는지 + 시작)로 대체.
 *  · 부지분석 완료 직후 이미 채워진 풍성 데이터(법정/실효 한도·종상향·특이부지·다필지·입지)를
 *    첫 페이지 주력으로 노출 — 첫 진입부터 "빈 필드 없이 풍성하게" 보이게 한다.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import { getCachedAnalysis, setCachedAnalysis, TTL_7D } from "@/lib/analysis-fetch-cache";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { verifyLedger } from "@/lib/analysis-ledger";
import { SiteScoreCard } from "@/components/projects/SiteScoreCard";
import { BuildableEnvelopeCard } from "@/components/projects/BuildableEnvelopeCard";
import { DataLineageTooltip } from "@/components/common/DataLineageTooltip";
import { DataField } from "@/components/projects/DataField";
import { StagePreview } from "@/components/projects/StagePreview";
import { formatAnalysisValue } from "@/lib/formatters";
import { AnalysisVerificationPanel } from "@/components/common/AnalysisVerificationPanel";

// 다필지 통합분석 응답(부분) — 요약 표시에 필요한 필드만(읽기 소비). 전부 옵셔널(부분응답 가드).
type IntegratedSummary = {
  parcel_count?: number | null;
  dominant_zone?: string | null;
  dominant_basis?: string | null;
  integrated?: {
    blended_bcr_eff_pct?: number | null;
    blended_far_eff_pct?: number | null;
    integrated_gfa_sqm?: number | null;
  } | null;
};

// 값 포맷 헬퍼 — 값이 없으면 null을 반환해 DataField가 줄 자체를 숨기도록 한다("—" 금지).
const eok = (won: number | null | undefined): string | null =>
  won != null ? `${(won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억` : null;
const num = (v: number | null | undefined, unit = ""): string => formatAnalysisValue(v, unit);
const numOrNull = (v: number | null | undefined, unit = ""): string | null =>
  v != null && Number.isFinite(v) ? formatAnalysisValue(v, unit) : null;
const pctOrNull = (v: number | null | undefined): string | null =>
  v != null && Number.isFinite(v) ? `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}%` : null;
const tCO2e = (kg: number | null | undefined): string | null =>
  kg != null && Number.isFinite(kg)
    ? `${(kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO₂e`
    : null;
// 건폐/용적 쌍 합성 — 둘 다 있으면 "건폐 X / 용적 Y", 한쪽만 있으면 그 한쪽만, 둘 다 없으면 null.
//   (이전 `${pctOrNull(b) ?? '—'} / ...` 방식은 한쪽만 있을 때 '60% / —' 빈 자리표시가 누출됐다.)
const bcrFarOrNull = (b: number | null | undefined, f: number | null | undefined): string | null => {
  const bs = pctOrNull(b);
  const fs = pctOrNull(f);
  if (bs && fs) return `건폐 ${bs} / 용적 ${fs}`;
  if (bs) return `건폐 ${bs}`;
  if (fs) return `용적 ${fs}`;
  return null;
};

function Tile({ label, value, sub, accent, tip }: { label: string; value: string; sub?: string; accent?: boolean; tip?: string }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]" title={tip}>{label}</p>
      <p className={`mt-1.5 text-xl font-[1000] tracking-tight ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}

/** DataField 행 묶음을 담는 섹션 카드.
 *  hasAny=false면 제목·껍데기까지 통째로 숨긴다(빈 카드 '1. 사업개요·입지' 노출 방지).
 *  (React.Children.count는 null 자식을 세지 못해 빈 셸을 못 막으므로, 호출부에서 OR 게이트를 계산해 넘긴다.) */
function Section({
  title,
  dataSource,
  fetchedAt,
  hasAny,
  detailLink,
  children,
}: {
  title: string;
  dataSource?: string | null;
  fetchedAt?: string | null;
  /** 이 섹션에 표시할 값이 하나라도 있는지(false면 섹션 전체 미렌더). */
  hasAny?: boolean;
  /** 풀버전(상세·수정) 페이지로 가는 링크(선택). href·label 둘 다 있을 때만 노출. */
  detailLink?: { href: string; label: string } | null;
  children: React.ReactNode;
}) {
  if (hasAny === false) return null;
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <h4 className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
        {title}
        <DataLineageTooltip dataSource={dataSource} fetchedAt={fetchedAt} />
        {detailLink && (
          // 풀버전(상세·수정) 진입 — 요약↔풀버전 라우팅 연결. Link라 데이터 fetch 없음(#185 무관).
          <Link
            href={detailLink.href}
            className="ml-auto inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-2.5 py-0.5 text-[10px] font-black text-[var(--accent-strong)] transition-all hover:scale-105"
          >
            {detailLink.label} ↗
          </Link>
        )}
      </h4>
      <dl className="mt-3 divide-y divide-[var(--line)]">{children}</dl>
    </div>
  );
}

export function ProjectAnalysisSummary({ locale }: { locale?: string }) {
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const design = useProjectContextStore((s) => s.designData);
  const cost = useProjectContextStore((s) => s.costData);
  const feas = useProjectContextStore((s) => s.feasibilityData);
  const esg = useProjectContextStore((s) => s.esgData);
  const comp = useProjectContextStore((s) => s.complianceData);
  const projectId = useProjectContextStore((s) => s.projectId);

  // StagePreview 진입 경로 빌더 — locale·projectId 둘 다 있을 때만 라우팅(없으면 미리보기 숨김).
  const routeTo = (seg: string): string | null =>
    locale && projectId ? `/${locale}/projects/${projectId}/${seg}` : null;

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

  // ── 다필지 통합분석 읽기 소비(로컬 state·SSOT 미기록) — parcelCount>1 && 필지목록>1일 때만 ──
  //   요약의 '통합 N필지' 라벨 옆에 dominant_zone/blended/통합GFA를 보강 표시. 없으면 단일 degrade.
  const ssotParcels = site?.parcels ?? null;
  const isMultiParcelSite = (site?.parcelCount ?? 1) > 1 && (ssotParcels?.length ?? 0) > 1;
  const parcelsSig = useMemo(() => {
    if (!isMultiParcelSite || !ssotParcels) return "";
    return ssotParcels.map((p) => `${p.pnu}:${p.areaSqm ?? ""}`).sort().join("|");
  }, [isMultiParcelSite, ssotParcels]);
  const [integrated, setIntegrated] = useState<IntegratedSummary | null>(null);
  useEffect(() => {
    if (!isMultiParcelSite || !ssotParcels || ssotParcels.length < 2) { setIntegrated(null); return; }
    const iKey = `integrated:${ssotParcels.length}:${parcelsSig}`;
    const cached = getCachedAnalysis<IntegratedSummary>(iKey, TTL_7D);
    if (cached) { setIntegrated(cached); return; }
    let alive = true;
    const triggeredProjectId = useProjectContextStore.getState().projectId;
    void apiClient.post<IntegratedSummary>("/zoning/integrated-analysis", {
      useMock: false,
      body: {
        parcels: ssotParcels.map((p) => ({ pnu: p.pnu, address: p.address, area_sqm: p.areaSqm, land_category: p.landCategory })),
        use_llm: false,
      },
    }).then((res) => {
      if (!alive) return;
      if (useProjectContextStore.getState().projectId !== triggeredProjectId) return;
      setIntegrated(res);
      setCachedAnalysis(iKey, res);
    }).catch(() => { /* 무목업: 실패 시 통합 보강 미표시(단일 degrade) */ });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMultiParcelSite, parcelsSig]);

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

  // 다필지 통합 면적 정직표기 — parcelCount>1이면 "통합 N필지" 라벨 + 대표면적 보조표기.
  //   단일필지(parcelCount 미설정/1)는 종전과 동일하게 단일 면적만 표시(무회귀).
  const isMultiParcel = (site?.parcelCount ?? 1) > 1;
  const landAreaLabel = isMultiParcel ? `대지면적 (통합 ${site?.parcelCount}필지)` : "대지면적";
  // ★표시 면적은 effectiveLandAreaSqm(다필지=통합 우선)로 안정화 — 단일 PNU 분석이
  //   landAreaSqm을 대표값으로 덮어써도 통합 면적이 보존된다. "대표 Y"는 repLandAreaSqm 그대로.
  const effArea = effectiveLandAreaSqm(site);
  const landAreaValue =
    effArea != null
      ? isMultiParcel && site?.repLandAreaSqm != null
        ? `${num(effArea, " ㎡")} (대표 ${num(site.repLandAreaSqm, " ㎡")})`
        : num(effArea, " ㎡")
      : null;

  // 용도지역 표시값 — 통합 확보 시 dominant_zone(혼재 표기) 우선, 아니면 단일 degrade.
  const zoneRowValue = integrated?.dominant_zone
    ? (integrated.dominant_basis === "mixed_review_required" || site?.zoneMixed
        ? `${integrated.dominant_zone} 외 (혼재·분리검토)`
        : integrated.dominant_zone)
    : site?.zoneCode
      ? (site?.zoneMixed ? `${site.zoneCode} 외 (혼합지)` : site.zoneCode)
      : null;

  // ── 부지분석 풍성 데이터(SSOT rich 필드) — 첫 페이지 주력 노출 ──
  // 법정 상한(국가법 최대치)·실효 한도(조례 반영)·종상향 잠재 상한·최상 가능성 등급.
  const ord = site?.ordinance ?? null;
  // 실효 건폐/용적: rich 필드(effective*Pct) 우선, 없으면 ordinance.effective* 폴백.
  const effBcr = site?.effectiveBcrPct ?? ord?.effectiveBcr ?? null;
  const effFar = site?.effectiveFarPct ?? ord?.effectiveFar ?? null;
  const natBcr = site?.nationalBcrPct ?? ord?.nationalBcr ?? null;
  const natFar = site?.nationalFarPct ?? ord?.nationalFar ?? null;
  // 실효 한도가 아직 잠정 법정상한 시드인지(라벨·근거 정직표기용).
  const effIsSeed = ord?.seededFromLegal === true;
  const effLimitLabel = effIsSeed
    ? "실제 적용 한도(잠정·국가법 상한)"
    : ord?.ordinanceFar != null || ord?.ordinanceBcr != null
      ? "실제 적용 한도(실효·조례반영)"
      : "실제 적용 한도(실효)";
  const effLimitEvidence = effIsSeed
    ? "조례·도시계획 확정값 승격 전 잠정 적용 — 국가 법정상한을 시드로 사용"
    : site?.farBasis || ord?.legalBasis || null;

  // 종상향 잠재(현행과 분리해 표기) — 잠재 상한 + 최상 가능성 등급(있을 때만).
  const upFarHigh = site?.upzoningPotentialFarHigh ?? null;
  const upFeasTop = site?.upzoningFeasibilityTop ?? null;

  // 특이부지(학교용지·GB·맹지 등) — 있을 때만 정직고지 섹션 노출.
  const sp = site?.specialParcel ?? null;
  const showSpecial = !!(sp && sp.isSpecial);
  const developabilityLabel: Record<string, string> = {
    POSSIBLE: "개발 가능",
    CONDITIONAL: "조건부 가능",
    PRECONDITION: "선결조건 필요",
    RESTRICTED: "제한적",
    BLOCKED: "개발 불가",
  };
  const resolvableLabel: Record<string, string> = {
    YES: "해결 가능",
    CONDITIONAL: "조건부 해결",
    NO: "해결 어려움",
  };

  // 통합 실효 건폐/용적·통합 GFA(다필지 통합 확보 시에만 노출).
  const integratedBcrFar = integrated?.integrated
    ? bcrFarOrNull(integrated.integrated.blended_bcr_eff_pct, integrated.integrated.blended_far_eff_pct)
    : null;
  const integratedGfa = integrated?.integrated?.integrated_gfa_sqm != null
    ? numOrNull(Math.round(integrated.integrated.integrated_gfa_sqm), " ㎡")
    : null;

  // ── 섹션별 데이터 유무 게이트(없으면 StagePreview로 대체) ──
  // 1·2 섹션(부지분석 rich): 표시할 값이 하나라도 있을 때만 카드를 그린다(빈 셸 차단).
  const hasSiteFields = !!(
    site?.address || site?.pnu || zoneRowValue || landAreaValue ||
    integratedBcrFar || integratedGfa || numOrNull(officialPrice, " 원") ||
    subway?.name || school?.name
  );
  const hasZoningFields = !!(
    bcrFarOrNull(natBcr, natFar) || bcrFarOrNull(effBcr, effFar) ||
    pctOrNull(upFarHigh) || upFeasTop || ord?.source
  );
  const hasCost = !!(cost && (cost.totalConstructionCostWon != null || cost.perPyeongWon != null || cost.directWon != null));
  const hasFeas = !!(feas && (feas.totalCostWon != null || feas.totalRevenueWon != null || feas.profitRatePct != null));
  const hasEsg = !!(esg && (esg.embodiedCarbonKg != null || esg.operationalCarbonKg != null || esg.totalCarbonPerSqm != null));
  const hasComp = !!(comp && (comp.bcrCompliant != null || comp.farCompliant != null || comp.heightCompliant != null || (comp.violations?.length ?? 0) > 0));
  const hasDesign = !!(design && (design.totalGfaSqm != null || design.floorCount != null || design.buildingType != null || design.bcr != null || design.far != null));

  const costRoute = routeTo("cost");
  const designRoute = routeTo("design");
  const feasRoute = routeTo("feasibility");
  const esgRoute = routeTo("esg");
  const legalRoute = routeTo("legal");

  // ── 섹션 동적 번호 ── 조건부로 일부 섹션이 빠져도 번호가 비지 않도록(예: 1·3·4) 연속 부여.
  //   부지분석 rich 섹션(사업개요·입지 / 용도지역·규제 / 특이부지 / 다필지)만 번호를 매긴다.
  //   (이후 건축계획·공사비·수지·ESG·법규는 단계 명칭만 — 미완 단계 StagePreview와 번호 충돌 회피)
  let _sectionNo = 0;
  const nextNo = () => (++_sectionNo);

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
            <span
              title="투자 수익률과 사업성 등급(투입 대비 남는 비율)"
              className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-black text-[var(--accent-strong)]"
            >
              {/* ROI가 있으면 '투자 수익률 X (등급 Y)', 없으면 '사업성 등급 Y'만 — '—' 자리표시 제거. */}
              {pctOrNull(feas?.profitRatePct)
                ? `투자 수익률 ${pctOrNull(feas.profitRatePct)} (사업성 등급 ${feas.grade})`
                : `사업성 등급 ${feas.grade}`}
            </span>
          ) : null}
        </div>
      </div>

      {/* 핵심 요약 — 산출된 지표만 타일로(미산출 지표는 숨김). 핵심요약에 보일 게 없으면 영역 자체 생략. */}
      {(() => {
        const tiles: React.ReactNode[] = [];
        if (feas?.profitRatePct != null)
          tiles.push(<Tile key="roi" label="투자 수익률" tip="투입 대비 몇 % 남는지" value={pctOrNull(feas.profitRatePct)!} sub={feas?.grade ? `사업성 등급 ${feas.grade}` : undefined} accent />);
        if (totalCost != null)
          tiles.push(<Tile key="cost" label="총사업비" value={eok(totalCost)!} />);
        if (netProfit != null)
          tiles.push(<Tile key="profit" label="순이익" value={eok(netProfit)!} accent />);
        if (esg?.totalCarbonPerSqm != null)
          tiles.push(<Tile key="carbon" label="면적당 탄소배출(친환경 정도)" tip="단위면적당 탄소배출량 — 낮을수록 친환경" value={`${num(esg.totalCarbonPerSqm)} kgCO₂/㎡`} />);
        if (violations != null)
          tiles.push(<Tile key="legal" label="법규준수" value={violations === 0 ? "적합" : `위반 ${violations}건`} />);
        if (tiles.length === 0) return null;
        return <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">{tiles}</div>;
      })()}

      {/* 입지점수(SiteScore) + 빌더블 인벨로프(정북일조) */}
      <div className="mt-5 space-y-3">
        <SiteScoreCard />
        <BuildableEnvelopeCard />
      </div>

      {/* 섹션 카드 */}
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {/* 사업개요·입지 — 부지분석 완료 직후 항상 풍성하게 채워지는 주력 섹션(값 없으면 카드 자체 미렌더).
            번호는 실제 렌더되는 섹션에만 부여(빈 셸 미렌더 시 nextNo도 미호출 → 번호 공백 방지). */}
        {hasSiteFields && (
        <Section title={`${nextNo()}. 사업개요·입지`} dataSource={site?.dataSource} fetchedAt={site?.fetchedAt}>
          <DataField label="주소" value={site?.address} />
          <DataField label="PNU" value={site?.pnu} />
          <DataField label="용도지역" value={zoneRowValue} />
          <DataField label={landAreaLabel} value={landAreaValue} />
          <DataField label="통합 건폐/용적(실효)" value={integratedBcrFar} />
          <DataField label="통합 GFA(연면적)" value={integratedGfa} />
          <DataField label="공시지가(㎡)" value={numOrNull(officialPrice, " 원")} />
          {/* 거리(distance_m)가 없으면 괄호 자체를 생략 — '홍대입구역 (분석 전)' 누출 방지(numOrNull 사용). */}
          <DataField
            label="최근접 지하철"
            value={subway?.name ? (() => { const d = numOrNull(subway.distance_m, "m"); return d ? `${subway.name} (${d})` : subway.name; })() : null}
          />
          <DataField
            label="최근접 학교"
            value={school?.name ? (() => { const d = numOrNull(school.distance_m, "m"); return d ? `${school.name} (${d})` : school.name; })() : null}
          />
        </Section>
        )}

        {/* 용도지역·규제 — 법정상한·실효한도·종상향 잠재(부지분석 rich 산출, 값 없으면 카드 미렌더) */}
        {hasZoningFields && (
        <Section title={`${nextNo()}. 용도지역·규제`} dataSource={site?.dataSource} fetchedAt={site?.fetchedAt}>
          <DataField
            label="국가법 최대치(법정상한·건폐/용적)"
            value={bcrFarOrNull(natBcr, natFar)}
            evidence="국토계획법상 용도지역별 법정 상한(조례·계획 적용 전)"
          />
          <DataField
            label={`${effLimitLabel}(건폐/용적)`}
            value={bcrFarOrNull(effBcr, effFar)}
            evidence={effLimitEvidence}
            accent
          />
          <DataField
            label="종상향 잠재 상한(용적)"
            value={pctOrNull(upFarHigh)}
            evidence="지구단위·역세권 등 종상향 시 도달 가능한 잠재 용적률 상단 — 현행과 분리 표기"
          />
          <DataField
            label="종상향 최상 가능성"
            value={upFeasTop ? `${upFeasTop} 등급` : null}
            evidence="종상향 시나리오 중 가장 실현 가능성이 높은 등급(상/중/하)"
          />
          <DataField label="조례 출처" value={ord?.source} />
        </Section>
        )}

        {/* 특이부지(학교용지·GB·맹지 등) — isSpecial일 때만 정직고지 */}
        {showSpecial && sp && (
          <Section title={`${nextNo()}. 특이부지 검토(정직고지)`} dataSource={site?.dataSource} fetchedAt={site?.fetchedAt}>
            <DataField
              label="개발 가능성"
              value={sp.developability ? (developabilityLabel[sp.developability] ?? sp.developability) : null}
              accent
            />
            <DataField
              label="해결 가능성"
              value={sp.resolvable ? (resolvableLabel[sp.resolvable] ?? sp.resolvable) : null}
            />
            <DataField
              label="특이 요인"
              value={sp.factors?.length ? sp.factors.join(" · ") : null}
            />
            <DataField label="정직고지" value={sp.honest} />
          </Section>
        )}

        {/* 다필지 통합 — parcelCount>1일 때만 */}
        {isMultiParcel && (
          <Section title={`${nextNo()}. 다필지 통합`} dataSource={site?.dataSource} fetchedAt={site?.fetchedAt}>
            <DataField label="필지 수" value={site?.parcelCount != null ? `${site.parcelCount}필지` : null} />
            <DataField label="통합 대지면적" value={numOrNull(effArea, " ㎡")} />
            <DataField label="대표 필지 면적" value={numOrNull(site?.repLandAreaSqm, " ㎡")} />
            {/* zoneMixed가 undefined(미상)면 '동일 용도'로 오확정하지 않고 행 자체를 숨긴다. */}
            <DataField
              label="용도 혼재"
              value={site?.zoneMixed != null ? (site.zoneMixed ? "혼합지(분리검토 필요)" : "동일 용도") : null}
            />
          </Section>
        )}

        {/* 5. 건축계획 — 설계 데이터 있으면 DataField, 없으면 StagePreview */}
        {hasDesign ? (
          <Section title="건축계획">
            <DataField label="건축유형" value={design?.buildingType} />
            <DataField label="연면적" value={numOrNull(design?.totalGfaSqm, " ㎡")} />
            <DataField label="층수" value={numOrNull(design?.floorCount, "층")} />
            <DataField label="건폐율" value={pctOrNull(design?.bcr)} />
            <DataField label="용적률" value={pctOrNull(design?.far)} />
            {/* 평형 구성(unitTypes) — StagePreview 약속 항목과 산출을 정합(있을 때만 표시). */}
            <DataField label="평형 구성" value={design?.unitTypes?.length ? design.unitTypes.join(" · ") : null} />
          </Section>
        ) : designRoute ? (
          <StagePreview
            title="설계 분석"
            items={["건축유형", "연면적(GFA)", "층수", "건폐율/용적률", "평형 구성"]}
            inputHint="부지분석 용도지역·실효 건폐/용적·면적 활용"
            route={designRoute}
          />
        ) : null}

        {/* 6. 공사비 — 있으면 DataField, 없으면 StagePreview */}
        {hasCost ? (
          <Section
            title="공사비"
            dataSource={cost?.source ? `공사비 산정(${cost.source})` : undefined}
            fetchedAt={site?.fetchedAt}
            // 풀버전: BIM 5D 적산(QTO) 대시보드(/cost) — 부위별 물량·상세내역 조회·수정.
            detailLink={costRoute ? { href: costRoute, label: "BIM 적산 상세·수정" } : null}
          >
            <DataField label="총공사비" value={eok(cost?.totalConstructionCostWon)} />
            <DataField label="평당" value={numOrNull(cost?.perPyeongWon, " 원")} />
            <DataField label="직접공사비" value={eok(cost?.directWon)} />
            <DataField label="간접공사비" value={eok(cost?.indirectWon)} />
            <DataField label="범위(최저~최대)" value={cost?.rangeMinWon != null && cost?.rangeMaxWon != null ? `${eok(cost.rangeMinWon)} ~ ${eok(cost.rangeMaxWon)}` : null} />
          </Section>
        ) : costRoute ? (
          <StagePreview
            title="공사비 분석"
            items={["총공사비", "평당단가", "직접/간접공사비", "범위(최저~최대)"]}
            inputHint="설계 연면적·건축유형 활용"
            route={costRoute}
          />
        ) : null}

        {/* 7. 수지·사업성 — 있으면 DataField, 없으면 StagePreview */}
        {hasFeas ? (
          <Section
            title="수지·사업성"
            // 풀버전: 사업성 분석 에디터(/feasibility) — /api/v2/feasibility/calculate 기반 현장부합 조회·수정.
            detailLink={feasRoute ? { href: feasRoute, label: "수지분석 상세·수정" } : null}
          >
            <DataField label="총사업비" value={eok(feas?.totalCostWon)} />
            <DataField label="분양매출" value={eok(feas?.totalRevenueWon)} />
            <DataField label="순이익" value={eok(netProfit)} accent />
            <DataField label="투자 수익률" value={pctOrNull(feas?.profitRatePct)} accent />
            <DataField label="사업성 등급" value={feas?.grade} />
          </Section>
        ) : feasRoute ? (
          <StagePreview
            title="수지·사업성 분석"
            items={["총사업비", "분양매출", "순이익", "투자 수익률(ROI)", "사업성 등급"]}
            inputHint="공사비·적정분양가·면적 활용"
            route={feasRoute}
          />
        ) : null}

        {/* 8. ESG·탄소 — 있으면 DataField, 없으면 StagePreview */}
        {hasEsg ? (
          <Section title="ESG·탄소">
            <DataField label="내재 탄소" value={tCO2e(esg?.embodiedCarbonKg)} />
            <DataField label="운영 탄소(연)" value={tCO2e(esg?.operationalCarbonKg)} />
            <DataField label="면적당 탄소배출(친환경 정도)" value={numOrNull(esg?.totalCarbonPerSqm, " kgCO₂/㎡")} />
          </Section>
        ) : esgRoute ? (
          <StagePreview
            title="ESG·탄소 분석"
            items={["내재 탄소", "운영 탄소(연)", "면적당 탄소배출"]}
            inputHint="설계 연면적·건축유형 활용"
            route={esgRoute}
          />
        ) : null}

        {/* 9. 법규 검토 — 있으면 DataField, 없으면 StagePreview */}
        {hasComp ? (
          <Section title="법규 검토">
            <DataField label="건폐율 적합" value={comp?.bcrCompliant == null ? null : comp.bcrCompliant ? "적합" : "위반"} />
            <DataField label="용적률 적합" value={comp?.farCompliant == null ? null : comp.farCompliant ? "적합" : "위반"} />
            <DataField label="높이 적합" value={comp?.heightCompliant == null ? null : comp.heightCompliant ? "적합" : "위반"} />
            <DataField label="위반 사항" value={violations != null ? (violations === 0 ? "없음" : `${violations}건`) : null} />
          </Section>
        ) : legalRoute ? (
          <StagePreview
            title="법규 검토"
            items={["건폐율 적합", "용적률 적합", "높이 적합", "위반 사항"]}
            inputHint="설계 건폐/용적·부지 실효 한도 비교"
            route={legalRoute}
          />
        ) : null}
      </div>

      {/* 검증 4계층 — 사업수지 기준(feasibility 노드, expertPanel=true).
          showTrustBadge는 원장 검증 완료(integrity.verified=true) 일 때만 활성화.
          context는 핵심 사업성 지표(JSON 직렬화 가능)만 전달 — 실데이터 있을 때만 렌더. */}
      {feas && (
        <div className="mt-5">
          <AnalysisVerificationPanel
            nodeId="feasibility"
            analysisType="feasibility"
            address={site?.address ?? undefined}
            context={{
              profitRatePct: feas.profitRatePct,
              totalCostWon: feas.totalCostWon,
              totalRevenueWon: feas.totalRevenueWon,
              grade: feas.grade,
            }}
            // 근거 계층(EvidencePanel)+데이터 출처 칩 활성화 — 사업성 핵심수치의 산식 근거를
            // 함께 노출해 비전문가도 "이 값이 왜 이렇게 나왔나"를 검증할 수 있게 한다(근거 기본제공).
            evidenceItems={(() => {
              // 값이 있는 근거 항목만 담는다('—' 자리표시 금지 — DataField와 동일 원칙).
              const ev: { label: string; value: string; basis: string }[] = [];
              const roi = pctOrNull(feas.profitRatePct);
              if (roi)
                ev.push({ label: "투자 수익률(ROI)", value: roi,
                  basis: `순이익 ÷ 총사업비 × 100${feas.grade ? ` · 사업성 등급 ${feas.grade}` : ""}` });
              const net = feas.totalRevenueWon != null && feas.totalCostWon != null
                ? eok(feas.totalRevenueWon - feas.totalCostWon) : null;
              if (net)
                ev.push({ label: "예상 순이익", value: net, basis: "총매출 − 총사업비" });
              const totalCost = eok(feas.totalCostWon);
              if (totalCost)
                ev.push({ label: "총사업비", value: totalCost, basis: "토지비 + 공사비 + 금융비 + 세금" });
              const totalRev = eok(feas.totalRevenueWon);
              if (totalRev)
                ev.push({ label: "총매출(분양)", value: totalRev, basis: "분양가 × 분양면적" });
              return ev;
            })()}
            showTrustBadge={integrity?.verified === true}
          />
        </div>
      )}
    </section>
  );
}
