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
import { Map as MapIcon, Layers, Sun, Construction, Ruler, Download, ArrowRight, MousePointerClick, ChevronDown } from "lucide-react";
import { dynamicMap } from "@/components/common/MapShell";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { AutoZoningBadge } from "@/components/projects/AutoZoningBadge";
import { BuildableEnvelopeCard } from "@/components/projects/BuildableEnvelopeCard";
import { SolarPlacementCard } from "@/components/projects/SolarPlacementCard";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { ParcelExportButton } from "@/components/projects/ParcelExportButton";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";

const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 520, loadingMessage: "구획도 로딩…" },
);

type TabKey = "land" | "regulation" | "development" | "solar" | "boundary";

export default function SiteCanvasPage() {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const id = params?.id as string;
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const [tab, setTab] = useState<TabKey>("land");
  // 필지 선택/변경 패널(지도 클릭선택+검색+엑셀) — 부지 미확정 시 기본 펼침, 확정 후 접힘.
  const [pickerOpen, setPickerOpen] = useState(false);

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

  const TABS: { key: TabKey; label: string; icon: typeof Layers }[] = [
    { key: "land", label: "토지", icon: Layers },
    { key: "regulation", label: "규제", icon: Ruler },
    { key: "development", label: "개발방식", icon: Construction },
    { key: "solar", label: "일조·배치", icon: Sun },
    { key: "boundary", label: "구획도", icon: Download },
  ];

  function DrillCta({ to, children }: { to: string; children: React.ReactNode }) {
    return (
      <Link href={to}
        className="mt-2 inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition hover:border-[var(--accent-strong)]">
        {children} <ArrowRight className="size-3" aria-hidden />
      </Link>
    );
  }

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

          <div className="mt-3 max-h-[60vh] space-y-3 overflow-y-auto pr-1">
            {tab === "land" && (
              <>
                {site?.address ? <AutoZoningBadge address={site.address} /> : null}
                <DrillCta to={proj("site-analysis")}>토지·실거래·적정매입가 상세</DrillCta>
              </>
            )}
            {tab === "regulation" && (
              <>
                <BuildableEnvelopeCard />
                <DrillCta to={proj("legal")}>규제 계층·인허가 상세</DrillCta>
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
                <SolarPlacementCard address={site?.address} pnu={site?.pnu} zone={site?.zoneCode} landAreaSqm={effArea} />
                <DrillCta to={proj("design")}>설계 스튜디오·CAD/BIM 상세</DrillCta>
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

        {/* 우: 자급식 구획도 지도 */}
        <div className="overflow-hidden rounded-2xl border border-[var(--line)]">
          {mapAddresses.length > 0 ? (
            <ParcelBoundaryMap parcels={mapAddresses} primaryZone={site?.zoneCode || undefined} />
          ) : (
            <div className="flex h-[520px] items-center justify-center text-sm text-[var(--text-hint)]">
              표시할 필지가 없습니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
