"use client";

/**
 * PersonaPanel — 실무 전문가 페르소나(분양대행·도시계획) 소비 UI(P1).
 *
 * 설계 결정(아키텍트): 페르소나는 DAG 노드(NodeId)가 아니라 동일 SSOT(projectId·주소·필지)를
 * '소비'하는 서버 오라클이다. 그래서 RunMode/plan 엔진(seedNodes·computeClosure·runNode)에
 * 끼워넣지 않고, OrchestratorPanel 안의 5번째 'view' 표면으로 분리한다. 이 컴포넌트는:
 *   - GET  /personas               → 페르소나 목록·체크리스트 미리보기(레지스트리 메타)
 *   - POST /personas/{key}/analyze → 선택 페르소나 분석(PersonaReport 핸드오프 계약)
 *   - POST /personas/{key}/analyze/pdf|pptx(StreamingResponse blob) → 보고서 다운로드
 *
 * ★경계(R6):
 *   - 읽기 소비만(updateSiteAnalysis/setProject 재기록 0). 입력은 useProjectContextStore에서 읽기만.
 *   - 결과는 로컬 React state(usePersona)만 보관 — propai-orchestration persist/byProject/snapshots 미접촉.
 *   - 무목업: 미확보 artifact 키는 카드를 생략(0 채우기 금지). missing 체크리스트는 "미확보" 정직 표기.
 *   - 계정격리: 매 POST 직전 boundProjectId===projectId 재확인(다른 프로젝트 컨텍스트로 호출 금지).
 *   - 무회귀: DAG 4모드·useNodeRunner·plan 엔진을 일절 건드리지 않는다(이 파일은 그쪽을 import도 안 함).
 *
 * 색상은 토큰만 사용(하드코딩 금지)·한국어.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import {
  adaptEvidence,
  type BackendEvidence,
  type BackendLegalRef,
} from "@/lib/evidence/adaptEvidence";

/* ── 백엔드 계약(읽기 전용 타입) ── */

/** GET /personas 목록 항목(registry.list_personas 메타). */
interface PersonaMeta {
  key: string;
  name_ko: string;
  checklist: { step: string; label: string; kpi?: string | null }[];
  expert_lens?: string;
  output_keys?: string[];
  billing_key?: string;
}

/** PersonaReport.checklist 1행(persona.py ChecklistItem). status=pass|warn|tentative|missing. */
interface ChecklistItem {
  step: string;
  label: string;
  status: string;
  value?: unknown;
  kpi?: string | null;
  note?: string | null;
}

/** PersonaReport(persona.py) — 핸드오프 reportContract. */
interface PersonaReport {
  persona_key: string;
  name_ko: string;
  project_id?: string | null;
  site_id?: string | null;
  address?: string | null;
  checklist: ChecklistItem[];
  artifacts: Record<string, unknown>;
  verification: Record<string, unknown>;
  honesty_notes: string[];
  status: string; // confirmed | tentative | partial
  billing?: Record<string, unknown>;
}

/** 분석 요청 입력(SSOT 1회 캡처) — PersonaAnalyzeRequest 정합. */
interface PersonaRequestBody {
  project_id: string | null;
  site_id: string | null;
  address: string | null;
  parcels: string[] | null;
  bcode: string | null;
  pnu: string | null;
  equity_won: number | null;
  // 설계·시공 페르소나 SSOT 입력 — useProjectContextStore에서 읽기 캡처(미확보면 null·정직 강등).
  // 시공(constructor): total_gfa_sqm 없으면 백엔드가 partial·정직 고지(estimate_overview gt=0 불가).
  // 설계(designer): land_area_sqm·zone_code 없으면 폴백 매스로 퇴화(백엔드가 정직 고지).
  total_gfa_sqm: number | null;
  land_area_sqm: number | null;
  zone_code: string | null;
  building_type: string | null;
  use_llm: boolean;
}

/* ── 상태 배지 토큰 매핑(토큰만 — 하드코딩 색상 금지) ── */

