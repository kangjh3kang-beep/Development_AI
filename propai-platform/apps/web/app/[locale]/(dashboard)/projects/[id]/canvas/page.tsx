"use client";

/**
 * SiteCanvas — 지도 중심 단일창 분석(요약 허브 + 드릴다운). 추가 라우트(기존 페이지 무손상).
 *
 * 좌: 맥락형 요약 탭(토지/규제/개발방식/일조·배치/구획도) — 각 탭은 핵심 요약 + "상세 →"로
 *     해당 전용 페이지(site-analysis·legal·permit·design 등)에 연결(사용자 정련: 지도=요약, 상세=패널 메뉴).
 * 우: 자급식 구획도 지도(ParcelBoundaryMap, parcels=주소배열 → 내부에서 경계 fetch).
 * SSOT(useProjectContextStore) 단일 소비 — 선택 필지 변경 시 카드·지도 자동 갱신(기존 메커니즘).
 */

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Map as MapIcon, Layers, Sun, Construction, Ruler, Download, ArrowRight, MousePointerClick, ChevronDown, Coins, FileText, Users } from "lucide-react";
import { dynamicMap } from "@/components/common/MapShell";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveFarPct, resolveBcrPct, resolveDominantZone } from "@/lib/zoning-ssot";
import { AutoZoningBadge } from "@/components/projects/AutoZoningBadge";
import { BuildableEnvelopeCard } from "@/components/projects/BuildableEnvelopeCard";
import { SolarPlacementCard } from "@/components/projects/SolarPlacementCard";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { ParcelExportButton } from "@/components/projects/ParcelExportButton";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { PermitGuideCard } from "@/components/projects/PermitGuideCard";
import { AiInsightCard } from "@/components/projects/AiInsightCard";
import { AiInsightStrip } from "@/components/projects/AiInsightStrip";
import { DecisionBriefPanel } from "@/components/projects/DecisionBriefPanel";
import { SeniorConsultPanel } from "@/components/orchestration/SeniorConsultPanel";
import { BuildableMassPreview } from "@/components/projects/BuildableMassPreview";
import { RegulationDigestCard } from "@/components/projects/RegulationDigestCard";
import { LegalDiscoveryCard } from "@/components/projects/LegalDiscoveryCard";
import { SiteInfraPoiCard } from "@/components/site/SiteInfraPoiCard";
import { BuildCostCard } from "@/components/projects/BuildCostCard";
import { VerificationBadge } from "@/components/common/VerificationBadge";

import type { NearbyTransactionsMap as NearbyTransactionsMapType } from "@/components/map/NearbyTransactionsMap";

const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 520, loadingMessage: "구획도 로딩…" },
);
const NearbyTransactionsMap = dynamicMap<React.ComponentProps<typeof NearbyTransactionsMapType>>(
  () => import("@/components/map/NearbyTransactionsMap"),
  { pick: "NearbyTransactionsMap", height: 520, loadingMessage: "주변 실거래 지도 로딩…" },
);

type TabKey = "land" | "regulation" | "infra" | "development" | "solar" | "feasibility" | "senior" | "summary" | "boundary";

const eok = (won: number | null | undefined): string =>
  won == null ? "—" : `${(won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`;

/** 전용 페이지 드릴다운 CTA(요약→상세). ★모듈 레벨 — 렌더 내 컴포넌트 생성 금지(react-hooks/static-components). */
function DrillCta({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link href={to}
      className="mt-2 inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition hover:border-[var(--accent-strong)]">
      {children} <ArrowRight className="size-3" aria-hidden />
    </Link>
  );
}

