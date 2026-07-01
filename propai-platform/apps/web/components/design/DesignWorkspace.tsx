"use client";

/**
 * 설계 스튜디오 통합 작업면.
 *
 * 사용자는 엔진/단계가 아니라 산출 흐름을 선택한다:
 * 조건 확인 → 추천안 만들기 → 도면 편집. 내부 컴포넌트는 기존 자산을 유지하되
 * 좌측 스텝레일을 제거해 화면 진입 장벽과 시선 왕복을 줄인다.
 */

import { useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  DraftingCompass,
  FileText,
  Layers3,
  LockKeyhole,
  MapPin,
  Sparkles,
} from "lucide-react";

import { DesignStudio } from "@/components/design/DesignStudio";
import { DesignGenPanel } from "@/components/design/DesignGenPanel";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { MetricBar } from "@/components/design/MetricBar";
import { useProjectContextStore, addressTokenMismatch } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveDominantZone } from "@/lib/zoning-ssot";
import type { Locale } from "@/i18n/config";

/* ── Labels ── */

type Labels = {
  // 내비게이션 스텝 탭 레이블 + 하위 설명
  viewSiteLabel: string;
  viewSiteDesc: string;
  viewGenerateLabel: string;
  viewGenerateDesc: string;
  viewDrawLabel: string;
  viewDrawDesc: string;
  // 파이프라인 카드 단계 레이블
  pipelineStep1Label: string;
  pipelineStep1Title: string;
  pipelineStep2Label: string;
  pipelineStep2Title: string;
  pipelineStep3Label: string;
  pipelineStep3Title: string;
  // 파이프라인 카드 detail 문구
  detailReanalysisNeeded: string;
  detailCurrentBasis: string;
  detailWaitingSite: string;
  detailRecommendReflected: string;
  detailCanGenerate: string;
  detailSiteBasisNeeded: string;
  detailEditorReady: string;
  detailRecommendNeeded: string;
  // 우측 컨텍스트 패널
  contextWorkBasis: string;
  contextProjectAddress: string;
  contextProjectAddressEmpty: string;
  contextAnalysisAddress: string;
  contextAnalysisAddressEmpty: string;
  contextZone: string;
  contextZoneEmpty: string;
  contextZoneAfterReanalysis: string;
  contextArea: string;
  contextAreaAfterReanalysis: string;
  // 주소 정합성 차단 배너 (amber 박스)
  addressMismatchTitle: string;
  addressMismatchDesc: string;
  // 파이프라인 순서 안내 (정합 시) — hint + bold + suffix 3분할
  pipelineOrderHint: string;
  pipelineOrderBold: string;
  pipelineOrderSuffix: string;
  // nav aria-label
  navAriaLabel: string;
  // PipelineBlocker 메시지들
  generateBlockTitleMismatch: string;
  generateBlockTitleNoBasis: string;
  generateBlockDescMismatch: string;
  generateBlockDescNoBasis: string;
  drawBlockTitle: string;
  drawBlockDescMismatch: string;
  drawBlockDescNoBasis: string;
  // 하단 정본 메트릭 잠금 바
  metricLockText: string;
  metricReanalysisNeeded: string;
};

