"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { FieldSourceBadge } from "@/components/common/FieldSourceBadge";
import { MarkdownLite } from "@/components/common/MarkdownLite";
import {
  useProjectContextStore,
  type CostData,
  type ProvenanceModule,
} from "@/store/useProjectContextStore";
import { SiteAnalysisDetail } from "./SiteAnalysisDetail";

// 세련된 인라인 아이콘(lucide 스타일) — 이모지 대체
function IconSparkle() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.6 4.6L18 9.2l-4.4 1.6L12 15l-1.6-4.2L6 9.2l4.4-1.6L12 3z" />
      <path d="M5 16l.8 2.2L8 19l-2.2.8L5 22l-.8-2.2L2 19l2.2-.8L5 16z" />
    </svg>
  );
}
function IconPin() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 17v5" /><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" />
    </svg>
  );
}

const NARR_LABELS: Record<string, string> = {
  carbon_assessment: "탄소 평가", reduction_strategy: "저감 전략", certification_pathway: "인증 경로",
  zeb_roadmap: "ZEB 로드맵", esg_investment_impact: "투자 영향", regulatory_outlook: "규제 전망",
  summary: "요약", analysis: "분석", recommendation: "권고", opinion: "의견", risk: "리스크",
};

/* ── Types ── */

interface PipelineStageStatus {
  stage: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  duration_ms: number | null;
  data: Record<string, unknown>;
  error: string | null;
}

interface PipelineRunResponse {
  pipeline_id: string;
  project_id: string;
  status: string;
  stages: PipelineStageStatus[];
  summary: Record<string, Record<string, unknown>>;
}

interface PipelineResultDetailProps {
  result: PipelineRunResponse;
  onRerun?: (stageName: string, overrides: Record<string, unknown>) => void;
  addresses?: string[];   // 다필지 주소(이력 복원분) — 필지 구획도에 전체 필지 표시용
}

/* ── Section definitions ── */

interface SectionDef {
  id: string;
  label: string;
  sourceStage: string;
  fields: FieldDef[];
}

interface FieldDef {
  key: string;
  label: string;
  unit: string;
  editable: boolean;
  format?: (v: unknown) => string;
}

