"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import {
  useAnalysisCache,
  analysisSignature,
  relativeKoreanTime,
} from "@/lib/use-analysis-cache";
import { AnalysisCacheStatus } from "@/components/common/AnalysisCacheStatus";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { NumberInput } from "@/components/common/NumberInput";
import { AutoZoningBadge } from "@/components/projects/AutoZoningBadge";
import { FieldSourceBadge } from "@/components/common/FieldSourceBadge";
import {
  EvidencePanel,
  type EvidenceItem,
} from "@/components/common/EvidencePanel";
import { dynamicMap } from "@/components/common/MapShell";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import type { Locale } from "@/i18n/config";

// 구획도 지도는 SSR 없이 동적 로드(SSR throw 차단 + 로딩 스켈레톤). 동작·props 불변.
const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 360, loadingMessage: "필지 구획도 로딩…" },
);

/* ── Response types ── */

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type AVMEstimateResponse = {
  id: string;
  project_id: string;
  estimated_price: number;
  price_per_sqm: number;
  confidence_score: number;
  comparable_count: number;
  model_version: string;
  comparables: Array<{
    address: string;
    price: number;
    area_sqm: number;
    transaction_date: string;
  }>;
  created_at: string;
};

/* ── 신뢰 메타데이터 타입(WP-D 가산·전부 옵셔널) ──
   구버전 백엔드(필드 부재)에서도 깨지지 않도록 모두 옵셔널로 둔다. url은 백엔드가
   검증한 값만 들어오며 프론트에서 조립하지 않는다(할루시네이션 링크 금지). */

/** 필드별 provenance — method=auto(자동)/estimated(추정)/user(수동) 등. */
type FieldProvenanceInput = {
  /** 출처 방식 (예: "auto", "estimated", "user", "manual"). */
  method?: string | null;
  /** 출처명/근거 한 줄 (예: "VWORLD 토지특성"). title 보조. */
  source?: string | null;
  /** 신뢰도 라벨(있으면 title에 부연). */
  confidence?: string | number | null;
  /** stamp 시각(epoch ms) — FieldSourceBadge title에 부연. */
  updated_at?: number | null;
};

/** 법령 원문링크 근거(레지스트리 get_legal_refs 출력) — url은 백엔드 제공값만. */
type LegalRef = {
  key?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string | null;
};

/** 수치 산출 트레이스 1건(EvidencePanel 항목 원천). */
type EvidenceTrace = {
  label?: string | null;
  value?: string | number | null;
  basis?: string | null;
  /** 이 항목과 연결할 법령 근거키(legal_refs[].key와 매칭해 url 주입). */
  legal_ref_key?: string | null;
};

type ParcelInfoResponse = {
  pnu: string;
  address: string;
  land_category: string;
  zoning: string;
  area_sqm: number;
  land_use_situation: string;
  official_price_per_sqm: number;
  road_side: string;
  terrain: string;
  restrictions: string[];
  /** WP-D 신뢰 메타데이터(가산·옵셔널) — 없으면(구버전) 렌더 생략. */
  inputs?: Record<string, FieldProvenanceInput> | null;
  evidence?: EvidenceTrace[] | null;
  legal_refs?: LegalRef[] | null;
};

/* ── Labels (Korean primary) ── */

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
  areaLabel: string;
  buildingAgeLabel: string;
  floorLabel: string;
  totalFloorsLabel: string;
  lawdCodeLabel: string;
  pnuLabel: string;
  submitAction: string;
  missingAddressError: string;
  missingAreaError: string;
  missingPnuError: string;
  avmTitle: string;
  avmAutoHint: string;
  autoMissingArea: string;
  autoLoading: string;
  avmEstimateLabel: string;
  avmUnitPriceLabel: string;
  avmConfidenceLabel: string;
  avmComparablesLabel: string;
  avmModelLabel: string;
  parcelTitle: string;
  parcelCategoryLabel: string;
  parcelZoningLabel: string;
  parcelAreaLabel: string;
  parcelUseSituationLabel: string;
  parcelOfficialPriceLabel: string;
  parcelRoadLabel: string;
  parcelTerrainLabel: string;
  parcelRestrictionsLabel: string;
  comparablesTitle: string;
  comparableAddressLabel: string;
  comparablePriceLabel: string;
  comparableAreaLabel: string;
  comparableDateLabel: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  retryAction: string;
};

