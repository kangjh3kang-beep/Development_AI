"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { DataSourceNotice } from "@/components/ui/DataSourceNotice";
import { RegulationHierarchyView, type RegResult } from "@/components/regulation/RegulationHierarchyView";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { parcelDataToRows, shouldSendParcels } from "@/lib/parcel-rows";
import { IntegratedParcelsBadge } from "@/components/common/IntegratedParcelsBadge";
import { resolveFarPct, resolveBcrPct } from "@/lib/zoning-ssot";
import type { Locale } from "@/i18n/config";

/* ── Response Types ── */

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type ComplianceCheckResponse = {
  address: string;
  zone_code: string;
  zone_name?: string;
  bcr_limit: number;
  bcr_planned: number;
  bcr_pass: boolean;
  far_limit: number;
  far_planned: number;
  far_pass: boolean;
  height_limit_m: number;
  height_planned_m: number;
  height_pass: boolean;
  overall_pass: boolean;
  // 백엔드가 미확인 용도지역 등에서 반환하는 상태 문자열 ("needs_verification" 등)
  overall_status?: string;
  remarks?: string;
  ai_analysis?: string;
};

// 규제 체크리스트(건축법 8항목): BuildingCodeRuleEngine.check_all 직렬화 응답.
type RuleCheckItem = {
  rule_id: string;
  rule_name: string;
  legal_basis: string;
  status: string; // pass / fail / warning / n/a
  required_value: string;
  actual_value: string;
  message: string;
};

type RuleCheckResponse = {
  zone_code?: string | null;
  zone_name?: string | null;
  overall_status: string; // pass / fail / warning
  pass_count: number;
  fail_count: number;
  warning_count: number;
  na_count: number;
  results: RuleCheckItem[];
  summary?: string | null;
};