function fmtNum(v: unknown): string {
  if (typeof v !== "number") return String(v ?? "-");
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(0)}만`;
  return v.toLocaleString("ko-KR");
}

function fmtPct(v: unknown): string {
  return typeof v === "number" ? `${v.toFixed(1)}` : "-";
}

function fmtArea(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString("ko-KR") : "-";
}

const SECTIONS: SectionDef[] = [
  {
    id: "overview",
    label: "1. 사업개요",
    sourceStage: "site_analysis",
    fields: [
      { key: "land_area_sqm", label: "대지면적", unit: "m\u00B2", editable: true, format: fmtArea },
      { key: "basic.zone_type", label: "용도지역", unit: "", editable: false },
      { key: "basic.pnu", label: "PNU 코드", unit: "", editable: false },
      { key: "pricing.official_price_per_sqm", label: "추정 지가(㎡당)", unit: "원", editable: false, format: fmtNum },
    ],
  },
  {
    id: "location",
    label: "2. 입지분석",
    sourceStage: "site_analysis",
    fields: [
      { key: "infrastructure.nearest_subway.name", label: "최근접 지하철", unit: "", editable: false },
      { key: "infrastructure.nearest_subway.distance_m", label: "지하철 거리", unit: "m", editable: false, format: fmtNum },
      { key: "infrastructure.schools.0.name", label: "최근접 학교", unit: "", editable: false },
      { key: "infrastructure.schools.0.distance_m", label: "학교 거리", unit: "m", editable: false, format: fmtNum },
      { key: "basic.land_category", label: "지목", unit: "", editable: false },
      { key: "basic.owner_type", label: "소유구분", unit: "", editable: false },
      { key: "max_bcr", label: "건폐율 한도", unit: "%", editable: false, format: fmtPct },
      { key: "max_far", label: "용적률 한도", unit: "%", editable: false, format: fmtPct },
    ],
  },
  {
    id: "architecture",
    label: "3. 건축계획",
    sourceStage: "design",
    fields: [
      { key: "building_type", label: "건축유형", unit: "", editable: false },
      { key: "floor_count", label: "층수", unit: "층", editable: true },
      { key: "total_gfa_sqm", label: "연면적", unit: "m\u00B2", editable: true, format: fmtArea },
      { key: "bcr", label: "건폐율", unit: "%", editable: false, format: fmtPct },
      { key: "far", label: "용적률", unit: "%", editable: false, format: fmtPct },
    ],
  },
  {
    id: "unit_mix",
    label: "4. 평형 구성",
    sourceStage: "design",
    fields: [
      { key: "unit_count", label: "세대수", unit: "세대", editable: true },
      { key: "avg_unit_sqm", label: "평균 전용면적", unit: "m\u00B2", editable: true, format: fmtArea },
      { key: "parking_ratio", label: "주차대수 비율", unit: "%", editable: false, format: fmtPct },
    ],
  },
  {
    id: "cost",
    label: "5. 공사비",
    sourceStage: "cost",
    fields: [
      { key: "total_construction_cost", label: "총공사비", unit: "", editable: true, format: fmtNum },
      { key: "cost_per_pyeong", label: "평당 공사비", unit: "원/평", editable: false, format: fmtNum },
      { key: "direct_cost", label: "직접공사비", unit: "", editable: false, format: fmtNum },
      { key: "construction_months", label: "공사기간", unit: "개월", editable: false },
    ],
  },
  {
    id: "feasibility",
    label: "6. 수지분석",
    sourceStage: "feasibility",
    fields: [
      { key: "total_revenue_won", label: "총수입", unit: "", editable: true, format: fmtNum },
      { key: "total_cost_won", label: "총사업비", unit: "", editable: true, format: fmtNum },
      { key: "profit_rate_pct", label: "수익률", unit: "%", editable: false, format: fmtPct },
      { key: "grade", label: "등급", unit: "", editable: false },
      { key: "net_profit_won", label: "순이익", unit: "", editable: false, format: fmtNum },
    ],
  },
  {
    id: "tax",
    label: "7. 세금",
    sourceStage: "tax",
    fields: [
      { key: "acquisition_tax", label: "취득세", unit: "", editable: false, format: fmtNum },
      { key: "transfer_tax", label: "양도세", unit: "", editable: false, format: fmtNum },
      { key: "comprehensive_tax", label: "종부세", unit: "", editable: false, format: fmtNum },
      { key: "total_tax", label: "세금 합계", unit: "", editable: false, format: fmtNum },
    ],
  },
  {
    id: "esg",
    label: "8. ESG/탄소",
    sourceStage: "esg",
    fields: [
      { key: "embodied_carbon_kg", label: "내재탄소", unit: "kg", editable: false, format: fmtNum },
      { key: "operational_carbon_30yr_kg", label: "운영탄소(30년)", unit: "kg", editable: false, format: fmtNum },
      { key: "total_carbon_per_sqm", label: "탄소밀도", unit: "kgCO\u2082/m\u00B2", editable: false, format: fmtPct },
      { key: "gresb_score", label: "GRESB 점수", unit: "점", editable: false },
    ],
  },
  {
    id: "compliance",
    label: "9. 법규검토",
    sourceStage: "report",
    fields: [
      { key: "compliance_pass", label: "통과 항목", unit: "개", editable: false },
      { key: "compliance_fail", label: "위반 항목", unit: "개", editable: false },
      { key: "compliance_total", label: "전체 항목", unit: "개", editable: false },
    ],
  },
  {
    id: "summary",
    label: "10. 종합평가",
    sourceStage: "report",
    fields: [
      { key: "overall_grade", label: "종합등급", unit: "", editable: false },
      { key: "risk_level", label: "리스크 수준", unit: "", editable: false },
      { key: "recommendation", label: "투자 의견", unit: "", editable: false },
    ],
  },
];

/* ── 오버라이드 영속 매핑(STORE_FIELD_MAP) ──
   재분석은 flat "{stage}.{field}" 계약(onRerun)을 그대로 쓰되, "수동 입력값"으로
   장기 보존할 가치가 있는 핵심 필드만 store(useProjectContextStore.manualFields)에
   source:"user"로 영속한다 — 페이지 이탈 후에도 수동값이 살아남고(소실 해소),
   자동 갱신(재분석 saveToStore)이 이 필드를 덮어쓰지 못한다(merge 가드).
   매핑되지 않은 편집 필드는 기존대로 세션 한정(overrides state)으로만 동작한다. */
interface StoreFieldEntry {
  module: ProvenanceModule;
  storeField: string; // store 데이터/manualFields의 키(예: landAreaSqm)
}
const STORE_FIELD_MAP: Record<string, StoreFieldEntry> = {
  "site_analysis.land_area_sqm": { module: "siteAnalysis", storeField: "landAreaSqm" },
  "cost.total_construction_cost": { module: "cost", storeField: "totalConstructionCostWon" },
};
const storeFieldKey = (stage: string, field: string) => `${stage}.${field}`;

/* ── Executive Summary Card Specs ── */

interface ExecKPI {
  label: string;
  key: string;
  source: string;
  unit: string;
  format: (v: unknown) => string;
  color: string;
}

const EXEC_KPIS: ExecKPI[] = [
  { label: "수익률", key: "profit_rate_pct", source: "feasibility", unit: "%", format: fmtPct, color: "text-emerald-400" },
  { label: "총사업비", key: "total_cost_won", source: "feasibility", unit: "", format: fmtNum, color: "text-[var(--accent-strong)]" },
  { label: "순이익", key: "net_profit_won", source: "feasibility", unit: "", format: fmtNum, color: "text-emerald-400" },
  { label: "탄소밀도", key: "total_carbon_per_sqm", source: "esg_carbon", unit: "kgCO\u2082/m\u00B2", format: fmtPct, color: "text-yellow-400" },
  { label: "법규준수", key: "compliance_pass", source: "report", unit: "", format: (v) => String(v ?? "-"), color: "text-blue-400" },
];

/* ── Inline Edit Cell ── */

function EditableCell({
  value,
  fieldDef,
  onChange,
}: {
  value: unknown;
  fieldDef: FieldDef;
  onChange: (newVal: unknown) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const display = fieldDef.format ? fieldDef.format(value) : String(value ?? "-");

  const startEdit = () => {
    setDraft(String(value ?? ""));
    setEditing(true);
  };

  const commitEdit = () => {
    setEditing(false);
    const parsed = Number(draft);
    if (!isNaN(parsed)) {
      onChange(parsed);
    } else {
      onChange(draft);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") setEditing(false);
  };

  if (!fieldDef.editable) {
    const empty = value == null || value === "" || display === "-" || display === "—" || display === "NaN";
    return (
      <p className={`text-sm font-bold truncate ${empty ? "text-[var(--text-hint)] font-medium" : "text-[var(--text-primary)]"}`}>
        {empty ? "분석 전" : display}
      </p>
    );
  }

  if (editing) {
    return (
      <input
        autoFocus
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitEdit}
        onKeyDown={handleKeyDown}
        className="w-full h-7 rounded-md border border-[var(--accent-strong)] bg-[var(--surface)] px-2 text-sm font-bold text-[var(--text-primary)] outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/30"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={startEdit}
      className="group flex items-center gap-1 text-left w-full"
    >
      <span className="text-sm font-bold text-[var(--text-primary)] truncate">
        {display}
      </span>
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--text-hint)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      </svg>
    </button>
  );
}

/* ── Component ── */

export function PipelineResultDetail({ result, onRerun, addresses }: PipelineResultDetailProps) {
  const [activeTab, setActiveTab] = useState("overview");
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [downloading, setDownloading] = useState(false);

  // ── 오버라이드 영속(STORE_FIELD_MAP) — store 액션/provenance 구독 ──
  // 셀렉터 단위 구독으로 불필요 리렌더 최소화(기존 ProjectPipelinePanel 패턴과 동일).
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);
  const revertFieldToAuto = useProjectContextStore((s) => s.revertFieldToAuto);
  // 마운트 시 시드 복원·배지 출처 판정은 현재 manualFields 스냅을 구독해 반영한다.
  const manualFields = useProjectContextStore((s) => s.manualFields);
  // 온디맨드 AI 해석(섹션 열람 시 단건 생성) — 저장 payload에 없을 때만
  const [lazyNarr, setLazyNarr] = useState<Record<string, { label: string; text: string }[]>>({});
  const [narrLoading, setNarrLoading] = useState<string | null>(null);
  const [narrError, setNarrError] = useState<Record<string, boolean>>({});

  // Merge stage data + summary data for lookup
  const stageDataMap = useMemo(() => {
    const map: Record<string, Record<string, unknown>> = {};
    for (const stage of result.stages) {
      map[stage.stage] = { ...stage.data };
    }
    // Also merge summary
    if (result.summary) {
      for (const [key, val] of Object.entries(result.summary)) {
        map[key] = { ...map[key], ...val };
      }
    }
    return map;
  }, [result]);

  // Apply overrides on top
  const getFieldValue = useCallback(
    (sourceStage: string, fieldKey: string) => {
      const ov = overrides[sourceStage]?.[fieldKey];
      if (ov !== undefined) return ov;
      const root = stageDataMap[sourceStage];
      if (!root) return undefined;
      // 점(.) 경로 + 배열 인덱스 지원 (site_analysis 등 중첩 구조 대응)
      if (!fieldKey.includes(".")) return root[fieldKey];
      let cur: unknown = root;
      for (const part of fieldKey.split(".")) {
        if (cur == null) return undefined;
        cur = Array.isArray(cur) ? (cur as unknown[])[Number(part)] : (cur as Record<string, unknown>)[part];
      }
      return cur;
    },
    [stageDataMap, overrides],
  );

  // AI 서술 해석 추출 — 스테이지 데이터에서 분석 narrative(인터프리터 텍스트)를 찾아 보고서에 노출.
  const getNarratives = useCallback(
    (sourceStage: string): { label: string; text: string }[] => {
      const root = stageDataMap[sourceStage];
      if (!root || typeof root !== "object") return [];
      const out: { label: string; text: string }[] = [];
      const LABELS: Record<string, string> = {
        ai_analysis: "AI 분석", interpretation: "AI 해석", analysis: "분석", narrative: "해설",
        opinion: "AI 의견", ai_opinion: "AI 의견", recommendation: "권고", summary_text: "요약",
        explanation: "설명", ai_summary: "AI 요약", comment: "코멘트", review: "검토의견",
        risk_assessment: "리스크 평가", insight: "인사이트",
      };
      const pushText = (label: string, v: unknown) => {
        if (typeof v === "string" && v.trim().length > 12) out.push({ label, text: v.trim() });
      };
      for (const [k, v] of Object.entries(root)) {
        if (LABELS[k]) pushText(LABELS[k], v);
        // 인터프리터가 {ai_interpretation:{section:text}} / {ai:{...}} 형태로 줄 수도 있음
        else if ((k === "ai" || k === "interpretation" || k === "llm" || k === "ai_interpretation") && v && typeof v === "object") {
          for (const [sk, sv] of Object.entries(v as Record<string, unknown>)) {
            pushText(LABELS[sk] || sk, sv);
          }
        }
      }
      return out.slice(0, 8);
    },
    [stageDataMap],
  );

  // 단계 해석 단건 fetch(온디맨드/프리페치 공용). showLoading=활성탭만 로딩표시.
  const fetchNarr = useCallback(
    (stg: string, showLoading: boolean, force = false) => {
      if (!force && (getNarratives(stg).length > 0 || lazyNarr[stg] || narrLoading === stg)) return;
      const data = stageDataMap[stg];
      if (!data || typeof data !== "object" || !Object.keys(data).length) return;
      const site = (stageDataMap.site_analysis || {}) as Record<string, any>;
      const dsn = (stageDataMap.design || {}) as Record<string, any>;
      const context: Record<string, unknown> = {
        address: site.address ?? site.juso,
        zone_type: site.zone_type ?? site.basic?.zone_type,
        land_area_sqm: site.land_area_sqm ?? site.basic?.land_area_sqm,
        total_gfa_sqm: dsn.total_gfa_sqm, building_type: dsn.building_type, floor_count: dsn.floor_count,
      };
      setNarrError((p) => ({ ...p, [stg]: false }));
      if (showLoading) setNarrLoading(stg);
      apiClient
        .postV2<{ ok?: boolean; sections?: Record<string, string> }>("/pipeline/interpret", {
          // E1: use_verification_retry=true → 검증관(VerifierService)이 fail/high 판정 시
          // LLM 1회 재생성하는 기 구현 피드백루프를 활성화한다(없으면 단발 생성).
          // 11개 섹션 + 검증 재생성은 첫 생성이 ~60~90초 걸릴 수 있다(이후 서버 캐시로 즉시).
          // 35s면 정상 생성도 타임아웃→'지연' 오표시되므로 120s로 상향(서버는 완료 후 캐시).
          body: { stage: stg, data, context, use_verification_retry: true }, useMock: false, timeoutMs: 120000,
        })
        .then((r) => {
          const secs = (r?.sections || {}) as Record<string, string>;
          const arr = Object.entries(secs)
            .filter(([, v]) => typeof v === "string" && v.trim().length > 12)
            .map(([k, v]) => ({ label: NARR_LABELS[k] || k, text: String(v).trim() }));
          if (arr.length) setLazyNarr((p) => ({ ...p, [stg]: arr }));
          else setNarrError((p) => ({ ...p, [stg]: true }));   // 빈 결과=실패 취급(재시도 유도)
        })
        .catch(() => setNarrError((p) => ({ ...p, [stg]: true })))
        .finally(() => setNarrLoading((c) => (c === stg ? null : c)));
    },
    [getNarratives, stageDataMap, lazyNarr, narrLoading],
  );

  // 활성 탭 온디맨드 로드(로딩 표시)
  useEffect(() => {
    const sec = SECTIONS.find((s) => s.id === activeTab);
    if (sec) fetchNarr(sec.sourceStage, true);
  }, [activeTab, fetchNarr]);

  // ② 선(先)생성 프리페치 — 진입 시 핵심 단계만 경량 워밍(과부하 방지, 나머지는 탭 클릭 시).
  useEffect(() => {
    const priority = ["site_analysis", "feasibility"];
    const timers = priority.map((stg, i) => setTimeout(() => fetchNarr(stg, false), 1000 + i * 2500));
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // STORE_FIELD_MAP에 등록된 핵심 필드는 store에 source:"user"로 영속한다(이탈 시 소실 해소).
  // siteAnalysis는 partial patch, cost는 full replace이므로 현재 store costData 위에 병합한다.
  const persistFieldToStore = useCallback((entry: StoreFieldEntry, value: unknown) => {
    if (entry.module === "siteAnalysis") {
      // partial patch — 단일 키만 갱신(나머지 보존). store는 Partial<SiteAnalysisData> 수용.
      updateSiteAnalysis(
        { [entry.storeField]: value } as Parameters<typeof updateSiteAnalysis>[0],
        { source: "user" },
      );
    } else if (entry.module === "cost") {
      // full replace 계약 — 현재 costData 위에 단일 필드만 덮어쓴다(나머지 보존).
      const prev = useProjectContextStore.getState().costData;
      const base: CostData = prev ?? {
        totalConstructionCostWon: null,
        perSqmWon: null,
        perPyeongWon: null,
        abovegroundWon: null,
        undergroundWon: null,
        landscapeWon: null,
        directWon: null,
        indirectWon: null,
        rangeMinWon: null,
        rangeMaxWon: null,
        source: "overview",
      };
      updateCostData({ ...base, [entry.storeField]: value } as CostData, { source: "user" });
    }
  }, [updateSiteAnalysis, updateCostData]);

  const setFieldOverride = useCallback((sourceStage: string, fieldKey: string, value: unknown) => {
    setOverrides((prev) => ({
      ...prev,
      [sourceStage]: { ...prev[sourceStage], [fieldKey]: value },
    }));
    const entry = STORE_FIELD_MAP[storeFieldKey(sourceStage, fieldKey)];
    if (entry) persistFieldToStore(entry, value);
  }, [persistFieldToStore]);

  // 마운트 시 manualFields(영속 user) → overrides 시드 복원.
  // store에 user로 보존된 핵심 필드를 세션 overrides에 주입해, 이탈/재진입 후에도
  // '수정됨' 링·재분석 대상으로 즉시 인지되게 한다(FieldSourceBadge는 별도로 출처 표기).
  useEffect(() => {
    const st = useProjectContextStore.getState();
    const seeded: Record<string, Record<string, unknown>> = {};
    for (const [flatKey, entry] of Object.entries(STORE_FIELD_MAP)) {
      const prov = st.getFieldProvenance(entry.module, entry.storeField);
      if (prov?.source !== "user") continue;
      const dataRec =
        entry.module === "siteAnalysis"
          ? (st.siteAnalysis as Record<string, unknown> | null)
          : (st.costData as Record<string, unknown> | null);
      const val = dataRec?.[entry.storeField];
      if (val == null) continue;
      const dot = flatKey.indexOf(".");
      const stage = flatKey.slice(0, dot);
      const field = flatKey.slice(dot + 1);
      seeded[stage] = { ...seeded[stage], [field]: val };
    }
    if (Object.keys(seeded).length > 0) {
      setOverrides((prev) => {
        const next = { ...prev };
        for (const [stage, fields] of Object.entries(seeded)) {
          next[stage] = { ...fields, ...next[stage] }; // 기존 세션 편집이 우선(시드는 보조)
        }
        return next;
      });
    }
    // 마운트 1회 — store 액션 정체성은 안정적이라 의존성 비포함(시드 복원은 진입 시 1회만).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasOverrides = Object.keys(overrides).length > 0;

  // Collect all overrides into flat map for rerun
  const collectOverrides = useCallback(() => {
    const flat: Record<string, unknown> = {};
    for (const [stage, fields] of Object.entries(overrides)) {
      for (const [k, v] of Object.entries(fields)) {
        flat[`${stage}.${k}`] = v;
      }
    }
    return flat;
  }, [overrides]);

  const handleRerun = useCallback(() => {
    if (!onRerun) return;
    const activeSection = SECTIONS.find((s) => s.id === activeTab);
    onRerun(activeSection?.sourceStage ?? "site_analysis", collectOverrides());
  }, [onRerun, activeTab, collectOverrides]);

  // 수정 초기화 — 세션 overrides를 비우고, STORE_FIELD_MAP에 영속된 user 플래그도 해제해
  // 다음 자동 갱신부터 덮어쓰기를 재허용한다(revertFieldToAuto). 값 자체는 보존(되돌림은
  // 다음 재분석이 담당) — 정직성: 임의 자동값으로 즉시 되돌리지 않는다.
  const resetOverrides = useCallback(() => {
    setOverrides({});
    for (const entry of Object.values(STORE_FIELD_MAP)) {
      revertFieldToAuto(entry.module, entry.storeField);
    }
  }, [revertFieldToAuto]);

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    try {
      // 실제 PDF 생성(reportlab) — 이미 계산된 result를 보내 재실행 없이 즉시 생성.
      const base = (() => {
        if (typeof window !== "undefined") {
          const h = window.location.hostname;
          if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr")
            return "https://api.4t8t.net/api/v2";
        }
        return "/api/proxy/v2";
      })();
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const r = await fetch(`${base}/pipeline/report/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ result: { summary: result.summary, stages: result.stages }, project_id: result.project_id }),
      });
      if (!r.ok || !(r.headers.get("content-type") || "").includes("pdf")) {
        alert("보고서 PDF 생성에 실패했습니다."); return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `PropAI_통합보고서_${result.project_id || "report"}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch {
      alert("보고서 다운로드에 실패했습니다.");
    } finally {
      setDownloading(false);
    }
  }, [result.summary, result.stages, result.project_id]);

  const activeSection = SECTIONS.find((s) => s.id === activeTab)!;
  const address =
    (stageDataMap.site_analysis?.address as string) ??
    (stageDataMap.site_analysis?.juso as string) ??
    "";
  const profitRate = getFieldValue("feasibility", "profit_rate_pct");
  const grade = getFieldValue("feasibility", "grade");

  return (
    <section className="rounded-2xl sm:rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-xl)] overflow-hidden transition-all">
      {/* ── Header ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6 border-b border-[var(--line)] bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent">
        <div className="flex items-center gap-3 mb-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-strong)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
              <path d="M14 2v6h6" />
              <path d="M16 13H8" />
              <path d="M16 17H8" />
              <path d="M10 9H8" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg sm:text-xl font-[800] tracking-tight text-[var(--text-primary)]">
              프로젝트 통합 분석 보고서
            </h2>
            {address && (
              <p className="text-sm font-medium text-[var(--text-secondary)] tracking-tight">
                {address}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── 신뢰도·할루시네이션 검증 배지(보고서 전체) ── */}
      <div className="px-6 pt-4 sm:px-8">
        <VerificationBadge
          analysisType="pipeline_report"
          context={(result.summary || {}) as Record<string, unknown>}
          // 응답 최상위 ledger_hash(원장 sha256) — 피드백 조인키(미노출이면 undefined·안전).
          ledgerHash={(result as unknown as { ledger_hash?: string })?.ledger_hash}
        />
      </div>

      {/* ── Executive Summary ── */}
      <div className="px-6 py-4 sm:px-8 border-b border-[var(--line)]">
        <div className="rounded-xl border border-[var(--accent-strong)]/20 bg-gradient-to-br from-[var(--accent-soft)]/30 to-transparent p-4 sm:p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
            <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.1em]">
              핵심 요약
            </h3>
            {typeof profitRate === "number" && typeof grade === "string" && (
              <span className="ml-auto text-xs font-bold px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                수익률 {fmtPct(profitRate)}% ({String(grade)}등급)
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {EXEC_KPIS.map((kpi) => {
              const val = getFieldValue(kpi.source, kpi.key);
              const formatted = kpi.format(val);
              // 미분석 상태 명확화 — 값 없음("-"/빈/NaN)일 때 "분석 전"으로 표기(핵심요약 카드 한정).
              const empty =
                val == null || val === "" || formatted === "-" || formatted === "—" || formatted === "NaN";
              return (
                <div
                  key={kpi.key}
                  className="rounded-xl bg-[var(--surface)] border border-[var(--line-strong)] p-3 text-center shadow-sm hover:shadow-[var(--shadow-glow)] hover:-translate-y-0.5 transition-all duration-300"
                >
                  <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-[0.12em] uppercase mb-1">
                    {kpi.label}
                  </p>
                  <p
                    className={`text-lg sm:text-xl font-[900] tracking-tight leading-none ${
                      empty ? "text-[var(--text-hint)] text-sm sm:text-base font-bold" : kpi.color
                    }`}
                  >
                    {empty ? "분석 전" : formatted}
                  </p>
                  {kpi.unit && !empty && (
                    <p className="text-[10px] font-medium text-[var(--text-tertiary)] mt-0.5">{kpi.unit}</p>
                  )}
                </div>
              );
            })}
          </div>
          {/* 종합 의견·리스크 — report 스테이지 서술이 있으면 노출 */}
          {(() => {
            const rec = getFieldValue("report", "recommendation") ?? getFieldValue("summary", "recommendation");
            const risk = getFieldValue("report", "risk_level") ?? getFieldValue("summary", "risk_level");
            const og = getFieldValue("report", "overall_grade") ?? getFieldValue("feasibility", "grade");
            if (!rec && !risk && !og) return null;
            return (
              <div className="mt-3 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)]"><IconPin /> 종합 의견</span>
                  {og ? <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-0.5 text-[11px] font-black text-[var(--accent-strong)]">종합등급 {String(og)}</span> : null}
                  {risk ? <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-bold text-amber-500">리스크 {String(risk)}</span> : null}
                </div>
                {rec ? <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{String(rec)}</p> : null}
              </div>
            );
          })()}
        </div>
      </div>

      {/* ── Tab Navigation (반응형 wrap — 좌우 스크롤 제거, 모든 탭 한눈에) ── */}
      <div className="px-6 sm:px-8 border-b border-[var(--line)]">
        <div className="flex flex-wrap gap-1.5 py-2">
          {SECTIONS.map((sec) => (
            <button
              key={sec.id}
              type="button"
              onClick={() => setActiveTab(sec.id)}
              className={`px-3 py-2 rounded-lg text-xs font-bold tracking-tight whitespace-nowrap transition-all ${
                activeTab === sec.id
                  ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-strong)] hover:text-[var(--text-primary)]"
              }`}
            >
              {sec.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Section Content ── */}
      <div className="px-6 py-5 sm:px-8 sm:py-6">
        <h3 className="text-sm font-bold text-[var(--text-primary)] tracking-[0.08em] mb-4">
          {activeSection.label}
        </h3>

        {/* ── E7: 가정값(assumed_defaults) 경고 배지 ──
            부지 단계가 외부 데이터 미확보로 기본 가정값(제2종/500㎡ 등)을 주입했으면
            data_quality="assumed_defaults"를 부지 출처 섹션에 정직 표기한다. 수치는 표시하되
            "가정값임"을 var(--status-warning)로 경고 — 사용자가 실측값으로 수정하도록 유도. */}
        {activeSection.sourceStage === "site_analysis" &&
          (() => {
            const site = stageDataMap.site_analysis;
            if (!site || site.data_quality !== "assumed_defaults") return null;
            const fields = Array.isArray(site.assumed_fields)
              ? (site.assumed_fields as unknown[]).map((f) => String(f))
              : [];
            return (
              <div className="mb-4 flex items-start gap-2 rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_38%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] px-4 py-3">
                <svg
                  width="15" height="15" viewBox="0 0 24 24" fill="none"
                  stroke="var(--status-warning)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                  className="mt-0.5 shrink-0"
                >
                  <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                  <line x1="12" x2="12" y1="9" y2="13" />
                  <line x1="12" x2="12.01" y1="17" y2="17" />
                </svg>
                <div className="text-[11px] leading-relaxed text-[var(--status-warning)]">
                  <span className="font-bold">가정값 사용</span> — 외부 데이터 미확보로 기본 가정값을 적용했습니다(실측 아님).
                  {fields.length > 0 && (
                    <span className="font-medium"> 해당 항목: {fields.join(", ")}.</span>
                  )}
                  <span className="font-medium"> 정확한 값으로 수정 후 재분석을 권장합니다.</span>
                </div>
              </div>
            );
          })()}

        {/* ── 부지분석 풍부 보고서(첫 분석과 동일) — 지도(필지구획도·주변실거래)·기본토지정보 ── */}
        {/* '입지분석' 탭에서만 1회 마운트(사업개요 탭 중복 제거). 자체 AI 해석은 hideInterpretation으로 숨김
            — 보고서 하단의 한글 라벨 "AI 상세 해석"과 중복되므로 지도+기본 토지정보만 노출한다. */}
        {activeSection.id === "location" &&
          (() => {
            const siteData = stageDataMap.site_analysis;
            const hasSiteData = siteData && Object.keys(siteData).length > 0;
            if (!hasSiteData) {
              return (
                <div className="mb-5 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-xs text-[var(--text-hint)]">
                  지도 데이터 없음 — 이 분석은 지도용 부지 데이터가 저장되지 않았습니다. 재분석 시 필지 구획도·주변 실거래 지도가 표시됩니다.
                </div>
              );
            }
            // 필지 구획도·주변 지도는 주소로 라이브 재조회 — 저장본에 좌표가 없어도 주소만 있으면 표시.
            // 다필지(addresses)가 복원돼 있으면 전체 필지를, 없으면 대표 1필지를 표시(옛 이력은 대표만 저장됨).
            const _basic = siteData.basic as Record<string, unknown> | undefined;
            const _addr = (_basic?.address as string) || (siteData.address as string) || "";
            const _parcels = (addresses && addresses.length > 0)
              ? addresses
              : (_addr ? [_addr] : []);
            return (
              <div className="mb-5">
                <SiteAnalysisDetail data={siteData} parcels={_parcels} hideInterpretation />
              </div>
            );
          })()}

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {(activeSection.fields ?? []).map((field) => {
            const val = getFieldValue(activeSection.sourceStage, field.key);
            const isOverridden = overrides[activeSection.sourceStage]?.[field.key] !== undefined;
            // 영속 출처(provenance) — STORE_FIELD_MAP에 등록된 필드만 store에서 user/auto를
            // 판정한다(미등록 필드는 배지 없음 = 세션 한정 '수정됨' 칩만 사용).
            const storeEntry = STORE_FIELD_MAP[storeFieldKey(activeSection.sourceStage, field.key)];
            const prov = storeEntry
              ? manualFields?.[storeEntry.module]?.[storeEntry.storeField] ?? null
              : null;

            return (
              <div
                key={field.key}
                className={`rounded-xl bg-[var(--surface)] border px-4 py-3 transition-all ${
                  isOverridden
                    ? "border-[var(--accent-strong)]/50 ring-1 ring-[var(--accent-strong)]/20"
                    : "border-[var(--line-strong)]"
                }`}
              >
                <p className="text-[10px] font-bold text-[var(--text-hint)] tracking-[0.12em] uppercase mb-1 flex items-center gap-1">
                  {field.label}
                  {field.unit && (
                    <span className="text-[var(--text-hint)]/60">({field.unit})</span>
                  )}
                  <span className="ml-auto flex items-center gap-1">
                    {/* 영속 출처 배지 — user(영속)/auto. 세션 '수정됨' 칩과 병기(소실 해소 가시화). */}
                    {prov && <FieldSourceBadge source={prov.source} updatedAt={prov.updatedAt} />}
                    {isOverridden && (
                      <span className="text-[8px] px-1.5 py-0.5 rounded bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] font-bold">
                        수정됨
                      </span>
                    )}
                  </span>
                </p>
                <EditableCell
                  value={val}
                  fieldDef={field}
                  onChange={(newVal) => setFieldOverride(activeSection.sourceStage, field.key, newVal)}
                />
              </div>
            );
          })}
        </div>

        {/* ── AI 상세 해석(저장 + 온디맨드 생성) ── */}
        {(() => {
          const stg = activeSection.sourceStage;
          const narr = [...getNarratives(stg), ...(lazyNarr[stg] || [])];
          const isLoading = narrLoading === stg && narr.length === 0;
          const hasErr = narrError[stg] && narr.length === 0;
          const hasData = stageDataMap[stg] && Object.keys(stageDataMap[stg]).length > 0;
          if (!narr.length && !isLoading && !hasErr) {
            // 데이터는 있으나 아직 미생성 → 수동 생성 버튼 제공(자동 미트리거 시)
            if (!hasData) return null;
            return (
              <div className="mt-5">
                <button onClick={() => fetchNarr(stg, true, true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-3.5 py-2 text-xs font-bold text-[var(--accent-strong)] hover:opacity-90">
                  <IconSparkle /> AI 상세 해석 생성
                </button>
              </div>
            );
          }
          return (
            <div className="mt-5 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-[var(--accent-strong)]"><IconSparkle /></span>
                <h4 className="text-sm font-bold text-[var(--accent-strong)]">AI 상세 해석</h4>
                {isLoading && <span className="text-[11px] text-[var(--text-hint)]">생성 중… (최대 1~2분, 완료 후 자동 표시)</span>}
              </div>
              {narr.map((n, i) => (
                <div key={i} className="rounded-xl border border-[var(--accent-strong)]/15 bg-[var(--accent-soft)]/30 p-4">
                  <p className="mb-1 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)]">{n.label}</p>
                  <MarkdownLite text={n.text} className="text-sm text-[var(--text-secondary)]" />
                </div>
              ))}
              {isLoading && (
                <div className="rounded-xl border border-[var(--accent-strong)]/15 bg-[var(--accent-soft)]/20 p-4">
                  <div className="h-3 w-2/3 animate-pulse rounded bg-[var(--line-strong)]" />
                  <div className="mt-2 h-3 w-full animate-pulse rounded bg-[var(--line)]" />
                  <div className="mt-2 h-3 w-5/6 animate-pulse rounded bg-[var(--line)]" />
                </div>
              )}
              {hasErr && (
                <div className="flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-400">
                  <span>해석 생성이 길어지고 있습니다 — 잠시 후 재시도하면 (서버에 생성·캐시된) 결과가 즉시 표시됩니다.</span>
                  <button onClick={() => fetchNarr(stg, true, true)} className="rounded-md border border-amber-500/40 px-2.5 py-1 font-bold hover:bg-amber-500/10">↻ 재시도</button>
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {/* ── Action Bar ── */}
      <div className="px-6 py-4 sm:px-8 border-t border-[var(--line)] flex flex-wrap items-center gap-3">
        {/* Download */}
        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading}
          className="h-10 px-5 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] text-sm font-bold text-[var(--text-primary)] hover:bg-[var(--surface-strong)] transition-all disabled:opacity-50 flex items-center gap-2"
        >
          {downloading ? (
            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" x2="12" y1="15" y2="3" />
            </svg>
          )}
          보고서 다운로드
        </button>

        {/* Rerun */}
        {onRerun && (
          <button
            type="button"
            onClick={handleRerun}
            disabled={!hasOverrides}
            className="h-10 px-5 rounded-xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] text-white text-sm font-bold shadow-[var(--shadow-glow)] hover:scale-[1.03] active:scale-[0.97] transition-all disabled:opacity-40 disabled:hover:scale-100 flex items-center gap-2"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 16h5v5" />
            </svg>
            {hasOverrides ? "수정값으로 재분석" : "재분석"}
          </button>
        )}

        {hasOverrides && (
          <button
            type="button"
            onClick={resetOverrides}
            className="h-10 px-4 rounded-xl text-xs font-bold text-[var(--text-secondary)] hover:text-red-400 transition-colors"
          >
            수정 초기화
          </button>
        )}
      </div>
    </section>
  );
}