const KO_LABELS: Labels = {
  heroTitle: "부지 분석",
  heroDescription:
    "주소를 입력하면 시세, 용도지역, 필지 정보를 자동으로 분석합니다.",
  heroHint: "",
  tokenHint: "",
  authError: "분석을 위해 로그인이 필요합니다.",
  contextTitle: "프로젝트 정보",
  contextHint: "주소와 면적을 입력하여 분석을 시작하세요.",
  projectIdLabel: "프로젝트 ID",
  projectNameLabel: "프로젝트명",
  projectStatusLabel: "상태",
  projectUpdatedLabel: "최근 수정일",
  formTitle: "부지 분석 입력",
  addressLabel: "주소",
  areaLabel: "면적 (㎡)",
  buildingAgeLabel: "건물 연식 (년)",
  floorLabel: "층",
  totalFloorsLabel: "총 층수",
  lawdCodeLabel: "법정동 코드",
  pnuLabel: "PNU (필지 고유번호)",
  submitAction: "부지 분석",
  missingAddressError: "주소는 필수 입력 항목입니다.",
  missingAreaError: "양수의 면적 값이 필요합니다.",
  missingPnuError: "PNU는 필지 정보 조회에 필수입니다.",
  avmTitle: "AVM 시세 추정 (ML 자동감정)",
  avmAutoHint: "주변 실거래(상단)와 별개의 머신러닝 자동감정 추정치입니다.",
  autoMissingArea:
    "면적 정보가 있으면 AVM 자동감정이 표시됩니다.",
  autoLoading: "AVM ML 자동감정을 분석하는 중입니다...",
  avmEstimateLabel: "추정 시세",
  avmUnitPriceLabel: "㎡당 단가",
  avmConfidenceLabel: "신뢰도",
  avmComparablesLabel: "비교사례 건수",
  avmModelLabel: "모델 버전",
  parcelTitle: "필지 정보",
  parcelCategoryLabel: "지목",
  parcelZoningLabel: "용도지역",
  parcelAreaLabel: "면적",
  parcelUseSituationLabel: "이용 상황",
  parcelOfficialPriceLabel: "공시지가 (㎡당)",
  parcelRoadLabel: "도로 접면",
  parcelTerrainLabel: "지형",
  parcelRestrictionsLabel: "규제사항",
  comparablesTitle: "비교 거래 사례",
  comparableAddressLabel: "주소",
  comparablePriceLabel: "거래가격",
  comparableAreaLabel: "면적",
  comparableDateLabel: "거래일",
  placeholder:
    "입력 양식을 제출하면 AVM 시세 추정 및 필지 정보가 표시됩니다.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 로드하지 못했습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 불가",
  projectLoadErrorDetail:
    "라이브 API에서 라우트 프로젝트 컨텍스트를 로드하지 못했습니다. 재시도하여 자동 입력과 메타데이터를 복원하세요.",
  retryAction: "재시도",
};

