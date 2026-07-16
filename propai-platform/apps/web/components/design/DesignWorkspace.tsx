"use client";

/**
 * 설계 스튜디오 통합 작업면.
 *
 * 사용자는 엔진/단계가 아니라 산출 흐름을 선택한다:
 * 조건 확인 → 추천안 만들기 → 도면 편집. 내부 컴포넌트는 기존 자산을 유지하되
 * 좌측 스텝레일을 제거해 화면 진입 장벽과 시선 왕복을 줄인다.
 */

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  Calculator,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  DraftingCompass,
  Info,
  Loader2,
  LockKeyhole,
  MapPin,
  Ruler,
  ScrollText,
  Sparkles,
} from "lucide-react";

import { DesignStudio } from "@/components/design/DesignStudio";
import { DesignGenPanel } from "@/components/design/DesignGenPanel";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";
import { MetricBar } from "@/components/design/MetricBar";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { useProjectContextStore, addressTokenMismatch } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { hasSiteBasis as computeHasSiteBasis } from "@/lib/design-ssot";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { toLegalChips, type LegalRefChipInput } from "@/lib/legal-refs";
import {
  resolveFarWithBasis,
  resolveBcrWithBasis,
  limitBasisLabel,
  resolveDominantZone,
  type LimitBasis,
} from "@/lib/zoning-ssot";
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
  // 우측 "근거·한도" 패널 (기존 "분석 주소·순서 안내" 중복 표기를 대체)
  panelTitle: string;             // 패널 헤더(접힘 토글 aria와 정합)
  limitsCardTitle: string;        // 부지 실효 한도 카드 제목
  limitsBcr: string;              // 건폐율
  limitsFar: string;              // 용적률
  limitsFloors: string;           // 층수
  limitsFloorsPending: string;    // 설계 전 층수 미확정 표기
  limitsEmpty: string;            // 부지분석 전 정직 안내
  limitsBcrTip: string;           // 건폐율 ⓘ 쉬운 설명
  limitsFarTip: string;           // 용적률 ⓘ 쉬운 설명
  legalRefsTitle: string;         // 법령 근거 소제목
  specialWarnTitle: string;       // 특이부지 경고 제목
  panelNextTitle: string;         // 다음 단계 소제목
  panelNextCta: string;           // 다음 단계 이동 버튼(고유 라벨 — dock·흐름바 CTA와 이름 충돌 방지)
  // 주소 정합성 차단 배너 (amber 박스)
  addressMismatchTitle: string;
  addressMismatchDesc: string;
  // ── 준비 대시보드(잠긴 단계) — 해제 요건 체크리스트 + 산출물 예시 구조 ──
  readyChecklistTitle: string;    // "해제 요건"
  reqAddress: string;             // 주소
  reqZone: string;                // 용도지역
  reqArea: string;                // 대지면적
  reqDesign: string;              // 추천안 적용
  reqGoSite: string;              // 부지 조건으로 이동 CTA
  reqGoGenerate: string;          // 추천안 만들기로 이동 CTA
  reqMetLabel: string;            // 충족 aria/배지
  reqUnmetLabel: string;          // 미충족 aria/배지
  previewTitle: string;           // "이 단계에서 얻는 산출물"
  previewExampleBadge: string;    // "예시 구조"(정직 라벨)
  previewHonest: string;          // 예시 구조 정직 안내문
  readyUnlockHint: string;        // "모든 요건 충족 시 자동 해제"
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
  // ── 흐름 진행 바(FlowAdvanceBar) — "지금 어느 단계·다음이 무엇" + 다음 액션 CTA ──
  // dock 스텝 라벨(viewGenerateLabel/viewDrawLabel)과 접근성 이름이 겹치지 않도록 별도 문구.
  //   dock=단계 네비게이션 컨트롤, CTA=현재 단계 완료 후 진행 액션 → 서로 다른 컨트롤이라
  //   접근성 이름 중복(중복 매칭)·label-in-name 혼동을 피하려 어휘를 구분한다.
  flowNextPrefix: string;        // "다음 단계" 프리픽스 칩
  flowToGenerate: string;        // site 완료 → 생성 단계로 이동 CTA
  flowToDraw: string;            // generate 완료 → 도면 단계로 이동 CTA
  flowHintNeedSite: string;      // site 미완료 시 정직 안내(무CTA)
  flowHintNeedDesign: string;    // generate 미완료 시 정직 안내(무CTA)
  flowTerminal: string;          // draw(마지막 단계) 안내
  // ★로드맵⑥: 설계→적산→수지 원스톱 — draw(도면 완료) 단계에서 실제 존재하는 다음 경로로 이어준다.
  //   flowToCost=이 설계로 BIM 5D 적산(/projects/[id]/cost, projectId로 컨텍스트 유지) 실행 CTA.
  //   flowNextChain=IA 파이프라인(설계 다음=적산→수지분석) 흐름 안내(실경로만·과장 금지).
  flowToCost: string;            // 도면 완료 → 적산 실행 CTA(프로젝트 컨텍스트 유지)
  flowNextChain: string;         // "다음 단계: 적산 → 수지 반영" 흐름 안내
  flowProgressAria: string;      // 진행 표시 aria-label
  flowNowLabel: string;          // "현재" prefix
  flowReview: string;            // CTA 타깃이 이미 complete일 때(방어적 분기) — "이어보기/검토"류
  // 단계 상태 어휘(dock 배지·흐름 바 공용) — 완료/진행가능/대기/로딩
  stateDone: string;
  stateReady: string;
  stateBlocked: string;
  stateLoading: string;
  // dock 추천 다음 단계 강조 칩
  nextChip: string;
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
  // 근거·한도 패널
  panelTitle: "근거 · 한도",
  limitsCardTitle: "부지 실효 한도",
  limitsBcr: "건폐율",
  limitsFar: "용적률",
  limitsFloors: "층수",
  limitsFloorsPending: "설계 시 확정",
  limitsEmpty: "부지분석을 실행하면 이 부지의 실효 건폐율·용적률·근거가 표시됩니다.",
  limitsBcrTip: "땅 면적 중 건물 1층이 덮을 수 있는 비율. 높을수록 넓게 지음.",
  limitsFarTip: "땅 면적 대비 전체 층 바닥면적 합의 비율. 높을수록 많이(높이) 지음.",
  legalRefsTitle: "법령 근거",
  specialWarnTitle: "특이부지 주의",
  panelNextTitle: "다음 단계",
  panelNextCta: "이 단계로 이동",
  // 주소 정합성 차단 배너
  addressMismatchTitle: "주소 정합성 차단",
  addressMismatchDesc:
    "다른 주소의 부지분석 결과가 남아 있어 추천안·도면 생성을 잠시 막았습니다. 현 프로젝트 기준으로 부지분석을 다시 실행하면 다음 단계가 열립니다.",
  // 준비 대시보드
  readyChecklistTitle: "해제 요건",
  reqAddress: "주소",
  reqZone: "용도지역",
  reqArea: "대지면적",
  reqDesign: "추천안 적용",
  reqGoSite: "부지 조건 확인하러 가기",
  reqGoGenerate: "추천안 만들러 가기",
  reqMetLabel: "충족",
  reqUnmetLabel: "미충족",
  previewTitle: "이 단계에서 얻는 산출물",
  previewExampleBadge: "예시 구조",
  previewHonest: "실제 산출이 아닌 예시 구조 미리보기입니다. 요건을 모두 충족하면 실데이터로 채워집니다.",
  readyUnlockHint: "요건을 모두 충족하면 이 단계가 자동으로 열립니다.",
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
  // 흐름 진행 바
  flowNextPrefix: "다음 단계",
  flowToGenerate: "추천안 생성 시작",
  flowToDraw: "CAD·BIM 편집 열기",
  flowHintNeedSite: "부지 조건(주소·용도지역·대지면적)을 확정하면 다음 단계가 열립니다.",
  flowHintNeedDesign: "추천안(건축개요)을 하나 적용하면 다음 단계가 열립니다.",
  flowTerminal: "마지막 단계 — 검증된 도면을 CAD·BIM으로 편집합니다.",
  flowToCost: "이 설계로 적산 실행",
  flowNextChain: "다음 단계: 적산 → 수지 반영",
  flowProgressAria: "설계 흐름 진행 상태",
  flowNowLabel: "현재",
  flowReview: "결과 이어보기",
  stateDone: "완료",
  stateReady: "진행 가능",
  stateBlocked: "대기",
  stateLoading: "부지 보강 중",
  nextChip: "다음",
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
  // 근거·한도 패널
  panelTitle: "Basis · limits",
  limitsCardTitle: "Effective site limits",
  limitsBcr: "Coverage",
  limitsFar: "FAR",
  limitsFloors: "Floors",
  limitsFloorsPending: "Set on design",
  limitsEmpty: "Run site analysis to see this site's effective coverage, FAR and basis.",
  limitsBcrTip: "Share of the lot the building footprint may cover. Higher = wider footprint.",
  limitsFarTip: "Total floor area vs. lot area. Higher = more (taller) building.",
  legalRefsTitle: "Legal basis",
  specialWarnTitle: "Special parcel notice",
  panelNextTitle: "Next step",
  panelNextCta: "Go to this step",
  // 주소 정합성 차단 배너
  addressMismatchTitle: "Address mismatch — blocked",
  addressMismatchDesc:
    "A site analysis result from a different address is still loaded. Generation of options and drawings has been paused. Run site analysis again for the current project address to unlock the next steps.",
  // 준비 대시보드
  readyChecklistTitle: "Unlock requirements",
  reqAddress: "Address",
  reqZone: "Zone",
  reqArea: "Site area",
  reqDesign: "Design applied",
  reqGoSite: "Go to site conditions",
  reqGoGenerate: "Go to generate options",
  reqMetLabel: "Met",
  reqUnmetLabel: "Not met",
  previewTitle: "What this step produces",
  previewExampleBadge: "Example structure",
  previewHonest: "Preview of the output structure only — not real results. Filled with live data once requirements are met.",
  readyUnlockHint: "This step unlocks automatically once all requirements are met.",
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
  // 흐름 진행 바
  flowNextPrefix: "Next step",
  flowToGenerate: "Start generating options",
  flowToDraw: "Open CAD·BIM editor",
  flowHintNeedSite: "Confirm site conditions (address · zone · area) to unlock the next step.",
  flowHintNeedDesign: "Apply one design brief to unlock the next step.",
  flowTerminal: "Final step — edit the verified drawings in CAD·BIM.",
  flowToCost: "Run cost estimate for this design",
  flowNextChain: "Next: cost estimate → feasibility",
  flowProgressAria: "Design flow progress",
  flowNowLabel: "Now",
  flowReview: "Continue to results",
  stateDone: "Done",
  stateReady: "In progress",
  stateBlocked: "Waiting",
  stateLoading: "Enriching site",
  nextChip: "Next",
};