/* ── Labels ── */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  contextTitle: string;
  contextHint: string;
  projectIdLabel: string;
  projectNameLabel: string;
  projectStatusLabel: string;
  projectUpdatedLabel: string;
  formTitle: string;
  addressLabel: string;
  zoneCodeLabel: string;
  plannedBcrLabel: string;
  plannedFarLabel: string;
  plannedHeightLabel: string;
  plannedFloorsLabel: string;
  submitAction: string;
  missingAddressError: string;
  missingZoneCodeError: string;
  complianceTitle: string;
  bcrLabel: string;
  farLabel: string;
  heightLabel: string;
  limitLabel: string;
  plannedLabel: string;
  passLabel: string;
  failLabel: string;
  // needs_verification 상태 전용 레이블 (미확인·확인필요)
  verifyLabel: string;
  overallLabel: string;
  regulationTitle: string;
  ruleCheckTitle: string;
  ruleCheckHint: string;
  ruleCheckEmpty: string;
  ruleCheckLoading: string;
  ruleLegalBasisLabel: string;
  ruleRequiredLabel: string;
  ruleActualLabel: string;
  ruleSummaryFmt: string;
  placeholder: string;
  autoLoading: string;
  autoMissingZone: string;
  limitsOnlyNote: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "법규 검토 라이브 작업 공간",
  heroDescription:
    "현재 프로젝트의 건축 법규 적합성을 실시간으로 검토합니다.",
  heroHint:
    "건폐율, 용적률, 높이 제한 등 건축 규제 사항을 API를 통해 자동 검증합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
  contextTitle: "프로젝트 컨텍스트",
  contextHint:
    "현재 라우트에서 프로젝트 ID를 가져옵니다. 주소와 용도지역은 제출 전 수정 가능합니다.",
  projectIdLabel: "프로젝트 ID",
  projectNameLabel: "프로젝트명",
  projectStatusLabel: "상태",
  projectUpdatedLabel: "최종 수정",
  formTitle: "법규 검토 입력",
  addressLabel: "주소",
  zoneCodeLabel: "용도지역 코드",
  plannedBcrLabel: "계획 건폐율 (%)",
  plannedFarLabel: "계획 용적률 (%)",
  plannedHeightLabel: "계획 높이 (m)",
  plannedFloorsLabel: "계획 층수",
  submitAction: "법규 검토 실행",
  missingAddressError: "주소를 입력해 주세요.",
  missingZoneCodeError: "용도지역 코드를 입력해 주세요.",
  complianceTitle: "건축 규제 검토 결과",
  bcrLabel: "건폐율",
  farLabel: "용적률",
  heightLabel: "높이 제한",
  limitLabel: "제한",
  plannedLabel: "계획",
  passLabel: "적합",
  failLabel: "부적합",
  verifyLabel: "미확인 · 확인 필요",
  overallLabel: "종합 판정",
  regulationTitle: "규제 체크리스트",
  ruleCheckTitle: "규제 체크리스트 (건축법 항목별)",
  ruleCheckHint:
    "건폐율·용적률·높이·건축선후퇴·주차·일조·피난방화·장애인편의 8개 항목을 관련 조항과 함께 검토합니다. 설계값이 없는 항목은 검토필요/해당없음으로 정직 표기합니다.",
  ruleCheckEmpty:
    "부지분석에서 용도지역이 확정되면 건축법 8개 항목 체크리스트가 자동으로 표시됩니다.",
  ruleCheckLoading: "건축법 8개 항목을 검토 중입니다...",
  ruleLegalBasisLabel: "관련 조항",
  ruleRequiredLabel: "기준",
  ruleActualLabel: "현재(계획)",
  ruleSummaryFmt: "적합 {pass} · 부적합 {fail} · 검토필요 {warning} · 해당없음 {na}",
  placeholder:
    "폼을 제출하면 건축 법규 적합성 검토 결과가 표시됩니다.",
  autoLoading: "용도지역 기준 법정 한도를 불러오는 중입니다...",
  autoMissingZone:
    "부지분석에서 용도지역이 확정되면 법정 한도가 자동으로 표시됩니다.",
  limitsOnlyNote:
    "용도지역 기준 법정 한도입니다. 계획값을 입력하고 검토를 실행하면 적합성까지 검증합니다.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러올 수 없습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 로드 실패",
  projectLoadErrorDetail:
    "라이브 API에서 프로젝트 컨텍스트를 가져오지 못했습니다. 재시도하여 자동 입력을 복원하세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Legal compliance live workspace",
  heroDescription:
    "Run a real-time building compliance check for the current project.",
  heroHint:
    "Automatically verifies BCR, FAR, height limits and other building regulations via API.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The project ID comes from the current route. Address and zone code can be adjusted before submission.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Compliance check input",
  addressLabel: "Address",
  zoneCodeLabel: "Zone code",
  plannedBcrLabel: "Planned BCR (%)",
  plannedFarLabel: "Planned FAR (%)",
  plannedHeightLabel: "Planned height (m)",
  plannedFloorsLabel: "Planned floors",
  submitAction: "Run compliance check",
  missingAddressError: "Address is required.",
  missingZoneCodeError: "Zone code is required.",
  complianceTitle: "Building compliance results",
  bcrLabel: "BCR",
  farLabel: "FAR",
  heightLabel: "Height limit",
  limitLabel: "Limit",
  plannedLabel: "Planned",
  passLabel: "Pass",
  failLabel: "Fail",
  verifyLabel: "Needs verification",
  overallLabel: "Overall result",
  regulationTitle: "Regulation checklist",
  ruleCheckTitle: "Regulation checklist (Building Act items)",
  ruleCheckHint:
    "Reviews 8 items (BCR, FAR, height, setback, parking, sunlight, evacuation/fire, accessibility) with their legal basis. Items without design values are honestly marked as review-needed / not-applicable.",
  ruleCheckEmpty:
    "The 8-item Building Act checklist appears automatically once the zone is confirmed in site analysis.",
  ruleCheckLoading: "Reviewing the 8 Building Act items...",
  ruleLegalBasisLabel: "Legal basis",
  ruleRequiredLabel: "Required",
  ruleActualLabel: "Actual (planned)",
  ruleSummaryFmt: "Pass {pass} · Fail {fail} · Review {warning} · N/A {na}",
  placeholder:
    "Submit the form to validate the building compliance check results.",
  autoLoading: "Loading statutory limits for the zone...",
  autoMissingZone:
    "Statutory limits will appear automatically once the zone is confirmed in site analysis.",
  limitsOnlyNote:
    "Statutory limits for the zone. Enter planned values and run the check to verify compliance.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore autofill.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Helpers ── */

