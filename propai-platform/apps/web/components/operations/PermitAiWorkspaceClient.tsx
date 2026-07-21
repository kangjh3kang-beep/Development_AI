"use client";

/**
 * 인.허가분석 자동화 — AI 인허가 분석 시스템.
 *
 * 부지분석(용도지역·건폐율/용적률·면적) + 지자체 조례 + 상위법령을 종합하여
 * LLM(Claude)이 개발방식별 인허가 가능성·근거법령·문제점·해결방안을 분석한다.
 * 주소는 ProjectAddressInput으로 (1) 프로젝트 선택 (2) 카카오 검색 (3) 변경/추가 입력 모두 지원.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Bot, CheckCircle2, ClipboardList, FileDown, Pin, Puzzle } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { dynamicMap } from "@/components/common/MapShell";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import { SolarEnvelopeCard } from "@/components/projects/SolarEnvelopeCard";
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";

// 구획도 지도는 SSR 없이 동적 로드(SSR throw 차단 + 로딩 스켈레톤). 동작·props 불변.
const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 360, loadingMessage: "필지 구획도 로딩…" },
);
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { AnalysisHistoryCard } from "@/components/common/AnalysisHistoryCard";
import { optionsSummary } from "@/lib/use-analysis-history";
import { AnalysisVerdict } from "@/components/analysis/AnalysisVerdict";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { RegistryBulkButton } from "@/components/common/RegistryBulkButton";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { buildAnalysisParcelAddrs } from "@/lib/parcel-rows";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { DEVELOPABILITY_LABEL, resolveFarPct, resolveBcrPct, specialFactorLabels } from "@/lib/zoning-ssot";
import type { Locale } from "@/i18n/config";

type MethodResult = {
  method: string;
  possibility: "상" | "중" | "하" | string;
  score: number;
  key_laws: string[];
  issues: string[];
  solutions: string[];
};

type ParcelInfo = {
  address: string;
  zone_type?: string | null;
  max_far?: number | null;
  max_bcr?: number | null;
  land_area_sqm?: number | null;
};

type MultiParcel = {
  ai?: boolean;
  parcels: ParcelInfo[];
  blended_far?: number | null;
  optimal_far?: number | null;
  max_far?: number | null;
  far_rationale?: string;
  far_key_laws?: string[];
  integration_issues?: string[];
  integration_solutions?: string[];
};

// 특이부지 게이트(가산·옵셔널) — 백엔드 permit_analysis_service가 detect_special_parcel 결과를
// result.site.special_parcel에 그대로 실어보낸다(is_special일 때만 객체, 일상부지는 null).
// AutoZoningBadge/LandIntelligencePanel의 확립된 특이부지 게이트 타입과 동형(읽기 소비).
type SpecialParcel = {
  is_special?: boolean | null;
  developability?: string | null; // POSSIBLE|CAUTION|CONDITIONAL|PRECONDITION|BLOCKED
  resolvable?: string | null; // YES|CONDITIONAL|NO
  severity_label?: string | null;
  factors?: Array<{ category?: string | null } | string> | null;
  honest_disclosure?: string | null;
};

type PermitAnalysis = {
  ai?: boolean;
  summary: string;
  methods: MethodResult[];
  recommendation: string;
  site?: {
    address?: string;
    zone_type?: string | null;
    max_bcr?: number | null;
    max_far?: number | null;
    land_area_sqm?: number | null;
    // 특이부지 게이트(가산) — null이면 일상부지(미표시). 가짜 생성 금지.
    special_parcel?: SpecialParcel | null;
  };
  multi_parcel?: MultiParcel;
};

// 특이부지 게이트 중 '주의 환기가 필요한' 개발가능성(법정한도가 그대로 실현되지 않음).
// 이 등급이면 시나리오/추천 표시에 특이부지 경고 prefix를 단다(AutoZoningBadge와 일관).
const GATED_DEVELOPABILITY = new Set(["BLOCKED", "PRECONDITION", "CONDITIONAL", "RESTRICTED", "CAUTION"]);

// 인허가 가능성 → 상태색(토큰). 하드코딩 색 금지 — color-mix로 표면/보더 파생.
const POSSIBILITY_STYLE: Record<string, string> = {
  상: "border-[var(--status-success)]/30 bg-[color-mix(in_srgb,var(--status-success)_15%,transparent)] text-[var(--status-success)]",
  중: "border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_15%,transparent)] text-[var(--status-warning)]",
  하: "border-[var(--status-error)]/30 bg-[color-mix(in_srgb,var(--status-error)_15%,transparent)] text-[var(--status-error)]",
};

export function PermitAiWorkspaceClient({ locale: _locale }: { locale: Locale }) {
  // 활성 프로젝트(projectId)가 있을 때만 컨텍스트 부지정보 사용 — 약식 검색 누수 차단.
  const _projectId = useProjectContextStore((s) => s.projectId);
  const _rawSite = useProjectContextStore((s) => s.siteAnalysis);
  const siteAnalysis = _projectId ? _rawSite : null;
  const [addr, setAddr] = useState("");
  const [extra, setExtra] = useState<string[]>([]); // 다필지 추가 주소
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PermitAnalysis | null>(null);
  // AI 인허가 해석 옵트인 — 종전엔 use_llm 미전송이라 백엔드 기본값(true)에 암묵 의존해 항상 ON이었다.
  // 기본 true로 유지해 기존 동작을 보존하면서, 끄면 규칙기반(무과금) 판정만 받을 수 있게 한다(D1).
  const [useLlm, setUseLlm] = useState(true);
  // 히스토리 카드 재조회 신호 — run() 완료 시 증가시켜 AnalysisHistoryCard가 새 항목을 반영한다.
  const [historyRefreshTick, setHistoryRefreshTick] = useState(0);

  // ★다필지 배선 절단 근본수정(2026-07-19 라이브 신고: 12필지 선택 → 구획도·개발방식·등기에
  //   1필지만 반영). 종전엔 run()만 store 다필지(siteAnalysis.parcels)를 폴백에 포함하고,
  //   렌더 자식(ParcelBoundaryMap·DevelopmentScenarioCard·RegistryBulkButton)엔 인라인
  //   [addr, ...extra](스토어 다필지 누락)를 넘겨 대표주소 1개만 갔다. 단일 SSOT로 공용화 —
  //   run()과 모든 렌더 자식이 이 동일 목록을 쓴다(주소 문자열 계약·중복 target 제거·순서 보존).
  const analysisParcelAddrs = useMemo(
    () => buildAnalysisParcelAddrs(addr || siteAnalysis?.address || "", extra, siteAnalysis?.parcels),
    [addr, extra, siteAnalysis],
  );

  const run = useCallback(async () => {
    const target = addr || siteAnalysis?.address || "";
    if (!target) {
      setError("주소를 먼저 선택하거나 입력하세요.");
      return;
    }
    const parcels = analysisParcelAddrs;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await apiClient.post<PermitAnalysis>("/permits/ai-analysis", {
        body: {
          address: target,
          pnu: siteAnalysis?.pnu || undefined,
          site: siteAnalysis?.address === target ? siteAnalysis : undefined,
          parcels: parcels.length > 1 ? parcels : undefined,
          use_llm: useLlm,
        },
        useMock: false,
        timeoutMs: 150000,
      });
      setResult(r);
      setHistoryRefreshTick((t) => t + 1);
    } catch (err) {
      // 무반응 방지: 실패 원인을 구체적으로 안내(인증/과금/기타). 401·403=로그인 필요, 402=코인.
      if (err instanceof ApiClientError && (err.status === 401 || err.status === 403)) {
        setError("인허가 AI 분석은 로그인이 필요합니다. 로그인 후 다시 시도하세요.");
      } else if (err instanceof ApiClientError && err.status === 402) {
        setError("AI 인허가 분석은 사용량(코인)이 필요합니다. 충전 후 다시 시도하세요.");
      } else {
        setError("인허가 AI 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
      }
    } finally {
      setLoading(false);
    }
  }, [addr, siteAnalysis, useLlm, analysisParcelAddrs]);

  // 히스토리 대상(현재 입력) + 변동감지 시그니처 파트 — run() 내부와 동일한 필지 폴백 규칙을 미러링.
  //   백엔드 계약과 동일 순서: [address, pnu||"", parcelCount, useLlm, options요약(인허가는 옵션 없음→"")].
  const historyAddress = addr || siteAnalysis?.address || "";
  const historyPnu = siteAnalysis?.pnu || "";
  const historySignatureParts = useMemo(() => {
    // ★run()이 실제 보내는 목록과 동일 SSOT(buildAnalysisParcelAddrs) — 손수 미러링하면
    //   시그니처와 분석 대상이 어긋나 변동감지가 오작동(중복 제거 규칙까지 일치해야 한다).
    const parcels = buildAnalysisParcelAddrs(historyAddress, extra, siteAnalysis?.parcels);
    // parcelCount는 백엔드(permits.py) `len(req.parcels or []) or 1`을 미러(`|| 1`) — 단일필지
    // (미전송)여도 백엔드는 1로 적재하므로 0이면 오탐.
    return [historyAddress, historyPnu, String(parcels.length || 1), String(useLlm), optionsSummary(undefined)];
  }, [historyAddress, historyPnu, extra, siteAnalysis?.parcels, useLlm]);

  const site = result?.site;

  // ── 특이부지 게이트 ──
  // 백엔드가 result.site.special_parcel(detect_special_parcel 산출)에 실어준 값만 읽는다(가짜 생성 0).
  // is_special일 때만 객체. developability(영문) → 한국어 라벨(미지 등급은 severity_label 폴백).
  // factors는 객체({category}) 또는 문자열 혼재 → 표시 라벨 배열로 정규화. 모두 null 가드.
  const sp = site?.special_parcel ?? null;
  const isSpecialParcel = sp?.is_special === true;
  // ★공용 specialFactorLabels로 category 추출(dict factor "[object Object]" 오렌더 방지·전역 일관).
  const spFactors = specialFactorLabels(sp?.factors);
  const spDevelopabilityLabel =
    (sp?.developability && DEVELOPABILITY_LABEL[sp.developability]) ||
    (typeof sp?.severity_label === "string" ? sp.severity_label : null);
  // 법정한도가 그대로 실현되지 않는 등급이면 시나리오·추천에 경고 prefix를 붙인다(POSSIBLE은 게이트 미적용).
  const isGatedParcel =
    isSpecialParcel && !!sp?.developability && GATED_DEVELOPABILITY.has(sp.developability);

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* Hero — 인허가 관제 콘솔 헤더 */}
      <Card className="cc-bracketed overflow-hidden rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <CardContent className="relative p-6">
          <div className="cc-grid-bg opacity-40" />
          <div className="relative z-10 flex items-center justify-between gap-3">
            <span className="cc-meta">PERMIT · ENTITLEMENT AI</span>
            <span className="cc-live"><i />LIVE</span>
          </div>
          <div className="relative z-10 mt-3 flex items-center gap-3">
            {/* 인허가/심사 — 문서 위 승인 체크(도장 의미). 디자인토큰 색·장식용 */}
            <svg
              viewBox="0 0 24 24"
              className="h-7 w-7 shrink-0 text-[var(--accent-strong)]"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
              <path d="M14 3v5h5" />
              <path d="M9 14.5l2 2 4-4.5" />
            </svg>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">인.허가분석 자동화</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                상위법령(국토계획법·건축법·주택법·도시개발법·공공주택특별법·도시정비법)과 도시·군관리계획,
                해당 지자체 조례를 종합해 개발방식별 인허가 가능성·문제점·해결방안을 AI로 분석합니다.
              </p>
            </div>
          </div>

          <div className="relative z-10 mt-5">
            <ProjectAddressInput
              value={addr}
              onChange={setAddr}
              label="분석 대상지 주소 (단일·다필지)"
              placeholder="주소 검색 또는 엑셀로 다필지 일괄 등록"
              pickerLabel="분석 히스토리"
              disabled={loading}
              multi
              onParcelsChange={(all) => {
                // 다필지: 첫 필지=대표주소, 나머지=통합개발 추가필지(extra).
                setAddr(all[0] || "");
                setExtra(all.slice(1));
              }}
            />
          </div>

          {/* 다필지 통합개발 상태 — 위 주소바(다필지·엑셀)에서 등록한 필지 수 표시 */}
          <div className="relative z-10 mt-3">
            <span className="text-[11px] text-[var(--text-tertiary)]">
              {extra.length > 0
                ? `${extra.length + 1}개 필지 통합 — 용도지역이 다른 토지의 최적·최고 용적률을 함께 산정합니다`
                : "주소를 추가 검색하거나 엑셀로 다필지를 올리면 통합 개발 시 최적 용적률을 분석합니다 (단일필지는 그대로 실행)"}
            </span>
          </div>

          <div className="relative z-10 mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={run}
              disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "AI 분석 중… (약 2분)" : (<span className="inline-flex items-center gap-1.5"><Bot className="size-4" aria-hidden />인허가 분석</span>)}
            </button>
            {/* AI 해석 옵트인(기본 on — 기존 동작 보존). 끄면 규칙기반 판정만(무과금). */}
            <UseLlmToggle checked={useLlm} onChange={setUseLlm} disabled={loading} className="flex w-fit cursor-pointer items-center gap-2 text-[11px] text-[var(--text-secondary)]" />
            {error && <span className="text-xs font-semibold text-[var(--status-error)]">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {/* 필지 구획도 (단/다필지 경계 + 용도지역 + 인접성) — 주소 확정 시에만 */}
      {(addr || siteAnalysis?.address) && (
        <ParcelBoundaryMap parcels={analysisParcelAddrs} primaryZone={siteAnalysis?.zoneCode ?? undefined} />
      )}

      {/* 다각도 개발방식 시뮬레이션 (정책 적용판정 + 최적안 + 인접성) */}
      {(addr || siteAnalysis?.address) && (
        <DevelopmentScenarioCard
          address={addr || siteAnalysis?.address || undefined}
          parcels={analysisParcelAddrs}
        />
      )}

      {/* 등기부 일괄 조회/다운로드 (단/다필지 소유관계) */}
      {(addr || siteAnalysis?.address) && (
        <RegistryBulkButton addresses={analysisParcelAddrs} />
      )}

      {/* 부지 요약 + 종합 */}
      {/* 분석 히스토리 — ★result 조건 밖(실행 전·리로드 직후에도 접근 가능 — W5 소실 결함 교정). */}
      {historyAddress ? (
        <AnalysisHistoryCard
          analysisType="permit_ai"
          address={historyAddress}
          pnu={historyPnu || null}
          currentSignatureParts={historySignatureParts}
          onReanalyze={run}
          reanalyzing={loading}
          refreshSignal={historyRefreshTick}
        />
      ) : null}

      {result && (
        <>
          {/* 특이부지 게이트 — 임야·학교용지·GB·맹지·도시계획시설 등은 용도지역상 법정 최대
              연면적/용적률이 그대로 실현되지 않는다. is_special일 때만 경고 배너를 시나리오/추천
              위에 표시해, 아래 개발방식 시뮬레이션을 일반 개발지처럼 단정 해석하지 않도록 한다.
              값은 모두 백엔드 detect_special_parcel 실값(developability·factors·honest_disclosure). */}
          {isSpecialParcel && (
            <div className="space-y-2 rounded-[var(--radius-2xl)] border border-[color-mix(in_srgb,var(--status-warning)_40%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] px-5 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] px-3 py-1 text-xs font-bold text-[var(--status-warning)]">
                  <AlertTriangle className="size-3.5" aria-hidden />특이부지{spFactors.length > 0 ? ` · ${spFactors.join(" · ")}` : ""}
                </span>
                {spDevelopabilityLabel && (
                  <span className="text-xs font-semibold text-[var(--status-warning)]">
                    개발가능성: {spDevelopabilityLabel}
                  </span>
                )}
                {isGatedParcel && (
                  <span className="text-[11px] font-medium text-[var(--text-secondary)]">
                    법정 최대 용적률·연면적이 그대로 실현되지 않을 수 있어, 아래 개발방식은 선행절차 통과를 전제로 한 잠재치입니다.
                  </span>
                )}
              </div>
              {sp?.honest_disclosure && (
                <p className="text-xs leading-5 text-[var(--text-secondary)]">{sp.honest_disclosure}</p>
              )}
            </div>
          )}

          {/* 한눈 요약(at-a-glance) — 최적 개발방식·핵심 규제 지표 */}
          {(() => {
            const top = [...result.methods].sort((a, b) => (b.score || 0) - (a.score || 0))[0];
            const s = result.site;
            // 특이부지 게이트가 걸리면 추천 개발방식 앞에 '특이부지' prefix로 잠재치임을 환기(가짜값 아님).
            const topMethodLabel: ReactNode = top
              ? isGatedParcel
                ? (<span className="inline-flex items-center gap-1"><AlertTriangle className="size-4" aria-hidden />특이부지 · {top.method}</span>)
                : top.method
              : "—";
            const kpis: [string, ReactNode][] = [
              ["추천 개발방식", topMethodLabel],
              ["인허가 가능성", top ? `${top.possibility} · ${top.score}점` : "—"],
              ["용도지역", s?.zone_type || "—"],
              ["용적률 한도", s?.max_far != null ? `${s.max_far}%` : "—"],
            ];
            return (
              <Card className="cc-bracketed overflow-hidden rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 shadow-[var(--shadow-md)]">
                <i className="cc-bracket cc-bracket--tl" />
                <i className="cc-bracket cc-bracket--tr" />
                <i className="cc-bracket cc-bracket--bl" />
                <i className="cc-bracket cc-bracket--br" />
                <CardContent className="relative p-5">
                  <div className="cc-grid-bg opacity-40" />
                  <div className="relative z-10 flex items-center justify-between">
                    <span className="cc-meta">DIAGNOSTIC · AT-A-GLANCE</span>
                    <span className="cc-chip-data">PERMIT</span>
                  </div>
                  <div className="relative z-10 mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
                    {kpis.map(([k, v], i) => (
                      <div key={k} className={`rounded-xl border p-3 ${i === 0 ? "border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10" : "border-[var(--line)] bg-[var(--surface-soft)]"}`}>
                        <p className="cc-label">{k}</p>
                        <p className={`cc-num mt-1 text-base font-[1000] ${i === 0 ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{v}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })()}

          {/* 검증 배지 + AI 인허가 해석 요약 통합 카드(상세 환경 카드는 아래 유지). */}
          <AnalysisVerdict
            analysisType="permit"
            context={result as unknown as Record<string, unknown>}
            interpretation={result.summary}
            interpretationTitle="AI 인허가 해석"
            // 응답 최상위 ledger_hash(원장 sha256) — 피드백 조인키(미노출이면 undefined·안전).
            ledgerHash={(result as unknown as { ledger_hash?: string })?.ledger_hash}
          />

          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <p className="text-sm font-bold text-[var(--accent-strong)]">부지 종합 인허가 환경</p>
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
                    result.ai
                      ? "border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                      : "border-[var(--line-strong)] text-[var(--text-tertiary)]"
                  }`}
                >
                  {result.ai ? "AI 분석" : "규칙기반 폴백"}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{result.summary}</p>
              {site && (
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {[
                    ["용도지역", site.zone_type || "-"],
                    ["건폐율 한도", site.max_bcr != null ? `${site.max_bcr}%` : "-"],
                    ["용적률 한도", site.max_far != null ? `${site.max_far}%` : "-"],
                    ["대지면적", site.land_area_sqm != null ? `${Math.round(site.land_area_sqm)}㎡` : "-"],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 시니어 전문가 자문 verdict(심의·도시계획·법무) — 백엔드 senior_consultation 소비 */}
          <SeniorVerdictCard
            consultation={(result as { senior_consultation?: SeniorConsultation }).senior_consultation}
            title="시니어 인허가 자문(심의·도시계획·법무)"
          />

          {/* 일조권 · 건축가능 볼륨(정북일조 + 동지 일영) — 인허가 핵심 규제 정량화 */}
          <SolarEnvelopeCard
            address={site?.address || addr || siteAnalysis?.address || undefined}
            pnu={siteAnalysis?.pnu || undefined}
            zone={site?.zone_type || undefined}
            landAreaSqm={site?.land_area_sqm ?? effectiveLandAreaSqm(siteAnalysis) ?? undefined}
            farLimitPct={resolveFarPct(siteAnalysis) ?? undefined}
            bcrLimitPct={resolveBcrPct(siteAnalysis) ?? undefined}
          />

          {/* 다필지 통합 개발 — 최적·최고 용적률 산정 */}
          {result.multi_parcel && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]">
                    <Puzzle className="size-4" aria-hidden />다필지 통합 개발 · 최적 용적률 산정 ({result.multi_parcel.parcels?.length}개 필지)
                  </p>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
                      result.multi_parcel.ai
                        ? "border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                        : "border-[var(--line-strong)] text-[var(--text-tertiary)]"
                    }`}
                  >
                    {result.multi_parcel.ai ? "AI 산정" : "가중평균 기반"}
                  </span>
                </div>

                {/* 용적률 3종 */}
                <div className="mt-4 grid grid-cols-3 gap-3">
                  {[
                    ["법정 가중평균", result.multi_parcel.blended_far, "국토계획법 시행령 §84"],
                    ["최적 용적률", result.multi_parcel.optimal_far, "법정+통상 인센티브"],
                    ["최고 용적률", result.multi_parcel.max_far, "모든 상향수단 적용"],
                  ].map(([k, v, sub], idx) => (
                    <div
                      key={k as string}
                      className={`rounded-xl border p-3 text-center ${
                        idx === 1
                          ? "border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10"
                          : "border-[var(--line)] bg-[var(--surface-soft)]"
                      }`}
                    >
                      <p className="cc-label">{k as string}</p>
                      <p className="cc-num mt-0.5 text-lg font-black text-[var(--text-primary)]">
                        {v != null ? `${v}%` : "-"}
                      </p>
                      <p className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">{sub as string}</p>
                    </div>
                  ))}
                </div>

                {/* 필지별 표 */}
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-[var(--text-tertiary)]">
                        <th className="py-1.5 text-left font-semibold">필지</th>
                        <th className="py-1.5 text-left font-semibold">용도지역</th>
                        <th className="py-1.5 text-right font-semibold">용적률한도</th>
                        <th className="py-1.5 text-right font-semibold">면적</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result.multi_parcel.parcels ?? []).map((p, i) => (
                        <tr key={i} className="border-b border-[var(--line)]/50">
                          <td className="py-1.5 text-[var(--text-secondary)]">
                            {i + 1}. {p.address}
                          </td>
                          <td className="py-1.5 text-[var(--text-secondary)]">{p.zone_type || "미상"}</td>
                          <td className="py-1.5 text-right text-[var(--text-secondary)]">
                            {p.max_far != null ? `${p.max_far}%` : "-"}
                          </td>
                          <td className="py-1.5 text-right text-[var(--text-secondary)]">
                            {p.land_area_sqm != null ? `${Math.round(p.land_area_sqm)}㎡` : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {result.multi_parcel.far_rationale && (
                  <p className="mt-4 text-sm leading-relaxed text-[var(--text-secondary)]">
                    {result.multi_parcel.far_rationale}
                  </p>
                )}

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {(result.multi_parcel.integration_issues?.length ?? 0) > 0 && (
                    <div>
                      <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--status-error)]"><AlertTriangle className="size-3.5" aria-hidden />통합 인허가 문제점</p>
                      <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        {result.multi_parcel.integration_issues!.map((it, i) => (
                          <li key={i}>· {it}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(result.multi_parcel.integration_solutions?.length ?? 0) > 0 && (
                    <div>
                      <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--status-success)]"><CheckCircle2 className="size-3.5" aria-hidden />해결방안</p>
                      <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        {result.multi_parcel.integration_solutions!.map((s, i) => (
                          <li key={i}>· {s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {(result.multi_parcel.far_key_laws?.length ?? 0) > 0 && (
                  <div className="mt-4">
                    <p className="text-xs font-bold text-[var(--accent-strong)]">근거 법령</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {result.multi_parcel.far_key_laws!.map((l, i) => (
                        <span key={i} className="rounded-md bg-[var(--surface-soft)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                          {l}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* 개발방식별 카드 */}
          <div className="grid gap-4 lg:grid-cols-2">
            {[...result.methods]
              .sort((a, b) => (b.score || 0) - (a.score || 0))
              .map((m) => (
                <Card key={m.method} className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-sm)]">
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-black text-[var(--text-primary)]">{m.method}</p>
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${
                          POSSIBILITY_STYLE[m.possibility] || "border-[var(--line-strong)] text-[var(--text-secondary)]"
                        }`}
                      >
                        가능성 {m.possibility} · {m.score}점
                      </span>
                    </div>

                    <div className="mt-3 space-y-3 text-xs">
                      {m.key_laws?.length > 0 && (
                        <div>
                          <p className="font-bold text-[var(--accent-strong)]">근거 법령</p>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            {(m.key_laws ?? []).map((l, i) => (
                              <span key={i} className="rounded-md bg-[var(--surface-soft)] px-2 py-0.5 text-[var(--text-secondary)]">
                                {l}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {m.issues?.length > 0 && (
                        <div>
                          <p className="inline-flex items-center gap-1.5 font-bold text-[var(--status-error)]"><AlertTriangle className="size-3.5" aria-hidden />문제점</p>
                          <ul className="mt-1 space-y-0.5 text-[var(--text-secondary)]">
                            {(m.issues ?? []).map((it, i) => (
                              <li key={i}>· {it}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {m.solutions?.length > 0 && (
                        <div>
                          <p className="inline-flex items-center gap-1.5 font-bold text-[var(--status-success)]"><CheckCircle2 className="size-3.5" aria-hidden />해결방안</p>
                          <ul className="mt-1 space-y-0.5 text-[var(--text-secondary)]">
                            {(m.solutions ?? []).map((s, i) => (
                              <li key={i}>· {s}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
          </div>

          {/* 종합 권고 */}
          {result.recommendation && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]"><Pin className="size-4" aria-hidden />종합 권고</p>
                {/* 특이부지 게이트 시 권고 위에 잠재치 환기 — 백엔드 developability 라벨 실값 사용. */}
                {isGatedParcel && (
                  <p className="inline-flex items-start gap-1.5 mt-2 text-xs font-semibold text-[var(--status-warning)]">
                    <AlertTriangle className="size-3.5 mt-0.5 shrink-0" aria-hidden />특이부지(개발가능성 {spDevelopabilityLabel ?? "확인 필요"}) — 아래 권고는 선행절차 통과를 전제로 한 잠재안입니다.
                  </p>
                )}
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{result.recommendation}</p>
              </CardContent>
            </Card>
          )}

          {/* 인허가 서류 체크리스트 + PDF — 카드가 약속한 '필요서류·담당 액션·예상기간' 실산출.
              백엔드 GET /permits/package/checklist(정적 기준표) 소비 + POST /permits/package/pdf 다운로드.
              permit_type는 건축개발 기본(건축허가), 대지면적·농지 여부만 result에서 도출 전송(가짜값 0). */}
          <PermitChecklistCard
            landAreaSqm={site?.land_area_sqm ?? null}
            isAgricultural={spFactors.some((f) => f.includes("농지"))}
            projectId={_projectId ?? null}
          />

          {/* 전문가 패널 검증 */}
          <ExpertPanelCard
            analysisType="permit"
            address={result.site?.address || addr || siteAnalysis?.address || undefined}
            context={result as unknown as Record<string, unknown>}
          />
        </>
      )}
    </div>
  );
}

// API 오리진(버전 prefix 포함) — 바이너리(PDF) 다운로드는 apiClient(JSON 파서)를 못 쓰므로
// 원시 fetch 를 쓴다. MarketInsightsWorkspaceClient.marketApiBase 동형(peer 컨벤션 미러).
function permitApiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
}

// 인허가 유형 — 건축개발 프로젝트 기본값(건축허가). 체크리스트/PDF 양쪽에 동일 전송해 산출 일관성 보장.
const PERMIT_TYPE = "건축허가";

type ChecklistItem = {
  id: string;
  name: string;
  required: boolean;
  description?: string;
  applicable: boolean;
};
type ChecklistResponse = {
  permit_type: string;
  region: string;
  checklist: {
    permit_type: string;
    total_items: number;
    required_items: number;
    optional_items: number;
    items: ChecklistItem[];
  };
  duration: {
    permit_type: string;
    region: string;
    business_days: number;
    calendar_days: number;
    stages: string[];
  };
  duration_basis: string;
};

/**
 * 인허가 서류 체크리스트 + 예상기간 + PDF 다운로드 카드.
 *
 * 백엔드 GET /permits/package/checklist(정적 기준표 — LLM/외부 API 미사용)를 소비해 카드가 약속한
 * '필요서류·담당·예상기간' 산출물을 실제로 채운다. permit_type는 건축개발 기본값(건축허가)이며,
 * 대지면적(≥200㎡ 조경계획서)·농지 여부(농지전용허가서)만 분석 결과에서 도출해 전송한다(가짜값 0).
 * 조회 실패 시 카드를 숨기지 않고 '조회 실패'를 정직 표기한다(무목업).
 */
function PermitChecklistCard({
  landAreaSqm,
  isAgricultural,
  projectId,
}: {
  landAreaSqm?: number | null;
  isAgricultural: boolean;
  projectId: string | null;
}) {
  const [data, setData] = useState<ChecklistResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");

  // 대지면적 200㎡ 이상이면 조경계획서 등 조건부 서류가 적용된다(백엔드 기준표 매칭).
  const buildingAreaSqm =
    landAreaSqm != null && landAreaSqm > 0 ? Math.round(landAreaSqm) : undefined;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ permit_type: PERMIT_TYPE });
    if (buildingAreaSqm !== undefined) params.set("building_area_sqm", String(buildingAreaSqm));
    if (isAgricultural) params.set("is_agricultural", "true");
    apiClient
      .get<ChecklistResponse>(`/permits/package/checklist?${params.toString()}`, { useMock: false })
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch(() => {
        if (!cancelled) setError("체크리스트 조회에 실패했습니다. 잠시 후 다시 시도하세요.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [buildingAreaSqm, isAgricultural]);

  const downloadPdf = useCallback(async () => {
    setDownloading(true);
    setDownloadError("");
    try {
      const token =
        (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${permitApiBase()}/permits/package/pdf`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          permit_type: PERMIT_TYPE,
          project_id: projectId || undefined,
          ...(buildingAreaSqm !== undefined ? { building_area_sqm: buildingAreaSqm } : {}),
          ...(isAgricultural ? { is_agricultural: true } : {}),
        }),
      });
      // 성공=application/pdf(attachment), 실패=4xx/5xx(JSON) — blob 침묵 오염 차단(정직 표기).
      if (!res.ok || (res.headers.get("content-type") || "").includes("json")) {
        setDownloadError("PDF 생성에 실패했습니다. (로그인·권한 필요)");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `인허가서류패키지_${PERMIT_TYPE}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError("PDF 다운로드에 실패했습니다.");
    } finally {
      setDownloading(false);
    }
  }, [buildingAreaSqm, isAgricultural, projectId]);

  const cl = data?.checklist;
  const dur = data?.duration;

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]">
            <ClipboardList className="size-4" aria-hidden />인허가 서류 체크리스트
          </p>
          <span className="rounded-full border border-[var(--line-strong)] px-2.5 py-0.5 text-[11px] font-bold text-[var(--text-tertiary)]">
            {PERMIT_TYPE} 기준
          </span>
        </div>
        <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">
          건축개발 기본(건축허가) 기준의 필요서류·예상기간입니다. 대지면적·농지 포함 여부에 따라 조건부 서류가 자동 반영됩니다.
        </p>

        {loading && (
          <p className="mt-4 text-sm text-[var(--text-secondary)]">체크리스트 조회 중…</p>
        )}
        {!loading && error && (
          <p className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--status-error)]">
            <AlertTriangle className="size-4" aria-hidden />{error}
          </p>
        )}

        {!loading && !error && cl && (
          <>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--line)] text-[var(--text-tertiary)]">
                    <th className="py-1.5 pr-2 text-left font-semibold">번호</th>
                    <th className="py-1.5 pr-2 text-left font-semibold">서류명</th>
                    <th className="py-1.5 pr-2 text-left font-semibold">구분</th>
                    <th className="py-1.5 pr-2 text-left font-semibold">적용</th>
                    <th className="py-1.5 text-left font-semibold">발급·작성(비고)</th>
                  </tr>
                </thead>
                <tbody>
                  {(cl.items ?? []).map((it) => (
                    <tr key={it.id} className="border-b border-[var(--line)]/50">
                      <td className="py-1.5 pr-2 text-[var(--text-tertiary)]">{it.id}</td>
                      <td className="py-1.5 pr-2 font-semibold text-[var(--text-primary)]">{it.name}</td>
                      <td className="py-1.5 pr-2 text-[var(--text-secondary)]">
                        {it.required ? "필수" : "조건부"}
                      </td>
                      <td className="py-1.5 pr-2">
                        <span
                          className={
                            it.applicable
                              ? "font-bold text-[var(--status-success)]"
                              : "text-[var(--text-tertiary)]"
                          }
                        >
                          {it.applicable ? "적용" : "해당없음"}
                        </span>
                      </td>
                      <td className="py-1.5 text-[var(--text-secondary)]">{it.description || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="mt-3 text-xs text-[var(--text-secondary)]">
              총 {cl.total_items}건 중 적용 <b className="text-[var(--text-primary)]">{cl.required_items}건</b>
              {" "}(조건부 {cl.optional_items}건)
              {dur && (
                <>
                  {" · 예상 소요 "}
                  <b className="text-[var(--text-primary)]">{dur.business_days}영업일</b>
                  {` (달력 약 ${dur.calendar_days}일)`}
                </>
              )}
            </p>
            {data?.duration_basis && (
              <p className="mt-1 text-[10px] leading-snug text-[var(--text-tertiary)]">
                ※ {data.duration_basis}
              </p>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[var(--line)] pt-4">
              <button
                onClick={() => void downloadPdf()}
                disabled={downloading}
                className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
              >
                <FileDown className="size-4" aria-hidden />
                {downloading ? "PDF 생성 중…" : "서류 패키지 PDF"}
              </button>
              {downloadError && (
                <span className="text-xs font-semibold text-[var(--status-error)]">{downloadError}</span>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