// zh-CN은 참조 파일(ProjectLegalWorkspaceClient)과 동일하게 KO_LABELS alias 사용
const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

type ViewKey = "site" | "generate" | "draw";

type PipelineState = "complete" | "ready" | "blocked" | "loading";

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
  // 부지 보강(다필지 메타 fetch) 진행 신호 — 실측 store 필드. '로딩' 상태를 날조 없이 표기하는 근거.
  const parcelEnrichPending = useProjectContextStore((s) => s.parcelEnrichPending);
  const projectRecord = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  // CAD/BIM(STEP3)은 한 번이라도 진입한 뒤에만 마운트. 첫 진입 전엔 마운트 자체를 막아
  //  WebGL 점유를 차단한다(lazy). 진입 후엔 hidden 토글로 보존.
  const [drawMounted, setDrawMounted] = useState(false);
  // 좌측 dock(단계 스테퍼)·우측 패널(작업 기준)의 접이 상태 — 기본 펼침.
  //   좁은 화면이나 도면 집중 편집 시 접어 중앙 뷰포트를 100%로 확장한다(뷰포트 우선).
  const [dockOpen, setDockOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  // 우측 레일 자동 접힘(F1) — 뷰포트가 아니라 '작업면 컨테이너 실폭'을 ResizeObserver로 측정해
  //   좁을 때(< 1120px) 자동 접어 중앙 폭을 확보한다(컨테이너 기준 판정 — 뷰포트 미디어쿼리
  //   재도입 금지 원칙 준수). 사용자가 토글을 직접 누르면(panelTouchedRef) 이후 자동 제어를 멈춰
  //   수동 선택을 보존한다(수동 복원 가능).
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelTouchedRef = useRef(false);
  useEffect(() => {
    const el = rootRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      if (panelTouchedRef.current) return; // 수동 조작 후엔 자동 제어 중단(사용자 의도 보존)
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) setPanelOpen(w >= 1120);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // 토글 클릭 시 수동 플래그를 세워 자동 접힘이 사용자의 선택을 되돌리지 않게 한다.
  const togglePanel = () => {
    panelTouchedRef.current = true;
    setPanelOpen((v) => !v);
  };

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
  // ★공용 판정(lib/design-ssot.hasSiteBasis) — DesignStudio(콘솔)도 동일 함수를 호출해 "부지 기준
  //   준비됨" 판정이 레일·콘솔 사이에서 구조적으로 divergence 불가능하게 한다(PR#316 리뷰 M2).
  const hasSiteBasis = computeHasSiteBasis(siteAnalysis, projectRecord?.address);
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

  // ── 준비 요건 개별 판정(준비 대시보드용) — hasSiteBasis의 구성요소를 항목별로 분해해
  //    "무엇이 남았는지"를 실시간 체크리스트로 보여준다(동일 술어에서 파생 — 레일·대시보드 정합).
  const reqAddressOk = !!(siteAnalysis?.address || siteAnalysis?.pnu) && !hasAddressMismatch;
  const reqZoneOk = !!resolveDominantZone(siteAnalysis);
  const areaVal = effectiveLandAreaSqm(siteAnalysis);
  const reqAreaOk = typeof areaVal === "number" && areaVal > 0;

  // ── 부지 실효 한도(우측 근거·한도 패널) — 값 + 근거계층(법정상한/실효)을 함께(공용 리졸버·무날조). ──
  const siteFar = resolveFarWithBasis(siteAnalysis);
  const siteBcr = resolveBcrWithBasis(siteAnalysis);
  // 층수 클램프 — 설계 산출이 있으면 정본 층수, 없으면 null("설계 시 확정").
  const floorClamp = designData?.floorCount ?? null;
  // 법령 원문 링크 — siteAnalysis.legalRefs(unknown[])에서 법령명 있는 항목만 안전 추출(빈 칩 방지).
  const legalChips = toLegalChips(siteAnalysis?.legalRefs);
  const special = siteAnalysis?.specialParcel ?? null;
  const isSpecial = !!special?.isSpecial;

  // 부지 보강이 진행 중이고 아직 기준이 확정되지 않았으면(그리고 주소불일치가 아니면) '로딩'.
  //   실측 신호(parcelEnrichPending)에만 의존 — 가짜 로딩 표기 금지(무날조).
  const siteLoading = parcelEnrichPending && !hasSiteBasis && !hasAddressMismatch;
  const siteState: PipelineState = hasAddressMismatch
    ? "blocked"
    : siteLoading
      ? "loading"
      : hasSiteBasis
        ? "complete"
        : "ready";
  const generateState: PipelineState = !hasSiteBasis ? "blocked" : hasDesignBasis ? "complete" : "ready";
  const drawState: PipelineState = !hasDesignBasis ? "blocked" : "ready";
  const activeState: Record<ViewKey, PipelineState> = {
    site: siteState,
    generate: generateState,
    draw: drawState,
  };

  // 추천 '다음 단계' — 순서(부지→생성→도면)상 아직 완료되지 않은 첫 단계(실상태 파생·무날조).
  //   dock의 "다음" 강조와 흐름 바(FlowAdvanceBar)의 CTA 타깃이 **이 값 하나**를 공유한다(단일
  //   소스). 예전에는 흐름 바가 sequentialNext[view](현재 뷰의 순차 다음)를 따로 썼는데, 완료된
  //   프로젝트를 site 뷰로 재진입하면(site·generate 둘 다 complete) sequentialNext는 이미 끝난
  //   generate를 다시 가리키면서 dock의 nextView=draw 강조와 상충했다 — 재발 방지를 위해 이 값
  //   하나로 통합한다(리뷰 지적 #1).
  const nextView: ViewKey =
    siteState !== "complete" ? "site" : generateState !== "complete" ? "generate" : "draw";

  // 좌측 dock 스테퍼 각 단계의 상태 배지·상세 문구 — 기존 파이프라인 카드 로직을 그대로 이관.
  const stepDetail: Record<ViewKey, string> = {
    site: hasAddressMismatch
      ? labels.detailReanalysisNeeded
      : siteLoading
        ? labels.stateLoading
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
    //   ★갇힌 프레임 해소(Pillar D): 종전 고정높이(lg:h-[calc(100dvh-15rem)]) + 내부 overflow-auto가
    //   페이지 스크롤과 이중 스크롤을 만들었다. 이제 고정높이·overflow-hidden을 제거해 셸이 콘텐츠
    //   높이만큼 자라고 페이지가 단일 스크롤을 갖는다. 좌 dock은 sticky-top, 하단 KPI/흐름바는
    //   sticky-bottom으로 스크롤 중에도 고정 노출된다(overflow-hidden 제거가 sticky의 전제 — 스크롤
    //   컨테이너가 셸에 생기면 sticky가 페이지가 아닌 셸에 묶여 무력화됨).
    <div
      ref={rootRef}
      className="relative flex min-h-[34rem] min-w-0 flex-col rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--background-deep)]"
    >
      {/* 40px 정렬 그리드 — 보이드 위 정렬 가이드(테마 적응 --grid-line, 신규 색 없음).
          overflow-hidden 대신 rounded-[inherit]로 모서리를 배경 자체에 둥글려 클립 없이 정합. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0 rounded-[var(--r-panel)]"
        style={{
          backgroundImage:
            "linear-gradient(var(--grid-line) 1px, transparent 1px), linear-gradient(90deg, var(--grid-line) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative z-10 flex flex-col gap-3 p-3 lg:flex-row lg:items-start">
        {/* ── 좌측 dock: 산출 단계 스테퍼(1차 법규·부지 → 2차 개요 Top-N → 3차 CAD·BIM) ──
            Pillar D: lg에서 sticky-top + self-start로 페이지를 스크롤해도 파이프라인 레일이 고정
            노출된다. 레일 자체는 max-h로 뷰포트 이내로 묶고 내부 nav가 넘치면 스크롤(레일만 국소). */}
        <aside
          className={[
            // ★리뷰 HIGH 수정: lg:top-3(0.75rem)는 전역 앱 헤더(DashboardChromeGate 'sticky
            //   top-2 z-[1000]', 실측 높이 80px)보다 얕아 스크롤 시 dock/panel 상단(라벨+접기
            //   토글+첫 카드)이 헤더 뒤로 가려져 토글 클릭이 불가능했다. 공용 오프셋
            //   var(--app-header-offset)(tokens.css SSOT·6.25rem=헤더 고정 시 하단경계
            //   5.5rem+여백 0.75rem)로 top·max-h를 함께 재정합(불일치 해소). calc() 내부는
            //   Tailwind 임의값 규칙상 공백을 _로 표기해야 유효 CSS로 컴파일된다(공백 없는
            //   calc(a-b)는 무효 선언으로 조용히 무시됨 — 브라우저 계산 확인).
            "flex shrink-0 flex-col overflow-hidden rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface)] shadow-[var(--shadow-sm)] lg:sticky lg:top-[var(--app-header-offset)] lg:self-start lg:max-h-[calc(100dvh_-_var(--app-header-offset)_-_1rem)]",
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
            // gap-0 + 단계 사이 StepConnector(진행선)로 "부지→생성→도면" 흐름을 시각적으로 잇는다.
            //   연결선은 이전 단계가 complete일 때만 채워져(초록) 진행이 어디까지 왔는지 정직하게 보인다.
            <nav aria-label={labels.navAriaLabel} className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3">
              {views.map((item, i) => {
                const active = view === item.key;
                const state = activeState[item.key];
                const Icon = item.icon;
                // '다음 추천 단계' 강조 — 현재 보고 있지 않고 아직 미완료인, 순서상 다음 단계일 때만.
                const isNext = item.key === nextView && !active && state !== "complete";
                return (
                  <Fragment key={item.key}>
                    <button
                      type="button"
                      onClick={() => go(item.key)}
                      aria-pressed={active}
                      aria-current={active ? "step" : undefined}
                      className={[
                        "relative flex items-start gap-3 rounded-[var(--r-card)] border px-3 py-3 text-left transition-colors",
                        active
                          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]"
                          : state === "complete"
                            ? "border-[color-mix(in_srgb,var(--status-success)_35%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_8%,transparent)] hover:border-[color-mix(in_srgb,var(--status-success)_55%,transparent)]"
                            : isNext
                              ? "border-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)] bg-[var(--surface-soft)] ring-1 ring-[color-mix(in_srgb,var(--accent-strong)_30%,transparent)] hover:border-[var(--accent-strong)]"
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
                              : state === "loading"
                                ? "border-[color-mix(in_srgb,var(--accent-strong)_40%,transparent)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                                : isNext
                                  ? "border-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)] bg-[var(--surface-strong)] text-[var(--accent-strong)]"
                                  : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
                        ].join(" ")}
                      >
                        {state === "complete" ? (
                          <CheckCircle2 className="size-4" aria-hidden />
                        ) : state === "loading" ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden />
                        ) : state === "blocked" ? (
                          <LockKeyhole className="size-4" aria-hidden />
                        ) : (
                          <Icon className="size-4" aria-hidden />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span
                            className={[
                              "font-mono text-[10px] font-bold uppercase tracking-wider",
                              active ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]",
                            ].join(" ")}
                          >
                            {stepBadge[item.key]}
                          </span>
                          {isNext && (
                            <span className="inline-flex items-center gap-0.5 rounded-full bg-[var(--accent-strong)] px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wide text-white">
                              <ArrowRight className="size-2.5" aria-hidden />
                              {labels.nextChip}
                            </span>
                          )}
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
                          {state === "loading" && <Loader2 className="size-3 animate-spin" aria-hidden />}
                          {stepDetail[item.key]}
                        </span>
                      </span>
                    </button>
                    {i < views.length - 1 && <StepConnector filled={state === "complete"} />}
                  </Fragment>
                );
              })}

              {/* ── 엔진 파이프라인(L1~L5) 참고 — 정적 설명(가짜 상태·데모 지표 없음).
                    ★리뷰 LOW 수정: 이전엔 nav 바깥의 별도 shrink-0 형제였다 — nav는 flex-1
                    overflow-y-auto로 자체 스크롤하는데, details는 shrink-0라 줄어들지 않아
                    극단적으로 짧은 뷰포트(aside가 --app-header-offset 기반 max-h로 눌릴 때)에서
                    details 본문이 aside의 overflow-hidden에 잘릴 수 있었다. nav 안으로 옮겨
                    같은 스크롤 영역에 편입시켜 클립 없이 항상 스크롤로 도달 가능하게 한다. */}
              <details className="group mt-2 shrink-0 border-t border-[var(--line)] px-1 pt-2.5">
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
            </nav>
          )}

          {/* 접힘(데스크톱): 아이콘 레일로 단계 이동 유지 + 미니 진행선. 모바일 접힘은 헤더 토글만. */}
          {!dockOpen && (
            <div className="hidden flex-1 flex-col items-center py-3 lg:flex">
              {views.map((item, i) => {
                const active = view === item.key;
                const state = activeState[item.key];
                const Icon = item.icon;
                const isNext = item.key === nextView && !active && state !== "complete";
                return (
                  <Fragment key={item.key}>
                    <button
                      type="button"
                      onClick={() => go(item.key)}
                      aria-pressed={active}
                      aria-current={active ? "step" : undefined}
                      aria-label={`${item.label} — ${stepDetail[item.key]}`}
                      title={`${item.label} · ${stepDetail[item.key]}`}
                      className={[
                        "grid size-9 place-items-center rounded-full border transition-colors",
                        active
                          ? "border-transparent bg-[var(--accent-strong)] text-white"
                          : state === "complete"
                            ? "border-[color-mix(in_srgb,var(--status-success)_40%,transparent)] text-[var(--status-success)]"
                            : isNext
                              ? "border-[color-mix(in_srgb,var(--accent-strong)_50%,transparent)] text-[var(--accent-strong)] ring-1 ring-[color-mix(in_srgb,var(--accent-strong)_30%,transparent)]"
                              : "border-[var(--line)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]",
                      ].join(" ")}
                    >
                      {state === "complete" ? (
                        <CheckCircle2 className="size-4" aria-hidden />
                      ) : state === "loading" ? (
                        <Loader2 className="size-4 animate-spin" aria-hidden />
                      ) : state === "blocked" ? (
                        <LockKeyhole className="size-4" aria-hidden />
                      ) : (
                        <Icon className="size-4" aria-hidden />
                      )}
                    </button>
                    {i < views.length - 1 && (
                      <span
                        aria-hidden
                        className="my-1 block h-4 w-0.5 rounded-full transition-colors"
                        style={{ background: state === "complete" ? "var(--status-success)" : "var(--line)" }}
                      />
                    )}
                  </Fragment>
                );
              })}
            </div>
          )}
        </aside>

        {/* ── 중앙: 뷰포트(현재 단계 패널) + 하단 sticky 상태바(흐름바 + KPI) ── */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {/* 뷰포트 시트 — 현재 단계 패널만 표시. ★Pillar D: 내부 overflow-auto·고정높이 제거 →
              콘텐츠 높이만큼 자라고 페이지가 단일 스크롤을 갖는다(이중 스크롤 소멸). 중앙 실폭이
              늘어 DesignStudio의 인스펙터/캔버스 2열(@4xl)이 자연 발화. 마운트된 패널은 hidden
              토글로 상태 보존(무회귀). */}
          <div className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface)] p-4 shadow-[var(--shadow-sm)] lg:p-5">
            <div className={view === "site" ? "" : "hidden"}>
              {/* onOpen3D: 부지 단계 우측 캔버스의 "3D·BIM 편집실로 →" 버튼이 호출 → draw 스텝으로 전환.
                  go("draw")가 기존 lazy 3D(WebGL)를 그때 마운트한다(컨텍스트 고갈 방지 아키텍처 보존). */}
              <DesignStudio projectId={projectId} onOpen3D={() => go("draw")} />
            </div>
            <div className={view === "generate" ? "" : "hidden"}>
              {hasSiteBasis ? (
                <DesignGenPanel projectId={projectId} />
              ) : (
                /* ★Pillar C: 잠긴 단계 = 빈 자물쇠 화면 대신 '준비 대시보드'(해제 요건 체크리스트 +
                   산출물 예시 구조 미리보기). 요건 충족 순간 hasSiteBasis가 true가 되어 자동 언락. */
                <ReadinessDashboard
                  stage="generate"
                  hasAddressMismatch={hasAddressMismatch}
                  reqAddressOk={reqAddressOk}
                  reqZoneOk={reqZoneOk}
                  reqAreaOk={reqAreaOk}
                  hasDesignBasis={hasDesignBasis}
                  labels={labels}
                  onGo={go}
                />
              )}
            </div>
            {drawMounted && hasDesignBasis && (
              <div className={view === "draw" ? "" : "hidden"}>
                <CadBimIntegrationPanel projectId={projectId} dictionary={{}} />
              </div>
            )}
            {view === "draw" && (!drawMounted || !hasDesignBasis) && (
              <ReadinessDashboard
                stage="draw"
                hasAddressMismatch={hasAddressMismatch}
                reqAddressOk={reqAddressOk}
                reqZoneOk={reqZoneOk}
                reqAreaOk={reqAreaOk}
                hasDesignBasis={hasDesignBasis}
                labels={labels}
                onGo={go}
              />
            )}
          </div>

          {/* ── 하단 sticky 상태바(Pillar D) — 흐름 진행 바 + KPI 바를 한 컨테이너에 묶어 sticky-bottom.
                페이지를 스크롤해도 "현재 단계·다음 액션 + 설계 산출 KPI"가 항상 바닥에 고정 노출된다.
                bg 불투명(surface)이라 스크롤 콘텐츠가 뒤로 지나가도 겹침 없이 읽힌다. ── */}
          <div className="sticky bottom-0 z-20 flex min-w-0 flex-col gap-3 lg:bottom-3">
            {/* 흐름 진행 바 — 실상태(activeState)에 직접 연결(무날조). ★Pillar A: 좌측 dock이 펼쳐져
                파이프라인 레일이 이미 보이면 흐름바의 3단계 진행 dots는 중복이므로 숨기고(showProgress=
                !dockOpen), dock이 접혔을 때만 컴팩트 진행 인디케이터로 표시한다. */}
            <FlowAdvanceBar
              view={view}
              states={activeState}
              views={views}
              nextView={nextView}
              hasAddressMismatch={hasAddressMismatch}
              showProgress={!dockOpen}
              labels={labels}
              onGo={go}
              // ★로드맵⑥: 도면 완료(draw+설계기준 통과) 시 '이 설계로 적산'으로 이어주는 실경로 링크.
              //   projectId를 경로에 실어 BimCostDashboard(projectId) 컨텍스트를 그대로 유지한다.
              costHref={`/${locale}/projects/${projectId}/cost`}
              designReady={hasDesignBasis}
            />
            {/* 하단 상태바 — 설계 산출 KPI(뷰포트 하단 고정). 대상 식별 지표는 상단 ContextHeader. */}
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

        {/* ── 우측 패널: 근거·한도(접이식) ──
            ★Pillar B 재정의: 종전엔 "분석 주소 1줄 + 순서 안내문"만 있어 폭 대비 정보밀도가 낮고,
            분석 주소는 상단 ContextHeader와 3중 중복이었다. 이제 패널을 '근거·한도'로 재정의해
            (1) 부지 실효 한도(건폐/용적/층수 + 법정상한/실효 근거·법령 링크), (2) 특이부지 경고 상시
            고정, (3) 다음 단계 CTA를 담는다 — 전부 기존 store 데이터 재배치(신규 API 없음). 좁은
            뷰포트에선 자동 접힘(F1)해 중앙 폭을 양보한다. Pillar D: dock과 동일하게 sticky-top. */}
        <aside
          className={[
            // ★리뷰 HIGH 수정: lg:top-3(0.75rem)는 전역 앱 헤더(DashboardChromeGate 'sticky
            //   top-2 z-[1000]', 실측 높이 80px)보다 얕아 스크롤 시 dock/panel 상단(라벨+접기
            //   토글+첫 카드)이 헤더 뒤로 가려져 토글 클릭이 불가능했다. 공용 오프셋
            //   var(--app-header-offset)(tokens.css SSOT·6.25rem=헤더 고정 시 하단경계
            //   5.5rem+여백 0.75rem)로 top·max-h를 함께 재정합(불일치 해소). calc() 내부는
            //   Tailwind 임의값 규칙상 공백을 _로 표기해야 유효 CSS로 컴파일된다(공백 없는
            //   calc(a-b)는 무효 선언으로 조용히 무시됨 — 브라우저 계산 확인).
            "flex shrink-0 flex-col overflow-hidden rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface)] shadow-[var(--shadow-sm)] lg:sticky lg:top-[var(--app-header-offset)] lg:self-start lg:max-h-[calc(100dvh_-_var(--app-header-offset)_-_1rem)]",
            panelOpen ? "w-full lg:w-[340px]" : "w-full lg:w-[3.25rem]",
          ].join(" ")}
        >
          <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2.5">
            {panelOpen && <span className="cc-label text-[10px] text-[var(--text-tertiary)]">{labels.panelTitle}</span>}
            <button
              type="button"
              onClick={togglePanel}
              aria-expanded={panelOpen}
              aria-label={panelOpen ? "근거·한도 패널 접기" : "근거·한도 패널 펼치기"}
              className="grid size-7 shrink-0 place-items-center rounded-[var(--r-input)] border border-[var(--line)] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
            >
              {panelOpen ? <ChevronRight className="size-4" aria-hidden /> : <ChevronLeft className="size-4" aria-hidden />}
            </button>
          </div>

          {panelOpen && (
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
              {/* 주소 불일치 경고 — 최우선 고정(스크린리더 즉시 경보). 그 외엔 실효 한도·근거를 보여준다. */}
              {hasAddressMismatch && (
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
              )}

              <LimitsPanel
                siteFar={siteFar}
                siteBcr={siteBcr}
                floorClamp={floorClamp}
                legalChips={legalChips}
                special={isSpecial ? special : null}
                mismatch={hasAddressMismatch}
                labels={labels}
              />

              {/* 다음 단계 CTA — 현재 상태에서 순서상 첫 미완료 단계로 이동(dock/흐름바와 동일 nextView). */}
              <PanelNextStep
                nextView={nextView}
                hasAddressMismatch={hasAddressMismatch}
                labels={labels}
                onGo={go}
              />
            </div>
          )}

          {!panelOpen && (
            <div className="hidden flex-1 items-start justify-center py-3 lg:flex">
              <ScrollText className="size-4 text-[var(--text-tertiary)]" aria-hidden />
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

/* ── dock 단계 사이 세로 진행선 — 이전 단계가 complete면 초록(진행 통과), 아니면 muted. ──
      node(size-9=36px) 중심 정렬: 카드 border(1) + px-3(12) + 반지름(18) = 31px → 2px선 중심 30px. */
function StepConnector({ filled }: { filled: boolean }) {
  return (
    <div aria-hidden className="flex py-0.5" style={{ paddingLeft: "1.875rem" }}>
      <span
        className="block h-4 w-0.5 rounded-full transition-colors"
        style={{ background: filled ? "var(--status-success)" : "var(--line)" }}
      />
    </div>
  );
}

/** PipelineState → 짧은 상태 낱말(dock 배지·흐름 바 공용). */
function stateWord(state: PipelineState, labels: Labels): string {
  switch (state) {
    case "complete":
      return labels.stateDone;
    case "loading":
      return labels.stateLoading;
    case "blocked":
      return labels.stateBlocked;
    default:
      return labels.stateReady;
  }
}

/** 현재 뷰가 blocked일 때 "왜"를 뷰포트 PipelineBlocker와 **동일한 근본원인 판정**(hasAddressMismatch)
 *  에서 파생한다(단일 소스). generate·draw는 PipelineBlocker가 실제로 쓰는 문구를 그대로 재사용해
 *  두 표면이 절대 다른 말을 하지 않도록 구조적으로 보장한다(리뷰 지적 #2 — sequentialNext 시절엔
 *  view==="site" 여부만 보고 문구를 골라 generate-blocked·!hasSiteBasis 케이스에서 "추천안을
 *  적용하라"는 오안내가 나갔다). site는 PipelineBlocker가 없고(콘텐츠 항상 렌더) 주소 불일치만이
 *  유일한 blocked 사유이므로 우측 패널의 addressMismatchDesc와 동일 문구를 공유한다. */
function blockedReasonHint(view: ViewKey, hasAddressMismatch: boolean, labels: Labels): string {
  if (view === "site") return labels.addressMismatchDesc;
  if (view === "generate") {
    return hasAddressMismatch ? labels.generateBlockDescMismatch : labels.generateBlockDescNoBasis;
  }
  // draw
  return hasAddressMismatch ? labels.drawBlockDescMismatch : labels.drawBlockDescNoBasis;
}

/* ── 흐름 진행 바 ── 뷰포트 하단, dock↔작업면을 잇는 "현재 위치 + 다음 액션" 스트립.
      좌: 3단계 가로 진행표시(실상태 dot·연결선) + 현재 단계·상태 낱말.
      우: 현재 단계 complete일 때만 '다음 단계' CTA 활성(무날조). 미완료면 정직 안내, 마지막 단계는 종료 안내.
      CTA 타깃은 부모가 dock 강조에도 쓰는 nextView(첫 미완료 단계) **하나만** 받는다 — 예전엔
      "현재 뷰의 순차 다음"(sequentialNext[view])을 따로 계산해, 완료된 프로젝트를 site 뷰로
      재진입하면(site·generate 둘 다 complete) CTA가 이미 끝난 generate를 다시 가리키면서 dock의
      nextView=draw 강조와 상충했다(리뷰 지적 #1 — 완료 프로젝트 재방문은 흔한 진입경로). */
function FlowAdvanceBar({
  view,
  states,
  views,
  nextView,
  hasAddressMismatch,
  showProgress,
  labels,
  onGo,
  costHref,
  designReady,
}: {
  view: ViewKey;
  states: Record<ViewKey, PipelineState>;
  views: { key: ViewKey; label: string; desc: string; icon: typeof MapPin }[];
  nextView: ViewKey;
  hasAddressMismatch: boolean;
  // ★Pillar A: 좌측 dock이 펼쳐져 파이프라인 레일이 이미 보이면 이 진행 dots는 중복 → 숨긴다.
  //   dock 접힘 시에만 true로 넘어와 컴팩트 진행 인디케이터로 표시(레일 단일화·중복 제거).
  showProgress: boolean;
  labels: Labels;
  onGo: (v: ViewKey) => void;
  // ★로드맵⑥: draw(마지막) 단계에서 노출할 '적산 실행' 실경로 링크 + 설계 준비 여부(hasDesignBasis).
  //   designReady일 때만 CTA를 켠다(무날조 — 설계 산출물이 실제 있을 때만 다음 단계 유도).
  costHref: string;
  designReady: boolean;
}) {
  const currentState = states[view];
  const currentLabel = views.find((v) => v.key === view)?.label ?? "";
  const currentDone = currentState === "complete";
  const currentIndex = views.findIndex((v) => v.key === view);

  // CTA 타깃 = dock과 동일한 nextView. 현재 뷰 자체가 곧 nextView면(아직 그 단계가 미완료) 더
  //   나아갈 곳이 없다는 뜻이므로 타깃 없음(null).
  const ctaTarget = nextView !== view ? nextView : null;
  const ctaTargetState = ctaTarget ? states[ctaTarget] : null;
  // 다음 CTA 라벨 — 타깃별(생성/도면). dock 라벨과 어휘를 구분해 접근성 이름 중복을 피한다.
  //   방어적 분기: nextView는 구조상 항상 미완료 단계를 가리키지만(현재 상태모델상 ctaTargetState는
  //   "complete"가 될 수 없음), 상태모델이 확장돼도(예: draw에 향후 "complete"가 추가돼도) CTA가
  //   이미 끝난 작업을 다시 "시작"하라고 오지시하지 않도록 이어보기/검토 문구로 분기해둔다.
  const ctaLabel =
    ctaTarget === null
      ? null
      : ctaTargetState === "complete"
        ? labels.flowReview
        : ctaTarget === "generate"
          ? labels.flowToGenerate
          : ctaTarget === "draw"
            ? labels.flowToDraw
            : null;
  // 미완료/차단/마지막 단계 안내 문구(정직). currentState==="blocked"면 뷰포트 블로커와 동일
  //   근본원인에서 파생한 문구를 최우선으로 쓴다(단일 소스 — 재발 방지). 그 외엔 **뷰 자체**로
  //   분기한다 — draw만 진짜 마지막 단계라 flowTerminal이고, site/generate는 ready(또는
  //   loading)여도 각자 선행요건 안내가 필요하다.
  //   ★리뷰 R2 회귀 수정: 예전엔 `ctaTarget===null`을 "terminal"의 기준으로 썼는데, ctaTarget은
  //   "현재 뷰가 곧 nextView(=아직 미완료인 최전선 단계)"일 때도 null이 된다. 그 결과 신규
  //   프로젝트의 기본 진입 뷰(site·ready)에서도, 부지확정 후 미생성 상태(generate·ready)에서도
  //   무조건 "마지막 단계 — 도면 편집"을 오표기했다(1단계인데 "마지막 단계" 날조). view==="draw"로
  //   직접 분기해 draw만 종료 문구를 쓰게 고정한다.
  const hint =
    currentState === "blocked"
      ? blockedReasonHint(view, hasAddressMismatch, labels)
      : view === "draw"
        ? labels.flowTerminal
        : view === "site"
          ? labels.flowHintNeedSite
          : labels.flowHintNeedDesign;

  return (
    <div className="flex min-h-[52px] flex-wrap items-center gap-x-4 gap-y-2 rounded-[var(--r-card)] border border-[var(--border-muted)] bg-[var(--surface)] px-3 py-2 shadow-[var(--shadow-sm)]">
      {/* 좌: 가로 진행표시 — 3단계 dot + 연결선(실상태). aria로 스크린리더에 현재/전체 위치 고지.
          ★Pillar A: dock 펼침 시엔 레일이 파이프라인을 이미 보여주므로 이 dots를 숨긴다(중복 제거).
          dock 접힘(showProgress) 때만 컴팩트 진행 인디케이터로 노출. */}
      {showProgress && (
        <div
          className="flex items-center"
          role="group"
          aria-label={`${labels.flowProgressAria} — ${currentLabel} (${currentIndex + 1}/${views.length})`}
        >
          {views.map((v, i) => {
            const s = states[v.key];
            const isCurrent = v.key === view;
            return (
              <Fragment key={v.key}>
                <span
                  className={[
                    "grid size-5 shrink-0 place-items-center rounded-full border text-[10px] font-black transition-colors",
                    isCurrent
                      ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)] ring-1 ring-[color-mix(in_srgb,var(--accent-strong)_35%,transparent)]"
                      : s === "complete"
                        ? "border-transparent bg-[var(--status-success)] text-white"
                        : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
                  ].join(" ")}
                  title={`${v.label} · ${stateWord(s, labels)}`}
                >
                  {s === "complete" && !isCurrent ? (
                    <CheckCircle2 className="size-3" aria-hidden />
                  ) : (
                    i + 1
                  )}
                </span>
                {i < views.length - 1 && (
                  <span
                    aria-hidden
                    className="mx-1 h-0.5 w-6 rounded-full transition-colors"
                    style={{ background: s === "complete" ? "var(--status-success)" : "var(--line)" }}
                  />
                )}
              </Fragment>
            );
          })}
        </div>
      )}

      {/* 현재 단계 낱말(상태색) */}
      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
        <span className="text-[var(--text-hint)]">{labels.flowNowLabel}</span>
        <span className="font-black text-[var(--text-primary)]">{currentLabel}</span>
        <span
          className={[
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold",
            currentState === "complete"
              ? "bg-[color-mix(in_srgb,var(--status-success)_14%,transparent)] text-[var(--status-success)]"
              : currentState === "blocked"
                ? "bg-[var(--surface-strong)] text-[var(--text-tertiary)]"
                : "bg-[var(--accent-soft)] text-[var(--accent-strong)]",
          ].join(" ")}
        >
          {currentState === "loading" && <Loader2 className="size-3 animate-spin" aria-hidden />}
          {stateWord(currentState, labels)}
        </span>
      </span>

      {/* 우: 다음 액션 CTA(완료 시) 또는 정직 안내(미완료·마지막). ★로드맵⑥: 마지막(draw) 단계라도
          설계 산출물이 준비되면(designReady) '이 설계로 적산 실행' 실경로 CTA + 흐름 안내를 노출해
          설계→적산→수지가 화면에서 끊기지 않게 한다. */}
      <div className="ml-auto flex min-w-0 items-center gap-3">
        {currentDone && ctaTarget && ctaLabel ? (
          <button
            type="button"
            onClick={() => onGo(ctaTarget)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-[var(--accent-strong)] px-3.5 py-1.5 text-[12px] font-bold text-white shadow-[var(--shadow-sm)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_88%,black)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)]"
          >
            <span className="text-[10px] font-black uppercase tracking-wider opacity-80">{labels.flowNextPrefix}</span>
            <span>{ctaLabel}</span>
            <ArrowRight className="size-4" aria-hidden />
          </button>
        ) : view === "draw" && designReady ? (
          <>
            {/* 흐름 안내(실경로만) — 설계 다음이 적산→수지임을 조용히 고지. 좁은 폭에선 숨김(CTA만). */}
            <span className="hidden truncate text-[11px] font-semibold text-[var(--text-hint)] sm:inline">
              {labels.flowNextChain}
            </span>
            <Link
              href={costHref}
              title={labels.flowToCost}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-[var(--accent-strong)] px-3.5 py-1.5 text-[12px] font-bold text-white shadow-[var(--shadow-sm)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_88%,black)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)]"
            >
              <Calculator className="size-4" aria-hidden />
              <span>{labels.flowToCost}</span>
              <ArrowRight className="size-4" aria-hidden />
            </Link>
          </>
        ) : (
          <span className="truncate text-[11px] font-semibold text-[var(--text-hint)]">{hint}</span>
        )}
      </div>
    </div>
  );
}