function formatPercent(value: number) {
  return `${value.toFixed(1)}%`;
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

// 프로젝트 상태 코드 → 일반 한국어(영문은 원어). DB enum(draft/active/…)을 사용자 친화 표기로.
function projectStatusLabel(locale: string, status?: string | null): string {
  if (!status) return "-";
  const ko: Record<string, string> = {
    draft: "작성 중",
    active: "진행 중",
    in_progress: "진행 중",
    review: "검토 중",
    completed: "완료",
    done: "완료",
    archived: "보관됨",
    on_hold: "보류",
    cancelled: "취소됨",
    canceled: "취소됨",
  };
  const en: Record<string, string> = {
    draft: "Draft",
    active: "Active",
    in_progress: "In progress",
    review: "In review",
    completed: "Completed",
    done: "Completed",
    archived: "Archived",
    on_hold: "On hold",
    cancelled: "Cancelled",
    canceled: "Cancelled",
  };
  const key = status.toLowerCase();
  const map = locale.startsWith("ko") ? ko : en;
  return map[key] ?? status;
}

// rule-check status별 한글 라벨·색상(의미색 토큰). 가짜 pass 금지 — 백엔드 status 그대로 매핑.
// 상태 칩 계약: 상태색 10% 틴트 + 1px 보더(적합=success·부적합=error·검토필요=warning·해당없음=중립).
function ruleStatusMeta(status: string): { label: string; className: string } {
  const s = (status || "").toLowerCase();
  if (s === "pass") {
    return {
      label: "적합",
      className:
        "border border-[var(--status-success)]/25 bg-[var(--status-success)]/10 text-[var(--status-success)]",
    };
  }
  if (s === "fail") {
    return {
      label: "부적합",
      className:
        "border border-[var(--status-error)]/25 bg-[var(--status-error)]/10 text-[var(--status-error)]",
    };
  }
  if (s === "n/a" || s === "na") {
    return {
      label: "해당없음",
      className:
        "border border-[var(--border-muted)] bg-[var(--surface-soft)] text-[var(--text-tertiary)]",
    };
  }
  // warning 및 기타
  return {
    label: "검토필요",
    className:
      "border border-[var(--status-warning)]/25 bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
  };
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }
    return `API request failed with status ${error.status}.`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed.";
}

/* ── Component ── */