const KO_LABELS: Labels = {
  // 내비게이션 스텝
  viewSiteLabel: "조건 확인",
  viewSiteDesc: "주소·용도지역·한도",
  viewGenerateLabel: "추천안 만들기",
  viewGenerateDesc: "건축개요 Top-N",
  viewDrawLabel: "도면 편집",
  viewDrawDesc: "CAD·BIM·명령",
  // 파이프라인 카드
  pipelineStep1Label: "1차 검증",
  pipelineStep1Title: "법규·부지 정합",
  pipelineStep2Label: "2차 생성",
  pipelineStep2Title: "건축개요 Top-N",
  pipelineStep3Label: "3차 도면",
  pipelineStep3Title: "CAD·BIM 편집",
  // 파이프라인 카드 detail
  detailReanalysisNeeded: "재분석 필요",
  detailCurrentBasis: "현재 부지 기준",
  detailWaitingSite: "부지분석 대기",
  detailRecommendReflected: "추천안 반영됨",
  detailCanGenerate: "생성 가능",
  detailSiteBasisNeeded: "부지 기준 필요",
  detailEditorReady: "편집실 준비",
  detailRecommendNeeded: "추천안 필요",
  // 컨텍스트 패널
  contextWorkBasis: "현재 작업 기준",
  contextProjectAddress: "프로젝트 주소",
  contextProjectAddressEmpty: "프로젝트 주소 미확보",
  contextAnalysisAddress: "분석 주소",
  contextAnalysisAddressEmpty: "부지분석 미실행",
  contextZone: "용도지역",
  contextZoneEmpty: "미확보",
  contextZoneAfterReanalysis: "재분석 후 확정",
  contextArea: "대지면적",
  contextAreaAfterReanalysis: "재분석 후 확정",
  // 주소 정합성 차단 배너
  addressMismatchTitle: "주소 정합성 차단",
  addressMismatchDesc:
    "다른 주소의 부지분석 결과가 남아 있어 추천안·도면 생성을 잠시 막았습니다. 현 프로젝트 기준으로 부지분석을 다시 실행하면 다음 단계가 열립니다.",
  // 파이프라인 순서 안내
  pipelineOrderHint: "산출물은 ",
  pipelineOrderBold: "부지 기준 확정 → Top-N 개요 → 도면 편집",
  pipelineOrderSuffix: " 순서로 연결됩니다.",
  // nav aria-label
  navAriaLabel: "설계 작업 보기",
  // PipelineBlocker
  generateBlockTitleMismatch: "현 프로젝트 기준 부지분석이 필요합니다.",
  generateBlockTitleNoBasis: "부지 조건을 먼저 확정해야 합니다.",
  generateBlockDescMismatch: "다른 주소의 분석값이 추천 건축개요로 흘러가지 않도록 차단했습니다.",
  generateBlockDescNoBasis: "주소·용도지역·대지면적이 준비되면 건축개요 Top-N을 생성할 수 있습니다.",
  drawBlockTitle: "도면 편집 전에 건축개요 추천안이 필요합니다.",
  drawBlockDescMismatch: "먼저 현 프로젝트 기준 부지분석을 다시 실행한 뒤 추천안을 생성하세요.",
  drawBlockDescNoBasis: "Top-N 건축개요 중 하나를 적용하면 CAD·BIM 편집실이 열립니다.",
  // 하단 정본 메트릭 잠금
  metricLockText: "정본 메트릭 잠금: 현 프로젝트와 다른 주소의 분석값은 표시하지 않습니다.",
  metricReanalysisNeeded: "재분석 필요",
};

const EN_LABELS: Labels = {
  // 내비게이션 스텝
  viewSiteLabel: "Site conditions",
  viewSiteDesc: "Address · zone · limits",
  viewGenerateLabel: "Generate options",
  viewGenerateDesc: "Top-N design briefs",
  viewDrawLabel: "Edit drawings",
  viewDrawDesc: "CAD · BIM · commands",
  // 파이프라인 카드
  pipelineStep1Label: "Step 1 — Verify",
  pipelineStep1Title: "Building code · site match",
  pipelineStep2Label: "Step 2 — Generate",
  pipelineStep2Title: "Design brief Top-N",
  pipelineStep3Label: "Step 3 — Draw",
  pipelineStep3Title: "CAD · BIM edit",
  // 파이프라인 카드 detail
  detailReanalysisNeeded: "Re-analysis required",
  detailCurrentBasis: "Current site basis",
  detailWaitingSite: "Awaiting site analysis",
  detailRecommendReflected: "Options applied",
  detailCanGenerate: "Ready to generate",
  detailSiteBasisNeeded: "Site basis required",
  detailEditorReady: "Editor ready",
  detailRecommendNeeded: "Options required",
  // 컨텍스트 패널
  contextWorkBasis: "Current work basis",
  contextProjectAddress: "Project address",
  contextProjectAddressEmpty: "Project address unavailable",
  contextAnalysisAddress: "Analysis address",
  contextAnalysisAddressEmpty: "Site analysis not run",
  contextZone: "Zone",
  contextZoneEmpty: "Unavailable",
  contextZoneAfterReanalysis: "Confirmed after re-analysis",
  contextArea: "Site area",
  contextAreaAfterReanalysis: "Confirmed after re-analysis",
  // 주소 정합성 차단 배너
  addressMismatchTitle: "Address mismatch — blocked",
  addressMismatchDesc:
    "A site analysis result from a different address is still loaded. Generation of options and drawings has been paused. Run site analysis again for the current project address to unlock the next steps.",
  // 파이프라인 순서 안내
  pipelineOrderHint: "Outputs flow as: ",
  pipelineOrderBold: "Site confirmed → Top-N brief → Drawing edit",
  pipelineOrderSuffix: ".",
  // nav aria-label
  navAriaLabel: "Design workflow views",
  // PipelineBlocker
  generateBlockTitleMismatch: "Site analysis for the current project address is required.",
  generateBlockTitleNoBasis: "Site conditions must be confirmed first.",
  generateBlockDescMismatch: "Analysis values from a different address are blocked from flowing into the design brief.",
  generateBlockDescNoBasis: "Once address, zone, and site area are ready, Top-N design briefs can be generated.",
  drawBlockTitle: "A design brief is required before editing drawings.",
  drawBlockDescMismatch: "First re-run site analysis for the current project address, then generate options.",
  drawBlockDescNoBasis: "Apply one of the Top-N design briefs to open the CAD · BIM editor.",
  // 하단 정본 메트릭 잠금
  metricLockText: "Metrics locked: analysis values from a different address are not displayed.",
  metricReanalysisNeeded: "Re-analysis required",
};