/* ── 우측 근거·한도 패널: 부지 실효 한도(건폐/용적/층수) + 법령 근거 + 특이부지 경고 ──
      전부 기존 store 데이터 재배치(신규 API 없음). 값은 공용 리졸버(resolveFar/BcrWithBasis)로
      "통합>실효>법정" 우선순위를 따르고, 법정상한/실효를 배지로 정직 구분한다(무날조: 없으면 "—"). */
function LimitsPanel({
  siteFar,
  siteBcr,
  floorClamp,
  legalChips,
  special,
  mismatch,
  labels,
}: {
  siteFar: { value: number; basis: LimitBasis } | null;
  siteBcr: { value: number; basis: LimitBasis } | null;
  floorClamp: number | null;
  legalChips: LegalRefChipInput[];
  special: { isSpecial: boolean; honest: string | null; factors: string[] } | null;
  mismatch: boolean;
  labels: Labels;
}) {
  // 주소 불일치 시 이 부지의 한도는 신뢰 불가(다른 주소 분석값) — 상단 배너가 사유를 이미 고지하므로
  //   값 표기는 생략한다(오도 방지·무날조).
  if (mismatch) return null;
  const hasLimits = !!siteFar || !!siteBcr;
  return (
    <div className="rounded-[var(--r-card)] border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <Ruler className="size-3.5 text-[var(--text-tertiary)]" aria-hidden />
        <span className="cc-label text-[10px] text-[var(--text-tertiary)]">{labels.limitsCardTitle}</span>
      </div>
      {hasLimits ? (
        <dl className="grid grid-cols-3 gap-2">
          <LimitCell label={labels.limitsBcr} tip={labels.limitsBcrTip} value={siteBcr ? `${siteBcr.value}%` : "—"} note={siteBcr ? limitBasisLabel(siteBcr.basis) : null} />
          <LimitCell label={labels.limitsFar} tip={labels.limitsFarTip} value={siteFar ? `${siteFar.value}%` : "—"} note={siteFar ? limitBasisLabel(siteFar.basis) : null} />
          <LimitCell label={labels.limitsFloors} value={floorClamp != null ? `${floorClamp}층` : labels.limitsFloorsPending} />
        </dl>
      ) : (
        <p className="text-[11px] leading-5 text-[var(--text-hint)]">{labels.limitsEmpty}</p>
      )}

      {/* 법령 근거 — evidence와 별개로 온 legalRefs를 칩으로 인라인화(있을 때만·무링크는 텍스트 폴백). */}
      {legalChips.length > 0 && (
        <div className="mt-2.5 border-t border-[var(--line)] pt-2.5">
          <p className="mb-1.5 flex items-center gap-1 text-[10px] font-bold text-[var(--text-tertiary)]">
            <ScrollText className="size-3" aria-hidden />
            {labels.legalRefsTitle}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {legalChips.map((r, i) => (
              <LegalRefChip key={i} lawName={r.lawName} article={r.article} title={r.title} url={r.url} />
            ))}
          </div>
        </div>
      )}

      {/* 특이부지 경고 상시 고정 — 콘솔 스크롤에 묻히지 않게 근거·한도 패널에 고정(무날조 honest 문구). */}
      {special?.isSpecial && (
        <div className="mt-2.5 rounded-[var(--r-input)] border border-[color-mix(in_srgb,var(--status-warning)_40%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-3 py-2">
          <p className="flex items-center gap-1 text-[11px] font-black text-[var(--status-warning)]">
            <AlertTriangle className="size-3.5" aria-hidden />
            {labels.specialWarnTitle}
          </p>
          {special.honest?.trim() && (
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">{special.honest.trim()}</p>
          )}
          {Array.isArray(special.factors) && special.factors.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[10px] text-[var(--text-tertiary)]">
              {special.factors.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/** 한도 셀 — 라벨(+ ⓘ 쉬운 설명 툴팁·F2) + 값(모노) + 근거 배지(법정상한/실효). */
function LimitCell({
  label,
  value,
  note,
  tip,
}: {
  label: string;
  value: string;
  note?: string | null;
  tip?: string;
}) {
  return (
    <div className="min-w-0 rounded-[var(--r-input)] border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5" title={tip}>
      <span className="flex items-center gap-0.5">
        <span className="cc-label text-[9px] text-[var(--text-tertiary)]">{label}</span>
        {tip && <Info className="size-2.5 shrink-0 text-[var(--text-hint)]" aria-hidden />}
      </span>
      <span className="cc-num block truncate text-sm text-[var(--text-primary)]">{value}</span>
      {note && <span className="block text-[9px] font-bold text-[var(--text-hint)]">{note}</span>}
    </div>
  );
}

/** 우측 패널 하단 '다음 단계' CTA — 순서상 첫 미완료 단계(nextView)로 이동. 버튼 라벨은 dock/흐름바
 *  CTA와 겹치지 않는 고유 문구(panelNextCta)를 써 접근성 이름 충돌을 피한다(다음 단계명은 텍스트로만). */
function PanelNextStep({
  nextView,
  hasAddressMismatch,
  labels,
  onGo,
}: {
  nextView: ViewKey;
  hasAddressMismatch: boolean;
  labels: Labels;
  onGo: (v: ViewKey) => void;
}) {
  if (hasAddressMismatch) return null; // 차단 상태에선 재분석이 먼저 — 진행 CTA 숨김.
  const nextLabel =
    nextView === "site" ? labels.viewSiteLabel : nextView === "generate" ? labels.viewGenerateLabel : labels.viewDrawLabel;
  return (
    <div className="rounded-[var(--r-card)] border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <p className="cc-label mb-1 text-[10px] text-[var(--text-tertiary)]">{labels.panelNextTitle}</p>
      <p className="mb-2 break-keep text-sm font-black text-[var(--text-primary)]">{nextLabel}</p>
      <button
        type="button"
        onClick={() => onGo(nextView)}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-[var(--r-input)] bg-[var(--accent-strong)] px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_88%,black)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)]"
      >
        <span>{labels.panelNextCta}</span>
        <ArrowRight className="size-4" aria-hidden />
      </button>
    </div>
  );
}

/* ── 준비 대시보드(Pillar C) — 잠긴 단계의 빈 자물쇠 화면을 대체.
      좌: 해제 요건 실시간 체크리스트(미충족 항목엔 바로가기 버튼). 우: 이 단계 산출물 '예시 구조'
      스켈레톤(정직 라벨 — 날조 아님). 요건이 모두 충족되면 부모 게이트가 실패널로 자동 교체된다. */
function ReadinessDashboard({
  stage,
  hasAddressMismatch,
  reqAddressOk,
  reqZoneOk,
  reqAreaOk,
  hasDesignBasis,
  labels,
  onGo,
}: {
  stage: "generate" | "draw";
  hasAddressMismatch: boolean;
  reqAddressOk: boolean;
  reqZoneOk: boolean;
  reqAreaOk: boolean;
  hasDesignBasis: boolean;
  labels: Labels;
  onGo: (v: ViewKey) => void;
}) {
  // 제목·설명 — 종전 PipelineBlocker 문구를 그대로 재사용(흐름바 hint와 단일 소스 유지 — 두 표면이
  //   같은 근본원인에서 파생돼 절대 다른 말을 하지 않는다). 무날조·무회귀.
  const title =
    stage === "generate"
      ? hasAddressMismatch
        ? labels.generateBlockTitleMismatch
        : labels.generateBlockTitleNoBasis
      : labels.drawBlockTitle;
  const description =
    stage === "generate"
      ? hasAddressMismatch
        ? labels.generateBlockDescMismatch
        : labels.generateBlockDescNoBasis
      : hasAddressMismatch
        ? labels.drawBlockDescMismatch
        : labels.drawBlockDescNoBasis;

  // 요건 항목 — generate: 부지 3요건(주소·용도지역·대지면적). draw: 부지 3요건 + 추천안 적용.
  //   미충족 항목엔 해당 단계로 이동하는 바로가기(부지 요건→site, 추천안→generate).
  const siteReqs: { key: string; label: string; ok: boolean; go: ViewKey }[] = [
    { key: "addr", label: labels.reqAddress, ok: reqAddressOk, go: "site" },
    { key: "zone", label: labels.reqZone, ok: reqZoneOk, go: "site" },
    { key: "area", label: labels.reqArea, ok: reqAreaOk, go: "site" },
  ];
  const reqs =
    stage === "generate"
      ? siteReqs
      : [...siteReqs, { key: "design", label: labels.reqDesign, ok: hasDesignBasis, go: "generate" as ViewKey }];

  return (
    // @container: 이 대시보드 실폭 기준으로 2열 분할(뷰포트 미디어쿼리 재도입 금지 — 컨테이너 쿼리 유지).
    <div
      className="@container cc-panel p-6 md:p-7"
      role="group"
      aria-label={title}
    >
      <div className="flex items-start gap-3">
        <div
          className="grid size-11 shrink-0 place-items-center rounded-full border border-[color-mix(in_srgb,var(--status-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_14%,transparent)] text-[var(--status-warning)]"
          aria-hidden
        >
          <LockKeyhole className="size-5" />
        </div>
        <div className="min-w-0">
          <h3 className="break-keep text-lg font-black text-[var(--text-primary)]">{title}</h3>
          <p className="mt-1 break-keep text-sm font-semibold leading-6 text-[var(--text-secondary)]">{description}</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 @2xl:grid-cols-2">
        {/* 해제 요건 체크리스트(실데이터·실시간) */}
        <div className="rounded-[var(--r-card)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <p className="cc-label mb-3 text-[10px] text-[var(--text-tertiary)]">{labels.readyChecklistTitle}</p>
          <ul className="space-y-2">
            {reqs.map((r) => (
              <li key={r.key} className="flex items-center gap-2.5">
                {r.ok ? (
                  <CheckCircle2 className="size-4 shrink-0 text-[var(--status-success)]" aria-hidden />
                ) : (
                  <CircleDashed className="size-4 shrink-0 text-[var(--text-tertiary)]" aria-hidden />
                )}
                <span
                  className={[
                    "min-w-0 flex-1 break-keep text-sm font-bold",
                    r.ok ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]",
                  ].join(" ")}
                >
                  {r.label}
                  <span className="sr-only">{r.ok ? ` — ${labels.reqMetLabel}` : ` — ${labels.reqUnmetLabel}`}</span>
                </span>
                {!r.ok && (
                  <button
                    type="button"
                    onClick={() => onGo(r.go)}
                    className="shrink-0 rounded-full border border-[color-mix(in_srgb,var(--accent-strong)_40%,transparent)] bg-[var(--accent-soft)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_15%,transparent)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color-mix(in_srgb,var(--accent-strong)_45%,transparent)]"
                  >
                    {r.go === "generate" ? labels.reqGoGenerate : labels.reqGoSite}
                  </button>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] leading-5 text-[var(--text-hint)]">{labels.readyUnlockHint}</p>
        </div>

        {/* 이 단계 산출물 '예시 구조' 미리보기 — 정직 라벨(날조 아님). aria-hidden(장식). */}
        <div className="rounded-[var(--r-card)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="cc-label text-[10px] text-[var(--text-tertiary)]">{labels.previewTitle}</span>
            <span className="rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">
              {labels.previewExampleBadge}
            </span>
          </div>
          <div aria-hidden className="space-y-2">
            {stage === "generate" ? <GenerateSkeleton /> : <DrawSkeleton />}
          </div>
          <p className="mt-3 text-[11px] leading-5 text-[var(--text-hint)]">{labels.previewHonest}</p>
        </div>
      </div>
    </div>
  );
}

/** 회색 스켈레톤 조각 — 예시 구조 미리보기용(무날조: 장식·aria-hidden). */
function Skel({ className = "" }: { className?: string }) {
  return <span className={`block rounded bg-[var(--surface-strong)] ${className}`} />;
}

/** 추천안(Top-N 개요) 예시 구조 — 카드 3장(제목바 + 본문 2줄 + 지표바). */
function GenerateSkeleton() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-[var(--r-input)] border border-[var(--line)] bg-[var(--surface)] p-3">
          <div className="flex items-center gap-2">
            <Building2 className="size-4 text-[var(--text-tertiary)]" aria-hidden />
            <Skel className="h-3 w-24" />
          </div>
          <Skel className="mt-2 h-2 w-full" />
          <Skel className="mt-1.5 h-2 w-2/3" />
        </div>
      ))}
    </>
  );
}

/** 도면 편집실 예시 구조 — 툴바 + 캔버스 박스. */
function DrawSkeleton() {
  return (
    <div className="rounded-[var(--r-input)] border border-[var(--line)] bg-[var(--surface)] p-3">
      <div className="flex items-center gap-1.5">
        <DraftingCompass className="size-4 text-[var(--text-tertiary)]" aria-hidden />
        <Skel className="h-2.5 w-10" />
        <Skel className="h-2.5 w-10" />
        <Skel className="h-2.5 w-10" />
      </div>
      <div className="mt-2 grid h-28 place-items-center rounded-[var(--r-input)] border border-dashed border-[var(--line)] bg-[var(--surface-muted)]">
        <Skel className="h-16 w-24" />
      </div>
    </div>
  );
}