export function ProjectLegalWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const updateComplianceData = useProjectContextStore((s) => s.updateComplianceData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAutoLoading, setIsAutoLoading] = useState(false);
  const [limitsOnly, setLimitsOnly] = useState(false);
  const [complianceResult, setComplianceResult] =
    useState<ComplianceCheckResponse | null>(null);
  // 종합 규제 분석(/regulation/analyze) — 화면 주(主) 분석. 계층·정량·영향도·LLM 통합 해석.
  const [regResult, setRegResult] = useState<RegResult | null>(null);
  const [regLoading, setRegLoading] = useState(false);
  const [regError, setRegError] = useState("");
  const [regLlmGated, setRegLlmGated] = useState(false);
  // 규제 체크리스트(건축법 8항목, /building-compliance/rule-check) — 인증불필요·규칙기반.
  const [ruleResult, setRuleResult] = useState<RuleCheckResponse | null>(null);
  const [ruleLoading, setRuleLoading] = useState(false);
  const [ruleError, setRuleError] = useState("");
  // 자동 로드 1회 가드: 같은 (주소+용도지역) 조합엔 자동호출 1회만, 수동제출과 충돌 방지.
  const autoLoadedKeyRef = useRef<string | null>(null);
  const regLoadedKeyRef = useRef<string | null>(null);
  const ruleLoadedKeyRef = useRef<string | null>(null);
  const [form, setForm] = useState({
    address: "",
    zoneCode: "",
    plannedBcr: "",
    plannedFar: "",
    plannedHeight: "",
    plannedFloors: "",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "legal-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  useEffect(() => {
    if (!projectQuery.data) {
      return;
    }
    setForm((current) => ({
      ...current,
      address: current.address || projectQuery.data.address || "",
    }));
  }, [projectQuery.data]);

  // Pre-fill from site analysis + design context (capillary network)
  // ★SSOT 단일소비: 용도지역 코드/계획 건폐·용적은 부지분석(siteAnalysis) 컨텍스트에서 자동 채움.
  // - zoneCode: siteAnalysis.zoneCode(상단 배지 "제2종 60%·200%"와 동일 SSOT).
  //   (이전 검색의 form 기본값/제1종 잔존 방지 — SSOT 코드가 있으면 그것으로 채운다.)
  // - plannedBcr/plannedFar: 조례 실효한도(ordinance.effectiveBcr/Far, 없으면 siteAnalysis.effectiveBcrPct/FarPct)
  //   → 설계값(designData.bcr/far) 순. ordinance·실효값이 모두 없으면 기존 동작(공란) 유지.
  // 자동 채움 후에도 사용자가 직접 수정 가능(current 값이 있으면 덮어쓰지 않음).
  useEffect(() => {
    // ★SSOT 읽기 통일: ordinance 실효한도 1순위(가장 정밀한 조례 확정값) → 통합>실효>법정 헬퍼 폴백.
    //   다필지에서 ordinance.effectiveFar가 대표필지 기준으로 기록됐을 수 있으나, 법규 워크스페이스
    //   입력값은 사용자가 직접 수정 가능하므로 보수적으로 ordinance 1순위 유지.
    const ssotEffectiveBcr =
      siteAnalysis?.ordinance?.effectiveBcr ?? resolveBcrPct(siteAnalysis) ?? null;
    const ssotEffectiveFar =
      siteAnalysis?.ordinance?.effectiveFar ?? resolveFarPct(siteAnalysis) ?? null;
    setForm((current) => ({
      ...current,
      address: current.address || siteAnalysis?.address || "",
      zoneCode: current.zoneCode || siteAnalysis?.zoneCode || "",
      plannedBcr:
        current.plannedBcr ||
        (ssotEffectiveBcr != null
          ? String(ssotEffectiveBcr)
          : designData?.bcr
            ? String(designData.bcr)
            : ""),
      plannedFar:
        current.plannedFar ||
        (ssotEffectiveFar != null
          ? String(ssotEffectiveFar)
          : designData?.far
            ? String(designData.far)
            : ""),
      plannedFloors: current.plannedFloors || (designData?.floorCount ? String(designData.floorCount) : ""),
      plannedHeight:
        current.plannedHeight ||
        (designData?.floorCount
          ? String(Math.round(designData.floorCount * 3.3 * 10) / 10)
          : ""),
    }));
  }, [siteAnalysis, designData]);

  // 자동 로드 입력값: 부지분석 컨텍스트에서 확정된 용도지역·주소.
  const autoZoneCode = (siteAnalysis?.zoneCode ?? "").trim();
  const autoAddress = (siteAnalysis?.address ?? "").trim();

  // 자동 로드: 진입 시 용도지역+주소가 컨텍스트에 있고 라이브면, 계획값 0으로 보내
  // 법정 한도만 1회 자동 호출한다. 결과 있거나 진행 중이면 skip(중복가드).
  // 무목업 — 실패 시 graceful 에러만 표기. legal-check는 인증 불필요·규칙기반.
  useEffect(() => {
    if (!canUseLiveApi || !autoZoneCode || !autoAddress) {
      return;
    }
    const key = `${autoAddress}::${autoZoneCode}`;
    // 동일 조합 자동호출 1회만. 이미 결과/진행중/제출중이면 skip.
    if (autoLoadedKeyRef.current === key || complianceResult || isSubmitting) {
      return;
    }
    autoLoadedKeyRef.current = key;

    let cancelled = false;
    setWorkspaceError("");
    setIsAutoLoading(true);

    (async () => {
      try {
        const result = await apiClient.post<ComplianceCheckResponse>(
          "/building-compliance/legal-check",
          {
            useMock: false,
            body: {
              address: autoAddress,
              zone_code: autoZoneCode,
              planned_bcr: 0,
              planned_far: 0,
              planned_height_m: 0,
              planned_floors: 0,
            },
          },
        );
        if (cancelled) return;
        setComplianceResult(result);
        setLimitsOnly(true);
      } catch (error) {
        if (!cancelled) {
          // 실패 시 다음 변경에서 재시도 가능하도록 가드 해제.
          autoLoadedKeyRef.current = null;
          setWorkspaceError(extractErrorMessage(error, labels.authError));
        }
      } finally {
        if (!cancelled) {
          setIsAutoLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUseLiveApi, autoZoneCode, autoAddress]);

  // 종합 규제 분석 자동 로드: 부지분석 주소(용도지역 있으면 정확도↑)가 있으면 진입 시 1회 호출.
  // /regulation/analyze는 인증 불필요. use_llm:true로 먼저 시도, 402(잔액/구독)면 use_llm:false 재호출.
  // 무목업 — 실패 시 graceful 에러만 표기.
  useEffect(() => {
    if (!autoAddress) {
      return;
    }
    const key = `${autoAddress}::${autoZoneCode}`;
    if (regLoadedKeyRef.current === key || regResult || regLoading) {
      return;
    }
    regLoadedKeyRef.current = key;

    let cancelled = false;
    setRegError("");
    setRegLlmGated(false);
    setRegLoading(true);

    (async () => {
      // 다필지: 프로젝트 컨텍스트 필지(zoneCode 동반)로 통합 규제분석(면적가중 우세용도).
      const effRows = parcelDataToRows(siteAnalysis?.parcels);
      const reqBody = (useLlm: boolean) => ({
        address: autoAddress,
        pnu: (siteAnalysis?.pnu ?? "").trim() || undefined,
        use_llm: useLlm,
        ...(shouldSendParcels(effRows) ? { parcels: effRows } : {}),
      });
      try {
        let result: RegResult;
        try {
          result = await apiClient.post<RegResult>("/regulation/analyze", {
            useMock: false,
            timeoutMs: 120000,
            body: reqBody(true),
          });
        } catch (llmError) {
          // LLM 게이트(402): AI 통합 해석은 잔액/구독 필요. 계층·정량·영향도는 표시.
          if (llmError instanceof ApiClientError && llmError.status === 402) {
            if (!cancelled) setRegLlmGated(true);
            result = await apiClient.post<RegResult>("/regulation/analyze", {
              useMock: false,
              timeoutMs: 120000,
              body: reqBody(false),
            });
          } else {
            throw llmError;
          }
        }
        if (cancelled) return;
        setRegResult(result);
      } catch (error) {
        if (!cancelled) {
          // 실패 시 다음 변경에서 재시도 가능하도록 가드 해제.
          regLoadedKeyRef.current = null;
          setRegError(extractErrorMessage(error, labels.authError));
        }
      } finally {
        if (!cancelled) {
          setRegLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAddress, autoZoneCode]);

  // 규제 체크리스트 자동 로드: 부지분석 용도지역이 확정되면 진입 시 1회 호출.
  // /building-compliance/rule-check는 인증 불필요. 부지(용도지역·대지면적·조례한도)+설계(있으면)를
  // 전달하고, 설계값 없는 항목은 백엔드가 검토필요/해당없음으로 정직 반환(가짜 pass 없음).
  // 동일 (주소+용도지역) 조합당 1회만(무한루프 가드).
  useEffect(() => {
    if (!autoZoneCode) {
      return;
    }
    const key = `${autoAddress}::${autoZoneCode}`;
    if (ruleLoadedKeyRef.current === key || ruleResult || ruleLoading) {
      return;
    }
    ruleLoadedKeyRef.current = key;

    let cancelled = false;
    setRuleError("");
    setRuleLoading(true);

    const ordinance = siteAnalysis?.ordinance ?? null;
    const floorCount = designData?.floorCount ?? 0;
    (async () => {
      try {
        const result = await apiClient.post<RuleCheckResponse>(
          "/building-compliance/rule-check",
          {
            useMock: false,
            timeoutMs: 60000,
            body: {
              // 부지: 용도지역·대지면적·조례한도(있으면). 미입력은 백엔드가 zone_code로 보완.
              zone_code: autoZoneCode,
              // ★다필지면 통합 면적을 법규 검토 백엔드로 전송(대표값이면 건폐/용적 한도가 통합과 어긋남).
              land_area_sqm: effectiveLandAreaSqm(siteAnalysis) ?? 0,
              max_bcr: ordinance?.effectiveBcr ?? designData?.bcr ?? null,
              max_far: ordinance?.effectiveFar ?? designData?.far ?? null,
              // 설계: 컨텍스트에 있는 값만. 나머지는 백엔드 graceful(0).
              building_type: designData?.buildingType ?? undefined,
              total_gfa_sqm: designData?.totalGfaSqm ?? 0,
              floor_count_above: floorCount,
              building_height_m: floorCount ? floorCount * 3.3 : 0,
            },
          },
        );
        if (cancelled) return;
        setRuleResult(result);
      } catch (error) {
        if (!cancelled) {
          // 실패 시 다음 변경에서 재시도 가능하도록 가드 해제.
          ruleLoadedKeyRef.current = null;
          setRuleError(extractErrorMessage(error, labels.authError));
        }
      } finally {
        if (!cancelled) {
          setRuleLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAddress, autoZoneCode]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    const zoneCode = form.zoneCode.trim();

    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }
    if (!zoneCode) {
      setWorkspaceError(labels.missingZoneCodeError);
      return;
    }

    setIsSubmitting(true);

    try {
      const result = await apiClient.post<ComplianceCheckResponse>(
        "/building-compliance/legal-check",
        {
          useMock: false,
          body: {
            address,
            zone_code: zoneCode,
            planned_bcr: Number(form.plannedBcr) || 0,
            planned_far: Number(form.plannedFar) || 0,
            planned_height_m: Number(form.plannedHeight) || 0,
            planned_floors: Number(form.plannedFloors) || 0,
          },
        },
      );
      setComplianceResult(result);
      setLimitsOnly(false);

      // Update project context store (capillary network)
      const violations: string[] = [];
      if (!result.bcr_pass) violations.push("건폐율 초과");
      if (!result.far_pass) violations.push("용적률 초과");
      if (!result.height_pass) violations.push("높이제한 초과");
      updateComplianceData({
        bcrCompliant: result.bcr_pass,
        farCompliant: result.far_pass,
        heightCompliant: result.height_pass,
        violations,
      });
      markStageComplete("legal");
      addAnalysisResult({
        module: "legal",
        completedAt: new Date().toISOString(),
        summary: {
          overallPass: result.overall_pass,
          bcrPass: result.bcr_pass,
          farPass: result.far_pass,
          heightPass: result.height_pass,
        },
      });
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      {/* Hero */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[var(--accent-strong)]/10 px-4 py-2 label-caps text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
          {!canUseLiveApi && (
            <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
            )}
          {!canUseLiveApi ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.authError}
            </div>
          ) : null}
          {projectError ? (
            <div className="mt-6">
              <WorkspaceQueryErrorCard
                title={labels.projectLoadErrorTitle}
                description={labels.projectLoadErrorDetail}
                message={projectError}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void projectQuery.refetch();
                }}
              />
            </div>
          ) : null}
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 p-5 text-sm leading-7 text-[var(--status-warning)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Context + Form */}
      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="grid gap-3">
            <div>
              <p className="label-caps text-[var(--text-tertiary)]">
                {labels.contextTitle}
              </p>
              <CardTitle className="mt-2 text-xl">
                {labels.contextHint}
              </CardTitle>
            </div>
            {projectQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-28" />
            ) : (
              <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                <p className="label-caps text-[var(--text-tertiary)]">
                  {labels.projectIdLabel}
                </p>
                <p className="mt-2 break-all text-sm font-semibold text-[var(--text-primary)]">
                  {projectId}
                </p>
                <p className="mt-4 label-caps text-[var(--text-tertiary)]">
                  {labels.projectNameLabel}
                </p>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {projectQuery.data?.name ?? labels.projectFallback}
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <MetricTile
                    label={labels.projectStatusLabel}
                    value={projectStatusLabel(locale, projectQuery.data?.status)}
                  />
                  <MetricTile
                    label={labels.projectUpdatedLabel}
                    value={
                      projectQuery.data?.updated_at
                        ? formatDate(locale, projectQuery.data.updated_at)
                        : "-"
                    }
                  />
                </div>
              </div>
            )}
          </div>

          <Card className="bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="label-caps text-[var(--text-tertiary)]">
                {labels.formTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
                {/* 주소 입력창: 부지분석에서 주소가 확정된 프로젝트 진입 시엔 숨김(불필요 입력 제거).
                    신규(주소 미보유) 상태에서만 노출해 직접 입력 가능. SSOT 주소(siteAnalysis.address)는
                    위 useEffect로 form.address에 이미 자동 채워져 제출에 그대로 사용된다. */}
                {!siteAnalysis?.address ? (
                  <ProjectAddressInput
                    value={form.address}
                    onChange={(address) => setForm((current) => ({ ...current, address }))}
                    label={labels.addressLabel}
                    placeholder={labels.addressLabel}
                  />
                ) : null}
                <label className="block text-xs font-semibold text-[var(--text-secondary)]">
                  {labels.zoneCodeLabel}
                  <Input
                    className="mt-1"
                    value={form.zoneCode}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        zoneCode: event.target.value,
                      }))
                    }
                    placeholder={labels.zoneCodeLabel}
                  />
                </label>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block text-xs font-semibold text-[var(--text-secondary)]">
                    {labels.plannedBcrLabel}
                    <Input
                      className="mt-1"
                      type="number"
                      value={form.plannedBcr}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          plannedBcr: event.target.value,
                        }))
                      }
                      placeholder={labels.plannedBcrLabel}
                    />
                  </label>
                  <label className="block text-xs font-semibold text-[var(--text-secondary)]">
                    {labels.plannedFarLabel}
                    <Input
                      className="mt-1"
                      type="number"
                      value={form.plannedFar}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          plannedFar: event.target.value,
                        }))
                      }
                      placeholder={labels.plannedFarLabel}
                    />
                  </label>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block text-xs font-semibold text-[var(--text-secondary)]">
                    {labels.plannedHeightLabel}
                    <Input
                      className="mt-1"
                      type="number"
                      value={form.plannedHeight}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          plannedHeight: event.target.value,
                        }))
                      }
                      placeholder={labels.plannedHeightLabel}
                    />
                  </label>
                  <label className="block text-xs font-semibold text-[var(--text-secondary)]">
                    {labels.plannedFloorsLabel}
                    <Input
                      className="mt-1"
                      type="number"
                      value={form.plannedFloors}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          plannedFloors: event.target.value,
                        }))
                      }
                      placeholder={labels.plannedFloorsLabel}
                    />
                  </label>
                </div>
                <Button type="submit" disabled={!canUseLiveApi || isSubmitting}>
                  {isSubmitting
                    ? `${labels.submitAction}...`
                    : labels.submitAction}
                </Button>
              </form>
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      {/* Results */}
      <div className="grid grid-cols-1 gap-6 min-w-0">
        {/* 종합 규제 분석 (주 분석): 계층·정량 한도(법정 vs 조례 vs 실효)·영향도·LLM 통합 해석 */}
        <Card>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="label-caps text-[var(--text-tertiary)]">
                종합 규제 분석 (법령·조례·상/하위법령 + 항목별 이유·관련조항)
              </p>
              {regLlmGated ? (
                <span className="rounded-full border border-[var(--ai-accent)]/30 bg-[var(--ai-accent)]/10 px-2.5 py-0.5 text-[10px] font-bold text-[var(--ai-accent)]">
                  AI 통합 해석은 잔액/구독 필요
                </span>
              ) : null}
            </div>
            {regResult ? (
              <div className="mt-4 grid gap-6">
                {regResult.integrated && <IntegratedParcelsBadge integrated={regResult.integrated} />}
                <RegulationHierarchyView result={regResult} locale={locale} />
              </div>
            ) : regLoading ? (
              <div className="mt-4">
                <SkeletonLoader count={1} itemClassName="h-40" />
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  상위법령·도시계획·조례·개별 규제를 종합 분석 중입니다...
                </p>
              </div>
            ) : regError ? (
              <div className="mt-4 rounded-[var(--radius-xl)] border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 p-5 text-sm leading-7 text-[var(--status-warning)]">
                {regError}
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {autoAddress
                  ? "부지 주소를 기준으로 종합 규제 분석을 준비합니다."
                  : "부지분석에서 주소가 확정되면 적용 법령·조례·상/하위법령을 계층으로 종합 분석합니다."}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 규제 체크리스트 (건축법 8항목): 항목별 상태·관련조항·이유·기준/현재 */}
        <Card>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="label-caps text-[var(--text-tertiary)]">
                {labels.ruleCheckTitle}
              </p>
              {ruleResult ? (
                <span className="rounded-full border border-[var(--line-strong)] px-2.5 py-0.5 text-[10px] font-bold text-[var(--text-secondary)]">
                  {labels.ruleSummaryFmt
                    .replace("{pass}", String(ruleResult.pass_count))
                    .replace("{fail}", String(ruleResult.fail_count))
                    .replace("{warning}", String(ruleResult.warning_count))
                    .replace("{na}", String(ruleResult.na_count))}
                </span>
              ) : null}
            </div>
            <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.ruleCheckHint}
            </p>
            {ruleResult ? (
              <div className="mt-4 grid gap-3">
                {(ruleResult.results ?? []).map((item) => {
                  const meta = ruleStatusMeta(item.status);
                  return (
                    <div
                      key={item.rule_id}
                      className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {item.rule_name}
                        </p>
                        <span
                          className={`inline-block rounded-lg px-3 py-1 text-[10px] font-bold uppercase tracking-widest ${meta.className}`}
                        >
                          {meta.label}
                        </span>
                      </div>
                      {item.legal_basis ? (
                        <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                          {labels.ruleLegalBasisLabel}: {item.legal_basis}
                        </p>
                      ) : null}
                      {item.message ? (
                        <p className="mt-1.5 text-sm leading-7 text-[var(--text-secondary)]">
                          {item.message}
                        </p>
                      ) : null}
                      {item.required_value || item.actual_value ? (
                        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--text-secondary)]">
                          {item.required_value ? (
                            <span>
                              {labels.ruleRequiredLabel}:{" "}
                              <span className="font-semibold text-[var(--text-primary)]">
                                {item.required_value}
                              </span>
                            </span>
                          ) : null}
                          {item.actual_value ? (
                            <span>
                              {labels.ruleActualLabel}:{" "}
                              <span className="font-semibold text-[var(--text-primary)]">
                                {item.actual_value}
                              </span>
                            </span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : ruleLoading ? (
              <div className="mt-4">
                <SkeletonLoader count={1} itemClassName="h-40" />
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.ruleCheckLoading}
                </p>
              </div>
            ) : ruleError ? (
              <div className="mt-4 rounded-[var(--radius-xl)] border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 p-5 text-sm leading-7 text-[var(--status-warning)]">
                {ruleError}
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.ruleCheckEmpty}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Compliance Results (보조): 계획값 대조용 정량 적합성 */}
        <Card>
          <CardContent className="p-6">
            <p className="label-caps text-[var(--text-tertiary)]">
              {labels.complianceTitle} · 계획값 대조 (보조)
            </p>
            {complianceResult ? (
              <div className="mt-4 space-y-4">
                {limitsOnly ? (
                  <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-4 text-sm leading-7 text-[var(--text-secondary)]">
                    {labels.limitsOnlyNote}
                  </div>
                ) : null}
                <div className="grid gap-4 md:grid-cols-3">
                  <ComplianceMetric
                    label={labels.bcrLabel}
                    limit={formatPercent(complianceResult.bcr_limit)}
                    planned={formatPercent(complianceResult.bcr_planned)}
                    pass={complianceResult.bcr_pass}
                    passLabel={labels.passLabel}
                    failLabel={labels.failLabel}
                  />
                  <ComplianceMetric
                    label={labels.farLabel}
                    limit={formatPercent(complianceResult.far_limit)}
                    planned={formatPercent(complianceResult.far_planned)}
                    pass={complianceResult.far_pass}
                    passLabel={labels.passLabel}
                    failLabel={labels.failLabel}
                  />
                  <ComplianceMetric
                    label={labels.heightLabel}
                    limit={`${complianceResult.height_limit_m}m`}
                    planned={`${complianceResult.height_planned_m}m`}
                    pass={complianceResult.height_pass}
                    passLabel={labels.passLabel}
                    failLabel={labels.failLabel}
                  />
                </div>
                {(() => {
                  // 3-state 종합 판정(기존 데이터 매핑만): needs_verification→조건부(warning)·pass→적합(success)·fail→부적합(error).
                  // 판정값 대형(--font-display) + 상태색 보더/틴트. 수치·판정 생성 없음 — complianceResult 그대로 소비.
                  const needsVerify =
                    complianceResult.overall_status === "needs_verification";
                  const toneVar = needsVerify
                    ? "var(--status-warning)"
                    : complianceResult.overall_pass
                      ? "var(--status-success)"
                      : "var(--status-error)";
                  const verdictValue = needsVerify
                    ? labels.verifyLabel
                    : complianceResult.overall_pass
                      ? labels.passLabel
                      : labels.failLabel;
                  return (
                    <div
                      className="rounded-[var(--radius-xl)] border p-6"
                      style={{
                        borderColor: `color-mix(in srgb, ${toneVar} 35%, transparent)`,
                        background: `color-mix(in srgb, ${toneVar} 8%, transparent)`,
                      }}
                    >
                      <p className="label-caps text-[var(--text-tertiary)]">
                        {labels.overallLabel}
                      </p>
                      <p
                        className="mt-2 text-4xl font-black leading-tight"
                        style={{
                          fontFamily: "var(--font-display)",
                          color: toneVar,
                        }}
                      >
                        {verdictValue}
                      </p>
                      {needsVerify && complianceResult.remarks ? (
                        <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">
                          {complianceResult.remarks}
                        </p>
                      ) : null}
                    </div>
                  );
                })()}
                {complianceResult.ai_analysis ? (
                  <div className="rounded-[var(--radius-xl)] border border-[var(--ai-accent)]/25 bg-[var(--ai-accent)]/[0.06] p-5">
                    <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--ai-accent)]">
                      AI 통합 해석
                    </p>
                    <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {complianceResult.ai_analysis}
                    </p>
                  </div>
                ) : null}
              </div>
            ) : isAutoLoading ? (
              <div className="mt-4">
                <SkeletonLoader count={1} itemClassName="h-28" />
                <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.autoLoading}
                </p>
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {autoZoneCode ? labels.placeholder : labels.autoMissingZone}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 데이터 출처·고지 (DESIGN.md B1 공공데이터 고지 계약) — 자동 검토 참고용, 인허가청 최종 확정. */}
      <DataSourceNotice
        source="건축법·국토계획법 및 지자체 조례 (규칙기반 자동 검토)"
        note="자동 검토 참고용 · 실제 인허가 여부는 관할 인허가청이 최종 확정"
      />
    </section>
  );
}

/* ── Sub-components ── */

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="label-caps text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

function ComplianceMetric({
  label,
  limit,
  planned,
  pass,
  passLabel,
  failLabel,
}: {
  label: string;
  limit: string;
  planned: string;
  pass: boolean;
  passLabel: string;
  failLabel: string;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4 space-y-2">
      <p className="label-caps text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="text-sm text-[var(--text-secondary)]">
        {limit} / {planned}
      </p>
      <span
        className={`inline-block rounded-lg border px-3 py-1 text-[10px] font-bold uppercase tracking-widest ${
          pass
            ? "border-[var(--status-success)]/25 bg-[var(--status-success)]/10 text-[var(--status-success)]"
            : "border-[var(--status-error)]/25 bg-[var(--status-error)]/10 text-[var(--status-error)]"
        }`}
      >
        {pass ? passLabel : failLabel}
      </span>
    </div>
  );
}