const CHECKLIST_BADGE: Record<string, { label: string; token: string }> = {
  pass: { label: "확인", token: "var(--status-success)" },
  warn: { label: "주의", token: "var(--status-warning)" },
  tentative: { label: "잠정", token: "var(--status-info)" },
  missing: { label: "미확보", token: "var(--text-tertiary)" },
};

const STATUS_BADGE: Record<string, { label: string; token: string }> = {
  confirmed: { label: "확정", token: "var(--status-success)" },
  tentative: { label: "잠정", token: "var(--status-info)" },
  partial: { label: "일부 미확보", token: "var(--text-tertiary)" },
};

/** 다운로드 idiom(ReportPdfDownload와 동일) — apiClient는 JSON만 반환하므로 blob은 수동 fetch. */
async function downloadPersonaBlob(
  personaKey: string,
  kind: "pdf" | "pptx" | "docx",
  body: PersonaRequestBody,
): Promise<void> {
  const { apiBaseUrl } = apiClient.getRuntimeConfig();
  const baseUrl = apiBaseUrl || "/api/proxy";
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("propai_access_token") ?? ""
      : "";
  // 통합 보고서 생성엔진: /analyze/report?format 이 4종을 PDF/PPTX/DOCX 로 렌더(분양대행은 pdf|pptx).
  const res = await fetch(
    `${baseUrl}/personas/${personaKey}/analyze/report?format=${kind}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    // 백엔드 400(주소·법정동코드 미확보 등) 메시지를 그대로 표면화(무목업·정직).
    let detail = `다운로드 실패 (HTTP ${res.status})`;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      /* 본문 비-JSON */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `persona-${personaKey}.${kind}`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/* ── 소형 표시 헬퍼 ── */

function Badge({ token, children }: { token: string; children: React.ReactNode }) {
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{
        color: token,
        background: `color-mix(in srgb, ${token} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${token} 38%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

function numFmt(v: unknown): string {
  if (typeof v === "number" && Number.isFinite(v)) return v.toLocaleString("ko-KR");
  return String(v ?? "—");
}

/* ── artifact 카드들(present 키만 렌더 — 무목업) ── */

/** 법정/조례/실효 3열 한 줄(렌더 헬퍼 — 컴포넌트 아님, 상태 없음). */
function zoneRow(label: string, v: Record<string, unknown>) {
  return (
    <div key={label} className="grid grid-cols-4 gap-2 text-[11px]">
      <span className="text-[var(--text-tertiary)]">{label}</span>
      <span className="text-[var(--text-secondary)]">법정 {v.legal != null ? numFmt(v.legal) : "—"}</span>
      <span className="text-[var(--text-secondary)]">조례 {v.ordinance != null ? numFmt(v.ordinance) : "—"}</span>
      <span className="font-bold text-[var(--text-primary)]">실효 {v.effective != null ? numFmt(v.effective) : "—"}</span>
    </div>
  );
}

function ZoneLimitsCard({ data }: { data: Record<string, unknown> }) {
  const far = (data.far ?? {}) as Record<string, unknown>;
  const bcr = (data.bcr ?? {}) as Record<string, unknown>;
  return (
    <ArtifactCard title="용도지역 한도(법정·조례·실효)">
      <div className="grid gap-1.5">
        {zoneRow("용적률(%)", far)}
        {zoneRow("건폐율(%)", bcr)}
      </div>
    </ArtifactCard>
  );
}

function DevMethodsCard({ data }: { data: unknown[] }) {
  const top = data.slice(0, 5) as { method?: string; score?: number; rank?: number }[];
  return (
    <ArtifactCard title="개발방식 판정(AHP 순위)">
      <ol className="grid gap-1">
        {top.map((m, i) => (
          <li key={i} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="text-[var(--text-primary)]">
              {m.rank ?? i + 1}. {m.method ?? "—"}
            </span>
            {m.score != null && (
              <span className="text-[var(--text-tertiary)]">{Number(m.score).toFixed(1)}점</span>
            )}
          </li>
        ))}
      </ol>
    </ArtifactCard>
  );
}

function IncentivesCard({ data }: { data: string[] }) {
  return (
    <ArtifactCard title="인센티브(종상향·용적완화)">
      <div className="flex flex-wrap gap-1.5">
        {data.map((s, i) => (
          <span
            key={i}
            className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-card)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]"
          >
            {s}
          </span>
        ))}
      </div>
    </ArtifactCard>
  );
}

function RoadmapCard({ data }: { data: unknown[] }) {
  const steps = data as { phase?: string; label?: string }[];
  return (
    <ArtifactCard title="인허가 로드맵">
      <ol className="grid gap-1.5">
        {steps.map((s, i) => (
          <li key={i} className="text-[11px]">
            <span className="mr-1.5 rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
              {s.phase ?? `단계 ${i + 1}`}
            </span>
            <span className="text-[var(--text-primary)]">{s.label ?? "—"}</span>
          </li>
        ))}
      </ol>
    </ArtifactCard>
  );
}

function IntegratedZoningCard({ data }: { data: Record<string, unknown> }) {
  const rows: { label: string; v: unknown }[] = [
    { label: "필지 수", v: data.parcel_count },
    { label: "통합면적(㎡)", v: data.total_area_sqm },
    { label: "지배 용도지역", v: data.dominant_zone },
    { label: "통합 실효 용적률(%)", v: data.blended_far_eff_pct },
    { label: "통합 실효 건폐율(%)", v: data.blended_bcr_eff_pct },
    { label: "통합 GFA(㎡)", v: data.integrated_gfa_sqm },
  ];
  return (
    <ArtifactCard title="다필지 통합 집계">
      <div className="grid gap-1">
        {rows
          .filter((r) => r.v != null)
          .map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="text-[var(--text-tertiary)]">{r.label}</span>
              <span className="font-bold text-[var(--text-primary)]">{numFmt(r.v)}</span>
            </div>
          ))}
      </div>
    </ArtifactCard>
  );
}