// zh-CN은 참조 파일(ProjectLegalWorkspaceClient)과 동일하게 KO_LABELS alias 사용
const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

type ViewKey = "site" | "generate" | "draw";

type PipelineState = "complete" | "ready" | "blocked";

export function DesignWorkspace({ projectId }: { projectId: string }) {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const labels = LABELS[locale as Locale] || LABELS.ko;

  const [view, setView] = useState<ViewKey>("site");
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const projectRecord = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  // CAD/BIM(STEP3)은 한 번이라도 진입한 뒤에만 마운트. 첫 진입 전엔 마운트 자체를 막아
  //  WebGL 점유를 차단한다(lazy). 진입 후엔 hidden 토글로 보존.
  const [drawMounted, setDrawMounted] = useState(false);

  // 현재 로케일 기준 views 배열 (labels 의존 → 컴포넌트 내부에서 생성)
  const views: { key: ViewKey; label: string; desc: string; icon: typeof MapPin }[] = [
    { key: "site", label: labels.viewSiteLabel, desc: labels.viewSiteDesc, icon: MapPin },
    { key: "generate", label: labels.viewGenerateLabel, desc: labels.viewGenerateDesc, icon: Sparkles },
    { key: "draw", label: labels.viewDrawLabel, desc: labels.viewDrawDesc, icon: DraftingCompass },
  ];

  const hasAddressMismatch = !!(
    projectRecord?.address &&
    siteAnalysis?.address &&
    addressTokenMismatch(projectRecord.address, siteAnalysis.address)
  );
  const siteAreaSqm = effectiveLandAreaSqm(siteAnalysis);
  const siteZone = resolveDominantZone(siteAnalysis);
  const hasSiteBasis = !!(
    siteAnalysis &&
    !hasAddressMismatch &&
    (siteAnalysis.address || siteAnalysis.pnu) &&
    siteAreaSqm &&
    siteAreaSqm > 0 &&
    siteZone
  );
  const hasDesignBasis = !!(
    hasSiteBasis &&
    designData &&
    ((designData.totalGfaSqm ?? 0) > 0 ||
      (designData.floorCount ?? 0) > 0 ||
      (designData.far ?? 0) > 0 ||
      designData.buildingType)
  );

  function go(next: ViewKey) {
    if (next === "draw" && hasDesignBasis) setDrawMounted(true);
    setView(next);
  }

  const siteState: PipelineState = hasAddressMismatch ? "blocked" : hasSiteBasis ? "complete" : "ready";
  const generateState: PipelineState = !hasSiteBasis ? "blocked" : hasDesignBasis ? "complete" : "ready";
  const drawState: PipelineState = !hasDesignBasis ? "blocked" : "ready";
  const activeState: Record<ViewKey, PipelineState> = {
    site: siteState,
    generate: generateState,
    draw: drawState,
  };

  return (
    <div className="flex min-h-[32rem] min-w-0 flex-col gap-3 md:h-[calc(100dvh-8rem)]">
      <div className="overflow-hidden rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow-sm)]">
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1.15fr)_minmax(22rem,0.85fr)]">
          <div className="relative overflow-hidden bg-[#07120d] px-6 py-5 text-white">
            <div
              aria-hidden
              className="absolute inset-0 opacity-25"
              style={{
                backgroundImage:
                  "linear-gradient(rgba(221,255,134,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(221,255,134,0.15) 1px, transparent 1px)",
                backgroundSize: "32px 32px",
              }}
            />
            <div className="relative z-10">
              <p className="cc-label text-[10px] text-[#ddff86]">UNIFIED DESIGN PIPELINE</p>
              <h2 className="mt-2 max-w-3xl text-2xl font-black tracking-tight text-white md:text-3xl">
                조건 확인, 추천안 생성, CAD·BIM 편집을 한 흐름으로 묶었습니다.
              </h2>
              <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-white/72">
                현 프로젝트 주소와 부지분석 주소가 맞을 때만 하위 산출물이 열립니다. 이전 주소의 분석값은
                설계안과 도면으로 전파되지 않습니다.
              </p>
              <div className="mt-5 grid gap-2 sm:grid-cols-3">
                <PipelineCard
                  icon={FileText}
                  label={labels.pipelineStep1Label}
                  title={labels.pipelineStep1Title}
                  state={siteState}
                  detail={
                    hasAddressMismatch
                      ? labels.detailReanalysisNeeded
                      : hasSiteBasis
                        ? labels.detailCurrentBasis
                        : labels.detailWaitingSite
                  }
                />
                <PipelineCard
                  icon={Layers3}
                  label={labels.pipelineStep2Label}
                  title={labels.pipelineStep2Title}
                  state={generateState}
                  detail={
                    hasDesignBasis
                      ? labels.detailRecommendReflected
                      : hasSiteBasis
                        ? labels.detailCanGenerate
                        : labels.detailSiteBasisNeeded
                  }
                />
                <PipelineCard
                  icon={DraftingCompass}
                  label={labels.pipelineStep3Label}
                  title={labels.pipelineStep3Title}
                  state={drawState}
                  detail={hasDesignBasis ? labels.detailEditorReady : labels.detailRecommendNeeded}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col justify-between gap-4 bg-[var(--surface-soft)] px-5 py-5">
            <div>
              <p className="cc-label text-[10px] text-[var(--text-tertiary)]">{labels.contextWorkBasis}</p>
              <dl className="mt-3 grid gap-2 text-xs">
                <ContextRow
                  label={labels.contextProjectAddress}
                  value={projectRecord?.address || labels.contextProjectAddressEmpty}
                />
                <ContextRow
                  label={labels.contextAnalysisAddress}
                  value={siteAnalysis?.address || labels.contextAnalysisAddressEmpty}
                />
                <ContextRow
                  label={labels.contextZone}
                  value={!hasAddressMismatch ? siteZone || labels.contextZoneEmpty : labels.contextZoneAfterReanalysis}
                />
                <ContextRow
                  label={labels.contextArea}
                  value={
                    !hasAddressMismatch && siteAreaSqm
                      ? `${Math.round(siteAreaSqm).toLocaleString()}㎡`
                      : labels.contextAreaAfterReanalysis
                  }
                />
              </dl>
            </div>
            {hasAddressMismatch ? (
              /* 주소 불일치 차단 배너 — 스크린리더가 즉시 읽어야 하는 경보 상태 */
              <div
                role="alert"
                aria-live="assertive"
                className="rounded-2xl border border-amber-400/50 bg-amber-100/60 px-4 py-3 text-xs font-semibold leading-5 text-amber-800"
              >
                <div className="flex items-center gap-2 text-sm font-black">
                  <AlertTriangle className="size-4" aria-hidden />
                  {labels.addressMismatchTitle}
                </div>
                <p className="mt-1">{labels.addressMismatchDesc}</p>
              </div>
            ) : (
              <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-xs font-semibold leading-5 text-[var(--text-secondary)]">
                {labels.pipelineOrderHint}
                <span className="font-black text-[var(--text-primary)]">{labels.pipelineOrderBold}</span>
                {labels.pipelineOrderSuffix}
              </div>
            )}
          </div>
        </div>

        <nav
          className="flex max-w-full gap-1 overflow-x-auto border-t border-[var(--line)] bg-[var(--surface)] p-2"
          aria-label={labels.navAriaLabel}
        >
          {views.map((item) => {
            const active = view === item.key;
            const state = activeState[item.key];
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => go(item.key)}
                aria-pressed={active}
                className={[
                  "flex min-w-[12rem] items-center gap-3 rounded-2xl px-4 py-3 text-left transition-colors",
                  active
                    ? "bg-[var(--ink)] text-white shadow-[var(--shadow-sm)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface)]",
                ].join(" ")}
              >
                <span
                  className={[
                    "grid size-9 shrink-0 place-items-center rounded-full border",
                    active ? "border-white/20 bg-white/12" : "border-[var(--line)] bg-[var(--surface-soft)]",
                  ].join(" ")}
                >
                  <Icon className="size-4" aria-hidden />
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-black">{item.label}</span>
                  <span className={active ? "block text-[10px] text-white/70" : "block text-[10px] text-[var(--text-hint)]"}>
                    {item.desc}
                  </span>
                </span>
                {state === "blocked" && (
                  <LockKeyhole className={active ? "ml-auto size-4 text-white/65" : "ml-auto size-4 text-[var(--text-hint)]"} aria-hidden />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* 메인 — 현재 단계의 패널만 표시. 마운트된 패널은 hidden 토글로 상태 보존(무회귀). */}
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <div className={view === "site" ? "" : "hidden"}>
          {/* onOpen3D: 부지 단계 우측 캔버스의 "3D·BIM 편집실로 →" 버튼이 호출 → draw 스텝으로 전환.
              go("draw")가 기존 lazy 3D(WebGL)를 그때 마운트한다(컨텍스트 고갈 방지 아키텍처 보존). */}
          <DesignStudio projectId={projectId} onOpen3D={() => go("draw")} />
        </div>
        <div className={view === "generate" ? "" : "hidden"}>
          {hasSiteBasis ? (
            <DesignGenPanel projectId={projectId} />
          ) : (
            <PipelineBlocker
              title={
                hasAddressMismatch
                  ? labels.generateBlockTitleMismatch
                  : labels.generateBlockTitleNoBasis
              }
              description={
                hasAddressMismatch
                  ? labels.generateBlockDescMismatch
                  : labels.generateBlockDescNoBasis
              }
            />
          )}
        </div>
        {drawMounted && hasDesignBasis && (
          <div className={view === "draw" ? "" : "hidden"}>
            <CadBimIntegrationPanel projectId={projectId} dictionary={{}} />
          </div>
        )}
        {view === "draw" && (!drawMounted || !hasDesignBasis) && (
          <PipelineBlocker
            title={labels.drawBlockTitle}
            description={
              hasAddressMismatch ? labels.drawBlockDescMismatch : labels.drawBlockDescNoBasis
            }
          />
        )}
      </div>

      {/* 하단 정본 메트릭바 — 메인 스크롤과 무관하게 grid 행으로 물리 분리(z-index 비의존). */}
      <div className="min-w-0">
        {hasAddressMismatch ? (
          /* 정본 메트릭 잠금 바 — 차단 상태를 스크린리더가 즉시 읽어야 하는 경보 */
          <div
            role="alert"
            aria-live="assertive"
            className="cc-panel flex min-h-[64px] items-center justify-between gap-3 px-4 py-3 text-xs font-semibold text-amber-700"
          >
            <span className="flex items-center gap-2">
              <AlertTriangle className="size-4" aria-hidden />
              {labels.metricLockText}
            </span>
            <span className="rounded-full bg-amber-100 px-3 py-1 text-[11px] font-black">
              {labels.metricReanalysisNeeded}
            </span>
          </div>
        ) : (
          <MetricBar />
        )}
      </div>
    </div>
  );
}

function PipelineCard({
  icon: Icon,
  label,
  title,
  state,
  detail,
}: {
  icon: typeof MapPin;
  label: string;
  title: string;
  state: PipelineState;
  detail: string;
}) {
  const tone =
    state === "complete"
      ? "border-[#ddff86]/50 bg-[#ddff86]/12 text-[#ddff86]"
      : state === "ready"
        ? "border-white/16 bg-white/10 text-white"
        : "border-amber-300/35 bg-amber-300/12 text-amber-100";
  return (
    <div className={`rounded-3xl border px-4 py-3 ${tone}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="cc-label text-[10px] text-current/75">{label}</span>
        {state === "complete" ? <CheckCircle2 className="size-4" aria-hidden /> : <Icon className="size-4" aria-hidden />}
      </div>
      <p className="mt-3 text-sm font-black text-white">{title}</p>
      <p className="mt-1 text-[11px] font-semibold text-white/62">{detail}</p>
    </div>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2">
      <dt className="shrink-0 font-bold text-[var(--text-tertiary)]">{label}</dt>
      <dd className="min-w-0 truncate font-black text-[var(--text-primary)]" title={value}>
        {value}
      </dd>
    </div>
  );
}

function PipelineBlocker({ title, description }: { title: string; description: string }) {
  return (
    <div className="cc-panel grid min-h-[22rem] place-items-center p-8 text-center">
      <div className="max-w-md">
        <div className="mx-auto grid size-14 place-items-center rounded-full border border-amber-300/50 bg-amber-100 text-amber-700">
          <LockKeyhole className="size-6" aria-hidden />
        </div>
        <h3 className="mt-5 text-xl font-black text-[var(--text-primary)]">{title}</h3>
        <p className="mt-2 text-sm font-semibold leading-6 text-[var(--text-secondary)]">{description}</p>
      </div>
    </div>
  );
}