const EN_LABELS: Labels = {
  heroTitle: "Site analysis live workspace",
  heroDescription:
    "Run AVM valuation and parcel info queries for real-time site value analysis.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "The project id comes from the current route. Address and area can be adjusted before submission.",
  projectIdLabel: "Project ID",
  projectNameLabel: "Project name",
  projectStatusLabel: "Status",
  projectUpdatedLabel: "Updated",
  formTitle: "Site analysis input",
  addressLabel: "Address",
  areaLabel: "Area (sqm)",
  buildingAgeLabel: "Building age (years)",
  floorLabel: "Floor",
  totalFloorsLabel: "Total floors",
  lawdCodeLabel: "LAWD code",
  pnuLabel: "PNU (parcel ID)",
  submitAction: "Run site analysis",
  missingAddressError: "Address is required.",
  missingAreaError: "A positive area value is required.",
  missingPnuError: "PNU is required for parcel info lookup.",
  avmTitle: "AVM valuation (ML auto-appraisal)",
  avmAutoHint:
    "An ML auto-appraisal estimate, distinct from the nearby actual transactions shown above.",
  autoMissingArea:
    "AVM auto-appraisal will appear when land area is available.",
  autoLoading: "Running AVM ML auto-appraisal...",
  avmEstimateLabel: "Estimated price",
  avmUnitPriceLabel: "Price per sqm",
  avmConfidenceLabel: "Confidence",
  avmComparablesLabel: "Comparables",
  avmModelLabel: "Model version",
  parcelTitle: "Parcel information",
  parcelCategoryLabel: "Land category",
  parcelZoningLabel: "Zoning",
  parcelAreaLabel: "Area",
  parcelUseSituationLabel: "Land use",
  parcelOfficialPriceLabel: "Official price (per sqm)",
  parcelRoadLabel: "Road access",
  parcelTerrainLabel: "Terrain",
  parcelRestrictionsLabel: "Restrictions",
  comparablesTitle: "Comparable transactions",
  comparableAddressLabel: "Address",
  comparablePriceLabel: "Price",
  comparableAreaLabel: "Area",
  comparableDateLabel: "Date",
  placeholder:
    "Submit the form to view AVM estimates and parcel information.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore autofill and project metadata.",
  retryAction: "Retry",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── Formatters ── */

function formatCurrency(locale: string, value: number) {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }
    return `API 요청 실패: 상태 ${error.status}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "요청 실패.";
}

/* ── 신뢰 메타데이터 헬퍼(가산·순수함수) ── */

/** provenance method → FieldSourceBadge source.
 *  "user"/"manual"만 수동(user)으로, 그 외(auto/estimated/derived 등)는 자동(auto).
 *  FieldSourceBadge가 두 값만 받으므로 매핑한다. method 미상이면 null(미표시·정직). */
function provenanceToFieldSource(
  input?: FieldProvenanceInput | null,
): "auto" | "user" | null {
  if (!input || typeof input !== "object") return null;
  const method = (input.method ?? "").toString().trim().toLowerCase();
  if (!method) return null;
  if (method === "user" || method === "manual") return "user";
  // auto/estimated/derived/computed/api 등 파이프라인 산출 → 자동.
  return "auto";
}

/** legal_refs[]를 key로 인덱싱(법령 근거 url 주입용). 잘못된 항목은 건너뛴다. */
function indexLegalRefs(
  refs?: LegalRef[] | null,
): Record<string, LegalRef> {
  const map: Record<string, LegalRef> = {};
  for (const ref of refs ?? []) {
    if (ref && typeof ref.key === "string" && ref.key.trim()) {
      map[ref.key.trim()] = ref;
    }
  }
  return map;
}

/** SSOT 보존용 신뢰 메타데이터 — 부지분석 patch에 가산 저장(있을 때만).
 *  store(SiteAnalysisData) 타입은 이 키를 명명하지 않지만, updateSiteAnalysis가
 *  patch를 siteAnalysis에 스프레드·영속하므로 round-trip 보존된다(하위호환·additive). */
type SiteTrustMeta = {
  legalRefs?: LegalRef[];
  inputs?: Record<string, FieldProvenanceInput>;
};

/** 부지분석 patch에 신뢰 메타데이터를 가산한 객체를 만든다.
 *  trust 값이 모두 없으면 기존 patch를 그대로 반환(불필요 키 추가 방지·완전 하위호환).
 *  excess-property 검사를 피하려고 fresh literal이 아닌 변수로 구성해 반환한다. */
function withSiteTrustMeta(
  base: Partial<SiteAnalysisData>,
  trust?: { legalRefs?: LegalRef[] | null; inputs?: Record<string, FieldProvenanceInput> | null },
): Partial<SiteAnalysisData> {
  const legalRefs = trust?.legalRefs ?? null;
  const inputs = trust?.inputs ?? null;
  const hasLegal = Array.isArray(legalRefs) && legalRefs.length > 0;
  const hasInputs = !!inputs && Object.keys(inputs).length > 0;
  if (!hasLegal && !hasInputs) return base;
  const meta: SiteTrustMeta = {};
  if (hasLegal) meta.legalRefs = legalRefs as LegalRef[];
  if (hasInputs) meta.inputs = inputs as Record<string, FieldProvenanceInput>;
  // 변수로 구성(literal 아님) → Partial<SiteAnalysisData>로 좁혀 반환해도 trustMeta가 살아 영속된다.
  const merged: Partial<SiteAnalysisData> & { trustMeta: SiteTrustMeta } = {
    ...base,
    trustMeta: meta,
  };
  return merged;
}

/** evidence[] + legal_refs[]를 EvidencePanel 항목으로 결합.
 *  각 trace의 legal_ref_key를 legal_refs 인덱스와 매칭해 url(백엔드 제공값)을 주입한다.
 *  매칭 실패/부재 시 legalRef 생략(텍스트만) — 가짜 링크 금지. label 없는 항목은 제외. */
function buildEvidenceItems(
  evidence?: EvidenceTrace[] | null,
  legalRefs?: LegalRef[] | null,
): EvidenceItem[] {
  const traces = Array.isArray(evidence) ? evidence : [];
  if (traces.length === 0) return [];
  const refIndex = indexLegalRefs(legalRefs);
  const items: EvidenceItem[] = [];
  for (const trace of traces) {
    if (!trace || typeof trace !== "object") continue;
    const label = (trace.label ?? "").toString().trim();
    if (!label) continue;
    const value = trace.value ?? "—";
    const key = trace.legal_ref_key?.trim();
    const ref = key ? refIndex[key] : undefined;
    items.push({
      label,
      value: typeof value === "number" ? value : String(value),
      basis: trace.basis ?? null,
      legalRef:
        ref && typeof ref.law_name === "string" && ref.law_name.trim()
          ? {
              lawName: ref.law_name,
              article: ref.article,
              title: ref.title,
              url: ref.url,
            }
          : null,
    });
  }
  return items;
}

/* ── Component ── */

export function ProjectSiteAnalysisWorkspaceClient({
  locale,
  projectId,
  address,
  pnu,
  areaSqm,
}: {
  locale: Locale;
  projectId: string;
  /** auto 모드 — 상단 결과흐름이 확정한 주소가 주어지면 입력폼 없이 AVM 자동감정을 실행한다. */
  address?: string;
  pnu?: string;
  areaSqm?: number;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  // AVMRequest.project_id는 필수(UUID). 비-UUID 로컬 프로젝트는 백엔드 422 방지를 위해 호출 보류.
  const isUuidProject =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId);

  // auto 모드 판정: 상단 흐름이 넘긴 주소가 있으면 입력폼·Hero·필지지도 없이 카드만 렌더한다.
  const autoMode = Boolean(address && address.trim());
  const autoAddress = (address ?? "").trim();
  const autoPnu = (pnu ?? "").trim();
  const autoArea = typeof areaSqm === "number" && Number.isFinite(areaSqm) && areaSqm > 0
    ? areaSqm
    : null;

  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);
  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);
  const storeZoneCode = useProjectContextStore((s) => s.siteAnalysis?.zoneCode ?? null);

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAutoLoading, setIsAutoLoading] = useState(false);
  const [avmResult, setAvmResult] = useState<AVMEstimateResponse | null>(null);
  const [parcelResult, setParcelResult] = useState<ParcelInfoResponse | null>(
    null,
  );

  // 영속 캐시: 주소·PNU·면적 불변이면 검증된 AVM·필지 결과 재사용(매 방문 재호출 방지),
  // 입력이 바뀌면 재분석 제안. auto 모드 자동호출을 캐시로 게이팅한다.
  const avmSignature = analysisSignature(autoAddress, autoPnu, autoArea);
  const {
    cached: avmCached,
    isFresh: avmFresh,
    isStale: avmStale,
    at: avmAt,
    save: saveAvm,
  } = useAnalysisCache<{ avm: AVMEstimateResponse; parcel: ParcelInfoResponse | null }>(
    "avm",
    avmSignature,
  );
  const [avmForceRun, setAvmForceRun] = useState(0);
  const [form, setForm] = useState<{
    address: string;
    areaSqm: number | null;
    buildingAgeYears: string;
    floor: string;
    totalFloors: string;
    lawdCd: string;
    pnu: string;
  }>({
    address: "",
    areaSqm: null,
    buildingAgeYears: "5",
    floor: "1",
    totalFloors: "5",
    lawdCd: "",
    pnu: "",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "site-analysis-live"],
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
      areaSqm:
        current.areaSqm ??
        (projectQuery.data.total_area_sqm != null
          ? projectQuery.data.total_area_sqm
          : null),
    }));
  }, [projectQuery.data]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";

  // 결과 카드 플레이스홀더: auto 모드에선 로딩/안내, 수동 모드에선 폼 제출 안내.
  const resultPlaceholder = autoMode
    ? autoArea
      ? labels.autoLoading
      : labels.autoMissingArea
    : labels.placeholder;

  // ── 신뢰 메타데이터(WP-D 가산·옵셔널) 파생 ──
  // 필드 provenance(inputs{}) → FieldSourceBadge, 산출 트레이스(evidence[]) → EvidencePanel.
  // 모두 옵셔널 가드 — 구버전 백엔드(필드 부재)에선 빈 값이 되어 렌더 생략된다.
  const parcelInputs = parcelResult?.inputs ?? null;
  const evidenceItems = buildEvidenceItems(
    parcelResult?.evidence,
    parcelResult?.legal_refs,
  );
  // 필드 키 → FieldSourceBadge 노드(없으면 undefined → MetricTile에서 미표시).
  const fieldBadge = (key: string): React.ReactNode => {
    const input = parcelInputs?.[key];
    const source = provenanceToFieldSource(input);
    if (!source) return undefined;
    const at =
      input && typeof input.updated_at === "number" && Number.isFinite(input.updated_at)
        ? input.updated_at
        : undefined;
    return <FieldSourceBadge source={source} updatedAt={at} />;
  };

  // auto 모드: 상단 흐름이 확정한 주소(+면적/PNU)로 AVM ML 자동감정·필지정보를 자동 호출한다.
  // 면적이 없으면 호출 보류(정직 안내). 무목업 — 실패 시 graceful 에러만 표기.
  useEffect(() => {
    if (!autoMode || !canUseLiveApi || !autoArea || !isUuidProject) {
      return;
    }
    // 캐시 신선(입력 불변) & 강제재실행 아님 → 검증된 결과 즉시 재사용, 네트워크 호출 생략.
    if (avmForceRun === 0 && avmFresh && avmCached?.avm) {
      setAvmResult(avmCached.avm);
      setParcelResult(avmCached.parcel ?? null);
      setIsAutoLoading(false);
      return;
    }
    let cancelled = false;
    setWorkspaceError("");
    setIsAutoLoading(true);

    (async () => {
      try {
        const avm = await apiClient.post<AVMEstimateResponse>("/avm/estimate", {
          useMock: false,
          body: {
            project_id: projectId,
            address: autoAddress,
            area_sqm: autoArea,
            pnu: autoPnu || undefined,
          },
        });
        if (cancelled) return;
        setAvmResult(avm);

        let parcelZoning: string | null = null;
        let parcelData: ParcelInfoResponse | null = null;
        // PNU가 없어도 주소로 지오코딩 폴백되도록 address도 함께 전달(필지정보 누락 해소).
        if (autoPnu || autoAddress) {
          const parcel = await apiClient.post<ParcelInfoResponse>(
            "/external/parcel/info",
            {
              useMock: false,
              body: { pnu: autoPnu || undefined, address: autoAddress || undefined },
            },
          );
          if (cancelled) return;
          parcelData = parcel;
          setParcelResult(parcel);
          parcelZoning = parcel.zoning || null;
        }
        // 검증된 결과 영속 → 재방문 시 재사용(입력 불변이면 재호출 안 함)
        saveAvm({ avm, parcel: parcelData });

        // 신뢰 메타데이터(legal_refs/inputs)를 SSOT에 가산 보존(있을 때만). 없으면 기존 patch 그대로.
        updateSiteAnalysis(
          withSiteTrustMeta(
            {
              estimatedValue: avm.estimated_price,
              landAreaSqm: autoArea,
              zoneCode: parcelZoning,
              address: autoAddress,
              pnu: autoPnu || null,
            },
            {
              legalRefs: parcelData?.legal_refs,
              inputs: parcelData?.inputs,
            },
          ),
        );
        addAnalysisResult({
          module: "site-analysis",
          completedAt: new Date().toISOString(),
          summary: {
            estimatedPrice: avm.estimated_price,
            confidence: avm.confidence_score,
            address: autoAddress,
          },
        });
      } catch (error) {
        if (!cancelled) {
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
  }, [autoMode, canUseLiveApi, autoAddress, autoPnu, autoArea, avmForceRun]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    const address = form.address.trim();
    const areaSqm = form.areaSqm ?? 0;
    const pnu = form.pnu.trim();

    if (!address) {
      setWorkspaceError(labels.missingAddressError);
      return;
    }
    if (!Number.isFinite(areaSqm) || areaSqm <= 0) {
      setWorkspaceError(labels.missingAreaError);
      return;
    }

    setIsSubmitting(true);

    try {
      const avm = await apiClient.post<AVMEstimateResponse>("/avm/estimate", {
        useMock: false,
        body: {
          project_id: projectId,
          address,
          area_sqm: areaSqm,
          building_age_years: Number(form.buildingAgeYears) || undefined,
          floor: Number(form.floor) || undefined,
          total_floors: Number(form.totalFloors) || undefined,
          lawd_cd: form.lawdCd.trim() || undefined,
          pnu: pnu || undefined,
        },
      });
      setAvmResult(avm);

      let parcelZoning: string | null = null;
      let parcelData: ParcelInfoResponse | null = null;
      if (pnu || address) {
        const parcel = await apiClient.post<ParcelInfoResponse>(
          "/external/parcel/info",
          {
            useMock: false,
            body: { pnu: pnu || undefined, address: address || undefined },
          },
        );
        parcelData = parcel;
        setParcelResult(parcel);
        parcelZoning = parcel.zoning || null;
      }

      // Update project context store (capillary network)
      // 신뢰 메타데이터(legal_refs/inputs)를 SSOT에 가산 보존(있을 때만). 없으면 기존 patch 그대로.
      updateSiteAnalysis(
        withSiteTrustMeta(
          {
            estimatedValue: avm.estimated_price,
            landAreaSqm: areaSqm,
            zoneCode: parcelZoning,
            address,
            pnu: pnu || null,
          },
          {
            legalRefs: parcelData?.legal_refs,
            inputs: parcelData?.inputs,
          },
        ),
      );
      markStageComplete("site-analysis");
      addAnalysisResult({
        module: "site-analysis",
        completedAt: new Date().toISOString(),
        summary: {
          estimatedPrice: avm.estimated_price,
          confidence: avm.confidence_score,
          address,
        },
      });
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="grid gap-6">
      {/* auto 모드: 입력폼·Hero·필지지도 없이 상태 안내 + AVM/필지/비교거래 카드만 렌더 */}
      {autoMode ? (
        <>
          {!autoArea ? (
            <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.autoMissingArea}
            </div>
          ) : null}
          {isAutoLoading ? (
            <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.autoLoading}
            </div>
          ) : null}
          {workspaceError ? (
            <div className="rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </>
      ) : (
        <>
      {/* Hero */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
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
          <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
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
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
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
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
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
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.projectIdLabel}
                </p>
                <p className="mt-2 break-all text-sm font-semibold text-[var(--text-primary)]">
                  {projectId}
                </p>
                <p className="mt-4 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.projectNameLabel}
                </p>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {projectQuery.data?.name ?? labels.projectFallback}
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <MetricTile
                    label={labels.projectStatusLabel}
                    value={projectQuery.data?.status ?? "-"}
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
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.formTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
                <GlobalAddressSearch
                  single
                  onChange={(entries) => {
                    if (entries.length > 0) {
                      setForm((current) => ({ ...current, address: entries[0].fullAddress }));
                    }
                  }}
                  placeholder={labels.addressLabel}
                />
                <div className="grid gap-3 md:grid-cols-2">
                  <NumberInput
                    allowDecimal
                    value={form.areaSqm}
                    onChange={(n) =>
                      setForm((current) => ({
                        ...current,
                        areaSqm: n,
                      }))
                    }
                    placeholder={labels.areaLabel}
                    className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                  />
                  <Input
                    value={form.pnu}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        pnu: event.target.value,
                      }))
                    }
                    placeholder={labels.pnuLabel}
                  />
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <Input
                    type="number"
                    value={form.buildingAgeYears}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        buildingAgeYears: event.target.value,
                      }))
                    }
                    placeholder={labels.buildingAgeLabel}
                  />
                  <Input
                    type="number"
                    value={form.floor}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        floor: event.target.value,
                      }))
                    }
                    placeholder={labels.floorLabel}
                  />
                  <Input
                    type="number"
                    value={form.totalFloors}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        totalFloors: event.target.value,
                      }))
                    }
                    placeholder={labels.totalFloorsLabel}
                  />
                </div>
                <Input
                  value={form.lawdCd}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      lawdCd: event.target.value,
                    }))
                  }
                  placeholder={labels.lawdCodeLabel}
                />
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

      {/* Auto-Zoning Badge */}
      {form.address.trim().length >= 3 && (
        <Card>
          <CardContent className="p-6">
            <p className="mb-3 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {locale === "en" ? "Auto-detected zoning" : "자동 용도지역 감지"}
            </p>
            <AutoZoningBadge address={form.address} />
          </CardContent>
        </Card>
      )}

      {/* 필지 구획도 (경계·용도지역·면적) */}
      {form.address.trim().length >= 3 && <ParcelBoundaryMap parcels={[form.address.trim()]} primaryZone={storeZoneCode ?? undefined} />}
        </>
      )}

      {/* Results */}
      <div className="grid gap-6 xl:grid-cols-2">
        {/* AVM Valuation */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.avmTitle}
            </p>
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
              {labels.avmAutoHint}
            </p>
            {autoMode && (
              <AnalysisCacheStatus
                isFresh={avmFresh && !!avmResult}
                isStale={avmStale && !!avmResult}
                at={avmAt}
                relativeLabel={relativeKoreanTime(avmAt)}
                onRerun={() => setAvmForceRun((n) => n + 1)}
                busy={isAutoLoading}
                rerunLabel="↻ 재감정"
              />
            )}
            {avmResult ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <MetricTile
                  label={labels.avmEstimateLabel}
                  value={formatCurrency(locale, avmResult.estimated_price)}
                />
                <MetricTile
                  label={labels.avmUnitPriceLabel}
                  value={formatCurrency(locale, avmResult.price_per_sqm)}
                />
                <MetricTile
                  label={labels.avmConfidenceLabel}
                  value={formatPercent(avmResult.confidence_score)}
                />
                <MetricTile
                  label={labels.avmComparablesLabel}
                  value={String(avmResult.comparable_count)}
                />
                <MetricTile
                  label={labels.avmModelLabel}
                  value={avmResult.model_version}
                />
                <MetricTile
                  label={labels.projectUpdatedLabel}
                  value={formatDate(locale, avmResult.created_at)}
                />
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {resultPlaceholder}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Parcel Info */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.parcelTitle}
            </p>
            {parcelResult ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MetricTile
                    label={labels.parcelCategoryLabel}
                    value={parcelResult.land_category}
                    badge={fieldBadge("land_category")}
                  />
                  <MetricTile
                    label={labels.parcelZoningLabel}
                    value={parcelResult.zoning}
                    badge={fieldBadge("zoning")}
                  />
                  <MetricTile
                    label={labels.parcelAreaLabel}
                    value={parcelResult.area_sqm != null && Number.isFinite(parcelResult.area_sqm) ? `${parcelResult.area_sqm.toLocaleString()} m2` : "—"}
                    badge={fieldBadge("area_sqm")}
                  />
                  <MetricTile
                    label={labels.parcelUseSituationLabel}
                    value={parcelResult.land_use_situation}
                  />
                  <MetricTile
                    label={labels.parcelOfficialPriceLabel}
                    value={formatCurrency(
                      locale,
                      parcelResult.official_price_per_sqm,
                    )}
                    badge={fieldBadge("official_price_per_sqm")}
                  />
                  <MetricTile
                    label={labels.parcelRoadLabel}
                    value={parcelResult.road_side}
                  />
                  <MetricTile
                    label={labels.parcelTerrainLabel}
                    value={parcelResult.terrain}
                  />
                </div>
                {/* 산출 근거(WP-D evidence[] + legal_refs[]) — 항목이 없으면(구버전) 자동 미표시.
                    EvidencePanel 내부에서 빈 items면 렌더하지 않으므로 추가 가드 불필요. */}
                <EvidencePanel items={evidenceItems} />
                {parcelResult.restrictions?.length > 0 && (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.parcelRestrictionsLabel}
                    </p>
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {(parcelResult.restrictions ?? []).map((r, i) => (
                        <li key={`restriction-${i}`}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {resultPlaceholder}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Comparable Transactions */}
      {avmResult && avmResult.comparables && avmResult.comparables?.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.comparablesTitle}
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)]">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparableAddressLabel}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparablePriceLabel}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparableAreaLabel}
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                      {labels.comparableDateLabel}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(avmResult.comparables ?? []).map((comp, i) => (
                    <tr
                      key={`comp-${i}`}
                      className="border-b border-[var(--line)] last:border-0"
                    >
                      <td className="px-4 py-3 text-[var(--text-primary)]">
                        {comp.address}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-[var(--text-primary)]">
                        {formatCurrency(locale, comp.price)}
                      </td>
                      <td className="px-4 py-3 text-right text-[var(--text-secondary)]">
                        {comp.area_sqm != null && Number.isFinite(comp.area_sqm) ? `${comp.area_sqm.toLocaleString()} m2` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right text-[var(--text-secondary)]">
                        {comp.transaction_date}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}

/* ── MetricTile ── */

function MetricTile({
  label,
  value,
  badge,
}: {
  label: string;
  value: string;
  /** 옵셔널 출처 배지(FieldSourceBadge 등) — 라벨 옆에 표시. 기존 호출은 미전달(무변경). */
  badge?: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="flex items-center gap-1.5 text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
        {badge}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