function PriceTiersCard({ data }: { data: unknown[] }) {
  const tiers = data as {
    label?: string;
    tier?: string;
    per_pyeong_10k?: number;
    premium_pct?: number;
  }[];
  return (
    <ArtifactCard title="적정분양가 tier(공급 평당가)">
      <div className="grid gap-1">
        {tiers.map((t, i) => (
          <div key={i} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="text-[var(--text-primary)]">
              {t.label ?? t.tier ?? "—"}
              {t.premium_pct != null && (
                <span className="ml-1 text-[var(--text-tertiary)]">(+{t.premium_pct}%)</span>
              )}
            </span>
            {t.per_pyeong_10k != null && (
              <span className="font-bold text-[var(--text-primary)]">
                {numFmt(t.per_pyeong_10k)}만원/평
              </span>
            )}
          </div>
        ))}
      </div>
    </ArtifactCard>
  );
}

function MarketReferenceCard({ data }: { data: Record<string, unknown> }) {
  const rows: { label: string; v: unknown }[] = [
    { label: "기준 범위", v: data.scope },
    { label: "주변 실거래 평당가(전용·만원)", v: data.market_pp_exclusive_10k },
    { label: "공급환산 평당가(만원)", v: data.market_pp_supply_10k },
  ];
  return (
    <ArtifactCard title="시장 기준(주변 실거래)">
      <div className="grid gap-1">
        {rows
          .filter((r) => r.v != null)
          .map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="text-[var(--text-tertiary)]">{r.label}</span>
              <span className="font-bold text-[var(--text-primary)]">{numFmt(r.v)}</span>
            </div>
          ))}
      </div>
    </ArtifactCard>
  );
}

function CostValidationCard({ data }: { data: Record<string, unknown> }) {
  const warning = typeof data.warning === "string" ? data.warning : null;
  return (
    <ArtifactCard title="원가 회수 검증(2차 가드)">
      {warning ? (
        <p className="inline-flex items-center gap-1.5 text-[11px] text-[var(--status-warning)]"><AlertTriangle className="size-3.5" aria-hidden />{warning}</p>
      ) : (
        <p className="text-[11px] text-[var(--status-success)]">시장가가 원가(공사비+간접)를 회수합니다.</p>
      )}
    </ArtifactCard>
  );
}

function ArtifactCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-card)] p-3">
      <p className="mb-2 text-xs font-bold text-[var(--text-primary)]">{title}</p>
      {children}
    </div>
  );
}

/** artifacts에서 존재하는 키만 골라 카드를 렌더(무목업 — 미확보 키는 생략). */
function ArtifactCards({ artifacts }: { artifacts: Record<string, unknown> }) {
  const cards: React.ReactNode[] = [];
  const a = artifacts;
  if (a.zone_limits && typeof a.zone_limits === "object")
    cards.push(<ZoneLimitsCard key="zone" data={a.zone_limits as Record<string, unknown>} />);
  if (Array.isArray(a.dev_methods) && a.dev_methods.length)
    cards.push(<DevMethodsCard key="dev" data={a.dev_methods} />);
  if (Array.isArray(a.incentives) && a.incentives.length)
    cards.push(<IncentivesCard key="inc" data={a.incentives as string[]} />);
  if (Array.isArray(a.permit_roadmap) && a.permit_roadmap.length)
    cards.push(<RoadmapCard key="road" data={a.permit_roadmap} />);
  if (a.integrated_zoning && typeof a.integrated_zoning === "object")
    cards.push(
      <IntegratedZoningCard key="intz" data={a.integrated_zoning as Record<string, unknown>} />,
    );
  if (Array.isArray(a.price_tiers) && a.price_tiers.length)
    cards.push(<PriceTiersCard key="tiers" data={a.price_tiers} />);
  if (a.market_reference && typeof a.market_reference === "object")
    cards.push(
      <MarketReferenceCard key="mref" data={a.market_reference as Record<string, unknown>} />,
    );
  if (a.cost_validation && typeof a.cost_validation === "object")
    cards.push(<CostValidationCard key="cost" data={a.cost_validation as Record<string, unknown>} />);
  if (!cards.length) return null;
  return <div className="grid gap-2 sm:grid-cols-2">{cards}</div>;
}

/** 백엔드 build_evidence_block 출력(verification.evidence_block) — 근거+법령링크 조인용. */
function EvidenceSection({ verification }: { verification: Record<string, unknown> }) {
  // verification.evidence_block = {evidence[], legal_refs[], provenance[], trust} (additive·없을 수 있음).
  const block = verification?.evidence_block as
    | { evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[] }
    | undefined
    | null;
  // adaptEvidence로 evidence[]+legal_refs[]를 EvidencePanel 소비형으로 합성(verified url만 링크).
  const items = adaptEvidence(block?.evidence, block?.legal_refs);
  // 근거 0건이면 렌더 안 함(빈 패널 방지·무목업).
  if (items.length === 0) return null;
  return <EvidencePanel title="산출 근거·법령" items={items} />;
}

/** verification(trust·expert_panel)·gate를 보조 칩으로 표면화(확정%는 status=confirmed일 때만). */
function VerificationChips({
  verification,
  gate,
  status,
}: {
  verification: Record<string, unknown>;
  gate: Record<string, unknown> | null;
  status: string;
}) {
  const chips: React.ReactNode[] = [];
  const trust = verification.trust as Record<string, unknown> | null | undefined;
  if (trust && trust.verdict) {
    const conf = typeof trust.confidence === "number" ? trust.confidence : null;
    // 확정% 표기는 status=confirmed일 때만(R12 — 잠정/일부는 % 억제).
    const showConf = status === "confirmed" && conf != null;
    chips.push(
      <span key="trust" className="rounded-full border border-[var(--line-strong)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
        교차검증 {String(trust.verdict)}
        {showConf ? ` · 신뢰도 ${Math.round((conf as number) * 100)}%` : ""}
      </span>,
    );
  }
  const expert = verification.expert_panel as Record<string, unknown> | null | undefined;
  if (expert && typeof expert.consensus === "string") {
    chips.push(
      <span key="expert" className="rounded-full border border-[var(--line-strong)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]">
        전문가 합의: {expert.consensus}
      </span>,
    );
  }
  if (gate && typeof gate.decision === "string" && gate.decision !== "PASS") {
    const tok = gate.decision === "BLOCK" ? "var(--status-error)" : "var(--status-info)";
    chips.push(
      <Badge key="gate" token={tok}>
        게이트 {gate.decision === "BLOCK" ? "차단" : "잠정"}
      </Badge>,
    );
  }
  if (!chips.length) return null;
  return <div className="flex flex-wrap items-center gap-1.5">{chips}</div>;
}

