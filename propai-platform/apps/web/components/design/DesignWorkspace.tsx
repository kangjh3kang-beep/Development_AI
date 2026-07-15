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
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  DraftingCompass,
  Info,
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

// 설계 엔진 내부 파이프라인(L1~L5) — 참고용 정적 설명. 데모 지표·가짜 상태 없음(무날조):
//   단계별 실시간 상태·정합 지표는 실측 신호가 배선될 때만 표기한다(현재 정적 리스트만).
const ENGINE_LAYERS: { code: string; name: string; desc: string }[] = [
  { code: "L1", name: "기하 커널 SSOT", desc: "설계 기하(좌표·치수)의 단일 진실원천" },
  { code: "L2", name: "제약 검증", desc: "건폐율·용적률·높이 등 법규 제약 검증" },
  { code: "L3", name: "LLM 도구이용", desc: "자연어 의도를 도구 호출로 해석(수치 직접생성 아님)" },
  { code: "L4", name: "근거 검증 게이트", desc: "검증 통과분만 하류 반영(근거·법령 확인)" },
  { code: "L5", name: "BIM 변환", desc: "검증된 기하를 IFC/BIM 모델로 변환" },
];

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
  // 좌측 dock(단계 스테퍼)·우측 패널(작업 기준)의 접이 상태 — 기본 펼침.
  //   좁은 화면이나 도면 집중 편집 시 접어 중앙 뷰포트를 100%로 확장한다(뷰포트 우선).
  const [dockOpen, setDockOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);

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

  // 좌측 dock 스테퍼 각 단계의 상태 배지·상세 문구 — 기존 파이프라인 카드 로직을 그대로 이관.
  const stepDetail: Record<ViewKey, string> = {
    site: hasAddressMismatch
      ? labels.detailReanalysisNeeded
      : hasSiteBasis
        ? labels.detailCurrentBasis
        : labels.detailWaitingSite,
    generate: hasDesignBasis
      ? labels.detailRecommendReflected
      : hasSiteBasis
        ? labels.detailCanGenerate
        : labels.detailSiteBasisNeeded,
    draw: hasDesignBasis ? labels.detailEditorReady : labels.detailRecommendNeeded,
  };
  const stepBadge: Record<ViewKey, string> = {
    site: labels.pipelineStep1Label,
    generate: labels.pipelineStep2Label,
    draw: labels.pipelineStep3Label,
  };

  return (
    // 스튜디오 셸 — 캔버스 보이드(--background-deep) 위에 좌 dock · 중앙 뷰포트 · 우 패널.
    // 앱 헤더/설계센터 프레임 아래를 채워 중앙 뷰포트가 화면을 지배한다(페이지 스크롤 최소화).
    <div className="relative flex min-h-[34rem] min-w-0 flex-col overflow-hidden rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--background-deep)] lg:h-[calc(100dvh-15rem)]">
      {/* 40px 정렬 그리드 — 보이드 위 정렬 가이드(테마 적응 --grid-line, 신규 색 없음). */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          backgroundImage:
            "linear-gradient(var(--grid-line) 1px, transparent 1px), linear-gradient(90deg, var(--grid-line) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative z-10 flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
        {/* ── 좌측 dock: 산출 단계 스테퍼(1차 법규·부지 → 2차 개요 Top-N → 3차 CAD·BIM) ── */}
        <aside
          className={[
            "flex shrink-0 flex-col overflow-hidden rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface)] shadow-[var(--shadow-sm)]",
            dockOpen ? "w-full lg:w-[320px]" : "w-full lg:w-[3.25rem]",
          ].join(" ")}
        >
          <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2.5">
            {dockOpen && <span className="cc-label text-[10px] text-[var(--text-tertiary)]">설계 파이프라인</span>}
            <button
              type="button"
              onClick={() => setDockOpen((v) => !v)}
              aria-expanded={dockOpen}
              aria-label={dockOpen ? "단계 패널 접기" : "단계 패널 펼치기"}
              className="grid size-7 shrink-0 place-items-center rounded-[var(--r-input)] border border-[var(--line)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
            >
              {dockOpen ? <ChevronLeft className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
            </button>
          </div>

          {dockOpen && (
            <nav aria-label={labels.navAriaLabel} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
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
                      "flex items-start gap-3 rounded-[var(--r-card)] border px-3 py-3 text-left transition-colors",
                      active
                        ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]"
                        : state === "complete"
                          ? "border-[color-mix(in_srgb,var(--status-success)_35%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_8%,transparent)] hover:border-[color-mix(in_srgb,var(--status-success)_55%,transparent)]"
                          : "border-[var(--line)] bg-[var(--surface-soft)] hover:border-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)]",
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "grid size-9 shrink-0 place-items-center rounded-full border",
                        active
                          ? "border-transparent bg-[var(--accent-strong)] text-white"
                          : state === "complete"
                            ? "border-[color-mix(in_srgb,var(--status-success)_40%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_12%,transparent)] text-[var(--status-success)]"
                            : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
                      ].join(" ")}
                    >
                      {state === "complete" ? <CheckCircle2 className="size-4" aria-hidden /> : <Icon className="size-4" aria-hidden />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={[
                          "block font-mono text-[10px] font-bold uppercase tracking-wider",
                          active ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]",
                        ].join(" ")}
                      >
                        {stepBadge[item.key]}
                      </span>
                      <span className="mt-0.5 block text-sm font-black text-[var(--text-primary)]">{item.label}</span>
                      <span className="block text-[11px] font-semibold text-[var(--text-hint)]">{item.desc}</span>
                      <span
                        className={[
                          "mt-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold",
                          state === "complete"
                            ? "bg-[color-mix(in_srgb,var(--status-success)_14%,transparent)] text-[var(--status-success)]"
                            : state === "blocked"
                              ? "bg-[var(--surface-strong)] text-[var(--text-tertiary)]"
                              : "bg-[var(--accent-soft)] text-[var(--accent-strong)]",
                        ].join(" ")}
                      >
                        {state === "blocked" && <LockKeyhole className="size-3" aria-hidden />}
                        {stepDetail[item.key]}
                      </span>
                    </span>
                  </button>
                );
              })}
            </nav>
          )}

          {/* ── 엔진 파이프라인(L1~L5) 참고 — 정적 설명(가짜 상태·데모 지표 없음). ── */}
          {dockOpen && (
            <details className="group shrink-0 border-t border-[var(--line)] px-3 py-2.5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 [&::-webkit-details-marker]:hidden">
                <span className="cc-label text-[10px] text-[var(--text-tertiary)]">엔진 파이프라인 (L1–L5)</span>
                <ChevronDown className="size-3.5 text-[var(--text-tertiary)] transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <ol className="mt-2 space-y-1.5">
                {ENGINE_LAYERS.map((l) => (
                  <li key={l.code} className="flex gap-2 rounded-[var(--r-input)] bg-[var(--surface-soft)] px-2.5 py-1.5">
                    <span className="mt-0.5 font-mono text-[10px] font-bold text-[var(--text-tertiary)]">{l.code}</span>
                    <span className="min-w-0">
                      <span className="block text-[11px] font-bold text-[var(--text-primary)]">{l.name}</span>
                      <span className="block text-[10px] leading-4 text-[var(--text-hint)]">{l.desc}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-[10px] leading-4 text-[var(--text-hint)]">
                참고용 파이프라인 설명입니다. 단계별 실시간 상태·정합 지표는 실측 신호가 배선되면 표시됩니다(현재 미표시 — 무날조).
              </p>
            </details>
          )}

          {/* 접힘(데스크톱): 아이콘 레일로 단계 이동 유지. 모바일 접힘은 헤더 토글만 노출(뷰포트 우선). */}
          {!dockOpen && (
            <div className="hidden flex-1 flex-col items-center gap-2 py-3 lg:flex">
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
                    aria-label={item.label}
                    title={item.label}
                    className={[
                      "grid size-9 place-items-center rounded-full border transition-colors",
                      active
                        ? "border-transparent bg-[var(--accent-strong)] text-white"
                        : state === "complete"
                          ? "border-[color-mix(in_srgb,var(--status-success)_40%,transparent)] text-[var(--status-success)]"
                          : "border-[var(--line)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                    ].join(" ")}
                  >
                    {state === "complete" ? <CheckCircle2 className="size-4" aria-hidden /> : <Icon className="size-4" aria-hidden />}
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* ── 중앙: 풀블리드 뷰포트(현재 단계 패널) + 하단 mono 상태바 ── */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
          {/* 뷰포트 시트 — 현재 단계 패널만 표시. 마운트된 패널은 hidden 토글로 상태 보존(무회귀). */}
          <div className="min-h-0 min-w-0 flex-1 overflow-auto rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface)] p-4 shadow-[var(--shadow-sm)] lg:p-5">
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

          {/* ── 하단 상태바 — KPI 7종 mono 통합(뷰포트 하단 고정). 분리된 라이트 바 제거. ── */}
          <div className="min-w-0 shrink-0">
            {hasAddressMismatch ? (
              /* 정본 메트릭 잠금 바 — 차단 상태를 스크린리더가 즉시 읽어야 하는 경보(상태색=--status-warning). */
              <div
                role="alert"
                aria-live="assertive"
                className="flex min-h-[56px] items-center justify-between gap-3 rounded-[var(--r-card)] border border-[color-mix(in_srgb,var(--status-warning)_40%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-4 py-3 text-xs font-semibold text-[var(--status-warning)]"
              >
                <span className="flex items-center gap-2">
                  <AlertTriangle className="size-4" aria-hidden />
                  {labels.metricLockText}
                </span>
                <span className="rounded-full bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] px-3 py-1 text-[11px] font-black">
                  {labels.metricReanalysisNeeded}
                </span>
              </div>
            ) : (
              <MetricBar />
            )}
          </div>
        </div>

        {/* ── 우측 패널: 현재 작업 기준 + 연결 안내(접이식) ── */}
        <aside
          className={[
            "flex shrink-0 flex-col overflow-hidden rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface)] shadow-[var(--shadow-sm)]",
            panelOpen ? "w-full lg:w-[340px]" : "w-full lg:w-[3.25rem]",
          ].join(" ")}
        >
          <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2.5">
            {panelOpen && <span className="cc-label text-[10px] text-[var(--text-tertiary)]">{labels.contextWorkBasis}</span>}
            <button
              type="button"
              onClick={() => setPanelOpen((v) => !v)}
              aria-expanded={panelOpen}
              aria-label={panelOpen ? "작업 기준 패널 접기" : "작업 기준 패널 펼치기"}
              className="grid size-7 shrink-0 place-items-center rounded-[var(--r-input)] border border-[var(--line)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
            >
              {panelOpen ? <ChevronRight className="size-4" aria-hidden /> : <ChevronLeft className="size-4" aria-hidden />}
            </button>
          </div>

          {panelOpen && (
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
              {/* 현재 작업(설계) 기준 = 부지분석 주소. 상단 ContextHeader와 하단 MetricBar가 이미
                  용도지역·대지면적을 정본으로 표기하므로, 이 패널에서는 그 수치를 반복하지 않는다
                  (사용자 지적 '부지 지표 3중 중복' 해소). 대신 '어느 분석을 기준으로 설계하는가'와
                  프로젝트-분석 주소 정합성만 다뤄, 패널의 고유 역할(기준·정합 확인)을 선명히 한다. */}
              <dl className="grid gap-2 text-xs">
                <ContextRow
                  label={labels.contextAnalysisAddress}
                  value={siteAnalysis?.address || labels.contextAnalysisAddressEmpty}
                />
                {/* 프로젝트 주소는 분석 주소와 어긋날 때만(정합성 경고) 함께 노출 — 일치 시 동일
                    주소 중복 표기를 피한다(무회귀: 불일치 시 두 주소를 나란히 보여 원인 노출). */}
                {hasAddressMismatch && (
                  <ContextRow
                    label={labels.contextProjectAddress}
                    value={projectRecord?.address || labels.contextProjectAddressEmpty}
                  />
                )}
              </dl>
              {hasAddressMismatch ? (
                /* 주소 불일치 차단 배너 — 스크린리더가 즉시 읽어야 하는 경보(상태색=--status-warning). */
                <div
                  role="alert"
                  aria-live="assertive"
                  className="rounded-[var(--r-card)] border border-[color-mix(in_srgb,var(--status-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] px-4 py-3 text-xs font-semibold leading-5 text-[var(--status-warning)]"
                >
                  <div className="flex items-center gap-2 text-sm font-black">
                    <AlertTriangle className="size-4" aria-hidden />
                    {labels.addressMismatchTitle}
                  </div>
                  <p className="mt-1 text-[var(--text-secondary)]">{labels.addressMismatchDesc}</p>
                </div>
              ) : (
                <div className="rounded-[var(--r-card)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-xs font-semibold leading-5 text-[var(--text-secondary)]">
                  {labels.pipelineOrderHint}
                  <span className="font-black text-[var(--text-primary)]">{labels.pipelineOrderBold}</span>
                  {labels.pipelineOrderSuffix}
                </div>
              )}
            </div>
          )}

          {!panelOpen && (
            <div className="hidden flex-1 items-start justify-center py-3 lg:flex">
              <Info className="size-4 text-[var(--text-tertiary)]" aria-hidden />
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-[var(--r-card)] border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2">
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
        <div className="mx-auto grid size-14 place-items-center rounded-full border border-[color-mix(in_srgb,var(--status-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_14%,transparent)] text-[var(--status-warning)]">
          <LockKeyhole className="size-6" aria-hidden />
        </div>
        <h3 className="mt-5 text-xl font-black text-[var(--text-primary)]">{title}</h3>
        <p className="mt-2 text-sm font-semibold leading-6 text-[var(--text-secondary)]">{description}</p>
      </div>
    </div>
  );
}