export default function SiteCanvasPage() {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const id = params?.id as string;
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const feas = useProjectContextStore((s) => s.feasibilityData);
  const [tab, setTab] = useState<TabKey>("land");
  // 필지 선택/변경 패널(지도 클릭선택+검색+엑셀) — 부지 미확정 시 기본 펼침, 확정 후 접힘.
  const [pickerOpen, setPickerOpen] = useState(false);
  // 우측 지도 모드 — 구획도(필지경계·용도지역) ↔ 실거래(주변 가격 마커, jootek/Naver式).
  const [mapMode, setMapMode] = useState<"boundary" | "transactions">("boundary");

  const ssotParcels = site?.parcels ?? null;
  const effArea = effectiveLandAreaSqm(site);
  // 자급식 지도 입력: 다필지 주소 배열(없으면 대표 주소).
  const mapAddresses = useMemo(() => {
    const list = (ssotParcels ?? [])
      .map((p) => p.address)
      .filter((a): a is string => !!a && a.trim().length > 0);
    if (list.length > 0) return list;
    return site?.address ? [site.address] : [];
  }, [ssotParcels, site?.address]);

  const proj = (p: string) => `/${locale}/projects/${id}/${p}`;
  // 전역 자산·권리 관리 페이지(프로젝트 무관·SSOT 필지 공유). Tier2 별도 관리 페이지 연동.
  const glob = (p: string) => `/${locale}/${p}`;

  const TABS: { key: TabKey; label: string; icon: typeof Layers }[] = [
    { key: "land", label: "토지", icon: Layers },
    { key: "regulation", label: "규제", icon: Ruler },
    { key: "infra", label: "입지", icon: MapIcon },
    { key: "development", label: "개발방식", icon: Construction },
    { key: "solar", label: "일조·배치", icon: Sun },
    { key: "feasibility", label: "수지", icon: Coins },
    { key: "senior", label: "시니어자문", icon: Users },
    { key: "summary", label: "통합", icon: FileText },
    { key: "boundary", label: "구획도", icon: Download },
  ];

  // 부지 미확정 — SiteCanvas에서 바로 필지를 검색/지도클릭/엑셀로 선택(SSOT 기록 → 아래 분석 자동 채움).
  if (!site?.address && !site?.pnu && mapAddresses.length === 0) {
    return (
      <div className="mx-auto max-w-2xl py-10">
        <div className="mb-4 text-center">
          <p className="inline-flex items-center gap-1.5 text-lg font-black text-[var(--text-primary)]">
            <MapIcon className="size-5 text-[var(--accent-strong)]" aria-hidden /> 지도 단일창 — 부지 선택
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            주소 검색·지도 클릭·엑셀로 필지를 선택하면 한 화면에서 분석이 채워집니다(다필지 통합 지원).
          </p>
        </div>
        <GlobalAddressSearch placeholder="주소·지번을 검색하거나 지도에서 필지를 클릭하세요" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {/* 상단: 주소 + 구획도 다운로드 */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <MapIcon className="size-4 text-[var(--accent-strong)]" aria-hidden />
          {site?.address || "부지 분석"}
          {(ssotParcels?.length ?? 0) > 1 && (
            <span className="rounded-md bg-[var(--accent-strong)]/10 px-1.5 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
              통합 {ssotParcels!.length}필지{effArea ? ` · ${Math.round(effArea).toLocaleString()}㎡` : ""}
            </span>
          )}
        </p>
        <div className="flex items-center gap-2">
          <button onClick={() => setPickerOpen((v) => !v)}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-bold transition ${
              pickerOpen ? "border-[var(--accent-strong)] text-[var(--accent-strong)]"
                : "border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"}`}>
            <MousePointerClick className="size-3.5" aria-hidden /> 필지 선택/변경
            <ChevronDown className={`size-3 transition ${pickerOpen ? "rotate-180" : ""}`} aria-hidden />
          </button>
          <ParcelExportButton
            parcels={ssotParcels?.map((p) => ({ pnu: p.pnu, address: p.address }))}
            address={site?.address}
            pnu={site?.pnu}
          />
        </div>
      </div>

      {/* 필지 선택/변경(지도 클릭선택+검색+엑셀, SSOT 기록 → 카드·지도 자동 갱신) */}
      {pickerOpen && (
        <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface-soft)] p-3">
          <GlobalAddressSearch
            initialAddress={site?.address || undefined}
            placeholder="주소·지번 검색 또는 지도에서 필지 클릭(다필지 통합)"
          />
        </div>
      )}

      {/* ★상단 히어로 — AI 종합판정(Go/CONDITIONAL/HOLD). 자급식(SSOT 주소 자동실행)·단일창 최상위 결론.
          jootek 미보유 차별자(부지+법규+인허가+설계Top3 통합 판정)를 첫 화면에 전면 배치(P0②). */}
      <DecisionBriefPanel projectId={id} />

      {/* 2분할: 좌 요약 탭 rail + 우 지도 */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[400px_1fr]">
        {/* 좌: 맥락형 요약 탭 */}
        <div className="flex flex-col rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <div className="flex flex-wrap gap-1 border-b border-[var(--line)] pb-2">
            {TABS.map((t) => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-bold transition ${
                  tab === t.key ? "bg-[var(--accent-strong)] text-white"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
                <t.icon className="size-3.5" aria-hidden /> {t.label}
              </button>
            ))}
          </div>

          {/* 각 탭 상단 경량 AI 인사이트(통합 탭 풀카드와 동일 캐시 — 'LLM 미적용' 갭 해소). 통합/구획도 탭 제외. */}
          {site?.address && tab !== "summary" && tab !== "boundary" ? (
            <div className="mt-3"><AiInsightStrip address={site.address} /></div>
          ) : null}

          <div className="mt-3 max-h-[60vh] space-y-3 overflow-y-auto pr-1">
            {tab === "land" && (
              <>
                {site?.address ? <AutoZoningBadge address={site.address} /> : null}
                <DrillCta to={proj("site-analysis")}>토지·실거래·적정매입가 상세</DrillCta>
                {/* ★자산·권리 관리(Tier2 별도 관리 페이지·SSOT 필지 공유) — 토지조서·등기/권리분석·시세추정 */}
                <div className="flex flex-wrap gap-1.5">
                  <DrillCta to={glob("land-schedule")}>토지조서 관리</DrillCta>
                  <DrillCta to={glob("registry-analysis")}>등기부·권리분석</DrillCta>
                  <DrillCta to={glob("desk-appraisal")}>AI 시세추정</DrillCta>
                </div>
              </>
            )}
            {tab === "regulation" && (
              <>
                {resolveDominantZone(site) && (resolveFarPct(site) != null || resolveBcrPct(site) != null) && (
                  <VerificationBadge analysisType="site" context={{
                    zone_type: resolveDominantZone(site)!,
                    effective_far: resolveFarPct(site) ?? null,
                    effective_bcr: resolveBcrPct(site) ?? null,
                    land_area_sqm: effArea,
                  }} />
                )}
                <BuildableEnvelopeCard compact />
                <RegulationDigestCard address={site?.address} />
                <LegalDiscoveryCard address={site?.address} />
                <PermitGuideCard />
                <DrillCta to={proj("legal")}>규제 계층·인허가 상세</DrillCta>
              </>
            )}
            {tab === "infra" && (
              <>
                {site?.address ? <SiteInfraPoiCard address={site.address} /> : (
                  <p className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 text-xs text-[var(--text-secondary)]">주소를 선택하면 입지점수·주변 인프라(POI)를 조회합니다.</p>
                )}
                <DrillCta to={proj("site-analysis")}>입지·상권 상세</DrillCta>
              </>
            )}
            {tab === "development" && (
              <>
                <DevelopmentScenarioCard
                  address={site?.address ?? undefined}
                  parcels={(ssotParcels ?? []).map((p) => p.address).filter((a): a is string => !!a && a.trim().length > 0)}
                />
                <DrillCta to={proj("permit")}>인허가 진단·로드맵 상세</DrillCta>
              </>
            )}
            {tab === "solar" && (
              <>
                <SolarPlacementCard address={site?.address} pnu={site?.pnu} zone={site?.zoneCode} landAreaSqm={effArea} compact />
                {/* ★P3.5② 법정 최대 매스 3D 미리보기(SSOT far/bcr/면적 파생·보기 게이트·근사 정직). 정밀은 설계 스튜디오. */}
                <BuildableMassPreview farPct={resolveFarPct(site)} bcrPct={resolveBcrPct(site)} areaSqm={effArea} />
                <DrillCta to={proj("design")}>설계 스튜디오·CAD/BIM 상세</DrillCta>
              </>
            )}
            {tab === "feasibility" && (
              <>
                {feas && (feas.totalCostWon != null || feas.totalRevenueWon != null || feas.roiPct != null) ? (
                  <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
                    <p className="text-xs font-black text-[var(--text-primary)]">사업 수지 요약 {feas.grade ? `· ${feas.grade}` : ""}</p>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-center text-[11px]">
                      <div><p className="text-[var(--text-hint)]">총 사업비</p><p className="font-bold text-[var(--text-primary)]">{eok(feas.totalCostWon)}</p></div>
                      <div><p className="text-[var(--text-hint)]">분양 매출</p><p className="font-bold text-[var(--text-primary)]">{eok(feas.totalRevenueWon)}</p></div>
                      <div><p className="text-[var(--text-hint)]">ROI</p><p className="font-bold text-[var(--accent-strong)]">{feas.roiPct != null ? `${feas.roiPct.toFixed(1)}%` : "—"}</p></div>
                      <div><p className="text-[var(--text-hint)]">순이익</p><p className="font-bold text-[var(--text-primary)]">{feas.totalRevenueWon != null && feas.totalCostWon != null ? eok(feas.totalRevenueWon - feas.totalCostWon) : "—"}</p></div>
                    </div>
                  </div>
                ) : (
                  <p className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 text-xs text-[var(--text-secondary)]">수지 분석 전 — 수지 페이지에서 매출·원가·ROI를 산출하세요.</p>
                )}
                <BuildCostCard address={site?.address} landAreaSqm={effArea} zone={site?.zoneCode} />
                <DrillCta to={proj("feasibility")}>수지 편집·민감도 상세</DrillCta>
                <DrillCta to={proj("cost")}>BIM 적산·공사비 상세</DrillCta>
              </>
            )}
            {tab === "senior" && (
              <>
                {/* ★시니어 자문(9전문가 PASS/WARN/BLOCK+법조문) — jootek 미보유 차별자. 자급식(SSOT 소비·무과금). */}
                <SeniorConsultPanel />
                <DrillCta to={proj("orchestrate")}>AI 오케스트레이션·전문가 패널 상세</DrillCta>
              </>
            )}
            {tab === "summary" && (
              <>
                <AiInsightCard address={site?.address} />
                <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4">
                  <p className="text-xs font-black text-[var(--text-primary)]">사업 종합(한눈에)</p>
                  <dl className="mt-2 space-y-1.5 text-[11px]">
                    <div className="flex justify-between"><dt className="text-[var(--text-hint)]">대지면적</dt><dd className="font-bold text-[var(--text-primary)]">{effArea ? `${Math.round(effArea).toLocaleString()}㎡ (${Math.round(effArea / 3.305785).toLocaleString()}평)` : "—"}</dd></div>
                    <div className="flex justify-between"><dt className="text-[var(--text-hint)]">용도지역</dt><dd className="font-bold text-[var(--text-primary)]">{resolveDominantZone(site) || "—"}</dd></div>
                    <div className="flex justify-between"><dt className="text-[var(--text-hint)]">필지</dt><dd className="font-bold text-[var(--text-primary)]">{(ssotParcels?.length ?? 0) > 1 ? `통합 ${ssotParcels!.length}필지` : "단일"}</dd></div>
                    <div className="flex justify-between"><dt className="text-[var(--text-hint)]">수지 ROI</dt><dd className="font-bold text-[var(--accent-strong)]">{feas?.roiPct != null ? `${feas.roiPct.toFixed(1)}%` : "분석 전"}</dd></div>
                  </dl>
                  <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-hint)]">각 탭의 요약을 종합한 한눈 보기입니다. 은행제출용 통합 보고서는 상세 페이지에서 생성하세요.</p>
                </div>
                <DrillCta to={proj("report")}>통합 보고서(은행제출)·PDF 상세</DrillCta>
              </>
            )}
            {tab === "boundary" && (
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 text-xs text-[var(--text-secondary)]">
                <p className="font-bold text-[var(--text-primary)]">구획도 다운로드</p>
                <p className="mt-1 leading-relaxed">
                  선택한 {mapAddresses.length}필지의 통합 구획도를 GeoJSON·PNG·PDF로 내려받을 수 있습니다.
                  지도에서 필지·통합 외곽선·용도지역 색을 확인하세요.
                </p>
                <div className="mt-2">
                  <ParcelExportButton
                    parcels={ssotParcels?.map((p) => ({ pnu: p.pnu, address: p.address }))}
                    address={site?.address}
                    pnu={site?.pnu}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 우: 지도(구획도 ↔ 실거래 토글) */}
        <div className="overflow-hidden rounded-2xl border border-[var(--line)]">
          <div className="flex items-center gap-1 border-b border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1.5">
            {([["boundary", "구획도"], ["transactions", "실거래"]] as const).map(([m, label]) => (
              <button key={m} onClick={() => setMapMode(m)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-bold transition ${
                  mapMode === m ? "bg-[var(--accent-strong)] text-white"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
                {label}
              </button>
            ))}
            <span className="ml-auto text-[10px] text-[var(--text-hint)]">
              {mapMode === "boundary" ? "필지경계·용도지역(지적편집도 토글)" : "주변 실거래 가격 마커"}
            </span>
          </div>
          {mapMode === "boundary" ? (
            mapAddresses.length > 0 ? (
              <ParcelBoundaryMap parcels={mapAddresses} primaryZone={site?.zoneCode || undefined} />
            ) : (
              <div className="flex h-[520px] items-center justify-center text-sm text-[var(--text-hint)]">
                표시할 필지가 없습니다.
              </div>
            )
          ) : (
            (site?.address || site?.pnu) ? (
              <NearbyTransactionsMap address={site?.address ?? undefined} pnu={site?.pnu ?? undefined} />
            ) : (
              <div className="flex h-[520px] items-center justify-center text-sm text-[var(--text-hint)]">
                주소가 필요합니다.
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