/* ── 메인 패널 ── */

export interface PersonaPanelProps {
  /** 가드/표시용 projectId(레이아웃 바인더가 store에 세팅한 값과 동일). */
  projectId: string;
  /** 실행 비활성(주소 미확보 등 — 상위가 판단). */
  runDisabled?: boolean;
}

export function PersonaPanel({ projectId, runDisabled = false }: PersonaPanelProps) {
  // ★읽기 소비만 — useProjectContextStore를 읽기만 하고 어떤 쓰기 액션도 호출하지 않는다.
  const boundProjectId = useProjectContextStore((s) => s.projectId);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  // 설계·시공 페르소나 입력원(SSOT). 설계 산출(연면적·건물유형)이 있으면 시공 견적·설계 매스에 공급.
  const designData = useProjectContextStore((s) => s.designData);

  const [personas, setPersonas] = useState<PersonaMeta[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [report, setReport] = useState<PersonaReport | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "pptx" | "docx" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  // AI 종합 서술 옵트인 — 기본 false(무과금 기본 정책 유지). 체크 시에만 use_llm 요청.
  const [useLlm, setUseLlm] = useState(false);
  // 결과 캐시(로컬 state만 — persist 미접촉). 입력 시그니처가 바뀌면 재실행을 권한다.
  const cacheRef = useRef<Record<string, { report: PersonaReport; sig: string }>>({});

  // GET /personas — 마운트 1회. apiClient.get은 JSON 파싱 반환.
  useEffect(() => {
    let alive = true;
    apiClient
      .get<{ personas: PersonaMeta[] }>("/personas", { useMock: false })
      .then((r) => {
        if (!alive) return;
        setPersonas(r?.personas ?? []);
      })
      .catch((e) => {
        if (!alive) return;
        setListError(
          e instanceof ApiClientError ? e.message : "전문가 목록을 불러오지 못했습니다.",
        );
        setPersonas([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  // SSOT 1회 캡처(읽기) — PersonaAnalyzeRequest 정합. bcode는 store에 없어 pnu[:10]에서 파생(없으면 null).
  const requestBody = useMemo<PersonaRequestBody>(() => {
    const pnu = siteAnalysis?.pnu ?? null;
    const bcode = pnu && pnu.length >= 10 ? pnu.slice(0, 10) : null;
    const parcels =
      siteAnalysis?.parcels
        ?.map((p) => p.address)
        .filter((x): x is string => typeof x === "string" && x.length > 0) ?? null;
    return {
      project_id: boundProjectId,
      site_id: null,
      address: siteAnalysis?.address ?? null,
      parcels: parcels && parcels.length ? parcels : null,
      bcode,
      pnu,
      equity_won: feasibilityData?.equityWon ?? null,
      // 설계·시공 입력 — SSOT 직접 읽기(미확보면 null → 백엔드가 정직 강등). 0 강제 금지(무목업).
      total_gfa_sqm:
        designData?.totalGfaSqm && designData.totalGfaSqm > 0 ? designData.totalGfaSqm : null,
      land_area_sqm:
        siteAnalysis?.landAreaSqm && siteAnalysis.landAreaSqm > 0 ? siteAnalysis.landAreaSqm : null,
      zone_code: siteAnalysis?.zoneCode ?? null,
      building_type: designData?.buildingType ?? null,
      // 하드코딩 false 해소 — 사용자 옵트인 토글(useLlm) 값을 그대로 전달.
      use_llm: useLlm,
    };
  }, [
    boundProjectId,
    siteAnalysis?.address,
    siteAnalysis?.pnu,
    siteAnalysis?.parcels,
    siteAnalysis?.landAreaSqm,
    siteAnalysis?.zoneCode,
    feasibilityData?.equityWon,
    designData?.totalGfaSqm,
    designData?.buildingType,
    useLlm,
  ]);

  // 입력 시그니처(캐시 키 변화 감지) — store의 currentSignature 발상 재사용.
  // 설계·시공 입력(연면적·대지면적·용도지역·건물유형)이 바뀌면 페르소나 결과를 stale 처리(재실행 유도).
  // L/D 접두어 = LLM 옵션 포함(SeniorConsultPanel 캐시키 발상 재사용) — 토글 전환 시 재실행 유도.
  const inputSig = useMemo(
    () =>
      `${useLlm ? "L" : "D"}|` +
      JSON.stringify([
        requestBody.address,
        requestBody.pnu,
        requestBody.parcels,
        requestBody.total_gfa_sqm,
        requestBody.land_area_sqm,
        requestBody.zone_code,
        requestBody.building_type,
      ]),
    [
      useLlm,
      requestBody.address,
      requestBody.pnu,
      requestBody.parcels,
      requestBody.total_gfa_sqm,
      requestBody.land_area_sqm,
      requestBody.zone_code,
      requestBody.building_type,
    ],
  );

  // 계정격리 + 주소(컨텍스트) 게이트 — OrchestrateWorkspaceClient.hasContext와 동일 발상.
  const hasContext =
    boundProjectId === projectId &&
    !!(siteAnalysis?.address || siteAnalysis?.pnu || requestBody.parcels?.length);

  const runPersona = useCallback(
    async (key: string) => {
      setRunError(null);
      setDownloadError(null);
      // ★계정격리: 다른 프로젝트 컨텍스트로는 호출하지 않는다(매 실행 직전 재확인).
      if (boundProjectId !== projectId || !hasContext) {
        setRunError("분석에는 부지(주소·PNU 또는 필지)가 필요합니다. 부지분석에서 먼저 등록하세요.");
        return;
      }
      // 캐시 적중(동일 입력) — 재실행 없이 즉시 표시.
      const cached = cacheRef.current[key];
      if (cached && cached.sig === inputSig) {
        setReport(cached.report);
        return;
      }
      setRunning(true);
      try {
        const res = await apiClient.post<PersonaReport>(`/personas/${key}/analyze`, {
          body: { ...requestBody },
          useMock: false,
        });
        cacheRef.current[key] = { report: res, sig: inputSig };
        setReport(res);
      } catch (e) {
        setReport(null);
        setRunError(
          e instanceof ApiClientError ? e.message : "전문가 분석에 실패했습니다.",
        );
      } finally {
        setRunning(false);
      }
    },
    [boundProjectId, projectId, hasContext, inputSig, requestBody],
  );

  const onSelect = useCallback(
    (key: string) => {
      setSelectedKey(key);
      setRunError(null);
      setDownloadError(null);
      // 선택 페르소나의 캐시가 현재 입력과 일치하면 결과 즉시 복원, 아니면 비운다(stale 표시 방지).
      const cached = cacheRef.current[key];
      setReport(cached && cached.sig === inputSig ? cached.report : null);
    },
    [inputSig],
  );

  const onDownload = useCallback(
    async (kind: "pdf" | "pptx" | "docx") => {
      if (!selectedKey) return;
      setDownloadError(null);
      setDownloading(kind);
      try {
        await downloadPersonaBlob(selectedKey, kind, { ...requestBody });
      } catch (e) {
        setDownloadError(e instanceof Error ? e.message : "다운로드에 실패했습니다.");
      } finally {
        setDownloading(null);
      }
    },
    [selectedKey, requestBody],
  );

  // 다운로드 게이트(personas.py): 주소+법정동코드 필요.
  // ★통합 보고서 생성엔진: 4종(도시/디벨로퍼/시공/설계)=PDF/PPTX/DOCX, 분양대행=PDF/PPTX.
  const ENGINE_PERSONAS = new Set(["urban_planner", "developer", "constructor", "designer"]);
  const hasAddrAndCode = !!requestBody.address && !!requestBody.bcode;
  const pdfDisabled = !hasAddrAndCode || downloading !== null;
  const pptxDisabled = !selectedKey || !hasAddrAndCode || downloading !== null;
  const docxSupported = !!selectedKey && ENGINE_PERSONAS.has(selectedKey);
  const docxDisabled = !docxSupported || !hasAddrAndCode || downloading !== null;

  const gate =
    report?.artifacts && typeof report.artifacts.gate === "object"
      ? (report.artifacts.gate as Record<string, unknown>)
      : null;

  // status 배지(게이트 BLOCK→차단·TENTATIVE→잠정 강등, R12).
  const statusView = useMemo(() => {
    if (gate?.decision === "BLOCK") return { label: "차단", token: "var(--status-error)" };
    if (gate?.decision === "TENTATIVE") return { label: "잠정", token: "var(--status-info)" };
    return STATUS_BADGE[report?.status ?? "partial"] ?? STATUS_BADGE.partial;
  }, [gate, report?.status]);

  return (
    <section className="grid gap-3">
      <div className="rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
        <p className="mb-1 text-sm font-bold text-[var(--text-primary)]">실무 전문가 분석</p>
        <p className="mb-3 text-[11px] text-[var(--text-secondary)]">
          분양대행·도시계획 전문가가 동일 부지 데이터로 실무 체크리스트·산출물을 정리합니다. 분석 항목은
          체크리스트로 미리 확인하고, 실행하면 핸드오프 보고서(PDF/PPT)로 받습니다.
        </p>

        {/* 페르소나 선택 카드 */}
        {listError && (
          <p className="mb-2 text-[11px] text-[var(--status-error)]">{listError}</p>
        )}
        {personas === null && !listError && (
          <p className="text-[11px] text-[var(--text-tertiary)]">전문가 목록 불러오는 중…</p>
        )}
        {personas && personas.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {personas.map((p) => {
              const active = selectedKey === p.key;
              return (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => onSelect(p.key)}
                  className={`rounded-xl border p-3 text-left transition-colors ${
                    active
                      ? "border-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)]"
                      : "border-[var(--line-strong)] bg-[var(--surface-card)] hover:border-[var(--accent-strong)]"
                  }`}
                >
                  <span className="block text-sm font-bold text-[var(--text-primary)]">
                    {p.name_ko}
                  </span>
                  <ul className="mt-1.5 grid gap-0.5">
                    {p.checklist.map((c) => (
                      <li key={c.step} className="truncate text-[10px] text-[var(--text-tertiary)]">
                        · {c.label}
                        {c.kpi ? ` (${c.kpi})` : ""}
                      </li>
                    ))}
                  </ul>
                </button>
              );
            })}
          </div>
        )}

        {/* 실행 버튼 */}
        {selectedKey && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={running || runDisabled || !hasContext}
              onClick={() => runPersona(selectedKey)}
              className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? "분석 중…" : report ? "다시 분석" : "분석 실행"}
            </button>
            {/* AI 종합 서술 옵트인(기본 off·무과금) — 공용 UseLlmToggle(전파방지). */}
            <UseLlmToggle
              checked={useLlm}
              onChange={setUseLlm}
              disabled={running}
              hint="LLM이 체크리스트·산출물을 자연어로 종합 · 미설정 시 무료"
            />
            {!hasContext && (
              <span className="text-[11px] text-[var(--text-tertiary)]">
                부지(주소·PNU 또는 필지)를 먼저 등록하세요.
              </span>
            )}
          </div>
        )}
        {runError && <p className="mt-2 text-[11px] text-[var(--status-error)]">{runError}</p>}
      </div>

      {/* 결과 */}
      {report && (
        <div className="grid gap-3 rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-card)] p-4">
          {/* 헤더: 이름 + status 배지 + 검증 칩 */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-[var(--text-primary)]">{report.name_ko}</span>
              <Badge token={statusView.token}>{statusView.label}</Badge>
            </div>
            <VerificationChips
              verification={report.verification ?? {}}
              gate={gate}
              status={report.status}
            />
          </div>

          {/* 정직 고지 배너(있을 때만) */}
          {report.honesty_notes && report.honesty_notes.length > 0 && (
            <div className="rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] p-3">
              <p className="mb-1 text-[11px] font-bold text-[var(--status-warning)]">정직 고지</p>
              <ul className="grid gap-0.5">
                {report.honesty_notes.map((n, i) => (
                  <li key={i} className="text-[11px] text-[var(--text-secondary)]">
                    · {n}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 게이트 차단 시 정직 disclosure(전체 개발규모 미제시) */}
          {gate?.decision === "BLOCK" && typeof gate.honest_disclosure === "string" && (
            <p className="rounded-xl border border-[color-mix(in_srgb,var(--status-error)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_10%,transparent)] p-3 text-[11px] text-[var(--status-error)]">
              {gate.honest_disclosure}
            </p>
          )}

          {/* 체크리스트 */}
          {report.checklist && report.checklist.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-xs font-bold text-[var(--text-primary)]">실무 체크리스트</p>
              {report.checklist.map((c) => {
                const badge = CHECKLIST_BADGE[c.status] ?? CHECKLIST_BADGE.missing;
                return (
                  <div
                    key={c.step}
                    className="flex items-start justify-between gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold text-[var(--text-primary)]">{c.label}</p>
                      {(c.kpi || c.note) && (
                        <p className="truncate text-[10px] text-[var(--text-tertiary)]">
                          {[c.kpi, c.note].filter(Boolean).join(" · ")}
                        </p>
                      )}
                    </div>
                    <Badge token={badge.token}>{badge.label}</Badge>
                  </div>
                );
              })}
            </div>
          )}

          {/* artifact 카드(존재 키만) */}
          <ArtifactCards artifacts={report.artifacts ?? {}} />

          {/* 산출 근거·법령링크(verification.evidence_block — 있을 때만, 무목업) */}
          <EvidenceSection verification={report.verification ?? {}} />

          {/* 다운로드 */}
          <div className="flex flex-wrap items-center gap-2 border-t border-[var(--line-strong)] pt-3">
            <button
              type="button"
              disabled={pdfDisabled}
              onClick={() => onDownload("pdf")}
              title={!hasAddrAndCode ? "주소·법정동코드 필요" : undefined}
              className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-card)] px-3.5 py-2 text-xs font-bold text-[var(--text-primary)] transition-colors hover:border-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {downloading === "pdf" ? "PDF 생성 중…" : "PDF 다운로드"}
            </button>
            <button
              type="button"
              disabled={pptxDisabled}
              onClick={() => onDownload("pptx")}
              title={!hasAddrAndCode ? "주소·법정동코드 필요" : undefined}
              className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-card)] px-3.5 py-2 text-xs font-bold text-[var(--text-primary)] transition-colors hover:border-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {downloading === "pptx" ? "PPTX 생성 중…" : "PPTX 다운로드"}
            </button>
            {docxSupported && (
              <button
                type="button"
                disabled={docxDisabled}
                onClick={() => onDownload("docx")}
                title={!hasAddrAndCode ? "주소·법정동코드 필요" : undefined}
                className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-card)] px-3.5 py-2 text-xs font-bold text-[var(--text-primary)] transition-colors hover:border-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {downloading === "docx" ? "Word 생성 중…" : "Word 다운로드"}
              </button>
            )}
            {!hasAddrAndCode && (
              <span className="text-[10px] text-[var(--text-tertiary)]">
                보고서는 주소·법정동코드(PNU)가 있어야 생성됩니다.
              </span>
            )}
          </div>
          {downloadError && (
            <p className="text-[11px] text-[var(--status-error)]">{downloadError}</p>
          )}
        </div>
      )}
    </section>
  );
}
