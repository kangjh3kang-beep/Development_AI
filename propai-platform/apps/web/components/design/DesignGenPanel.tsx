"use client";

/**
 * DesignGenPanel — AI 설계생성(검색·조합·인허가·근거) 패널.
 *
 * 백엔드 /api/v1/design-gen 파이프라인을 소비한다:
 *  - POST /ingest    : 설계파일(엑셀/DXF/IFC/PDF/이미지) 업로드 → 멀티모달 구조화·색인
 *  - POST /generate  : 부지조건 → 인허가 부합 설계안 Top-N(근거·법령링크 동반)
 *  - GET  /laws/coverage : 참조 법규 연결성·목록(근거)
 *
 * ★전역 원칙: 모든 산출물에 근거(EvidencePanel) + 법령링크(LegalRefChip). 미확보 값은
 * 정직 표기(가짜값 금지). AI 보조 초안 — 최종 인허가·설계 책임은 건축사.
 * 부지 면적/용도지역 기본값은 컨텍스트 스토어에서 시드(읽기 전용·store 미기록 → 무한렌더 회피).
 * 네트워크 호출은 버튼 클릭 시에만(자동 마운트 fetch·WebGL 없음 → 진입 멈춤 위험 없음).
 */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { NumberInput } from "@/components/common/NumberInput";

// WebGL/three 번들을 초기 로드에서 분리 — SSR 회피, 지연 마운트로 메인스레드 점유 방지.
const ProposalMassPreview = dynamic(
  () => import("./ProposalMassPreview").then((m) => m.ProposalMassPreview),
  { ssr: false },
);

/* ── 백엔드 계약 타입 ── */
type Confidence = "ordinance" | "statutory" | "rule" | "measured" | "estimated" | "unknown";

type Evidence = {
  claim: string;
  value?: string | number | boolean | null;
  basis?: string | null;
  source?: string | null;
  confidence?: Confidence | string | null;
  link?: string | null;
};

type IngestResult = {
  ok: boolean;
  drawing_type: string;
  source_format: string;
  content_hash: string;
  indexed: boolean;
  index_skip_reason: string | null;
  stored?: boolean;
  object_key?: string | null;
  store_skip_reason?: string | null;
  has_thumbnail?: boolean;
  warnings: string[];
  spec: Record<string, unknown>;
};

type BatchIngestResult = {
  ok: boolean;
  total: number;
  indexed: number;
  not_indexed: number;
  failed: number;
  results: {
    filename: string;
    ok: boolean;
    drawing_type?: string;
    content_hash?: string;
    indexed?: boolean;
    index_skip_reason?: string | null;
    stored?: boolean;
    store_skip_reason?: string | null;
    error?: string;
  }[];
};

type Candidate = {
  primary_drawing_type: string;
  primary_content_hash?: string | null;
  selected?: Record<string, string>;
  disciplines_covered?: string[];
  missing_disciplines?: string[];
  scale_factor: number | null;
  estimated_gfa_sqm: number | null;
  estimated_floors: number | null;
  estimated_units: number | null;
  estimated_parking: number | null;
  parking_required: number | null;
  parking_area_sqm: number | null;
  parking_basement_floors: number | null;
  parking_feasible: boolean | null;
  parking_layout?: {
    stalls_per_floor: number;
    floors_for_parking: number | null;
    footprint_w_m: number;
    footprint_d_m: number;
    stalls: { x: number; y: number; w: number; l: number }[];
    total_required: number;
    note: string;
  } | null;
  placement?: {
    site: { w: number; d: number };
    building: { x: number; y: number; w: number; d: number; area_sqm: number } | null;
    blocks?: { x: number; y: number; w: number; d: number }[];
    dong_count?: number;
    gap_m?: number;
    setback_m: number;
    buildable_region_sqm: number;
    setback_binds: boolean;
    note: string;
    notes: string[];
  } | null;
  compliant: boolean;
  score: number;
  warnings: string[];
};

type Verdict = {
  verdict: "pass" | "conditional" | "fail";
  compliant: boolean;
  permit_ok: boolean | null;
  notes: string[];
};

type Proposal = {
  candidate: Candidate;
  verdict: Verdict;
  evidence: Evidence[];
  ledger_hash?: string | null;  // 추천안 원장 적재 해시(피드백 큐레이션 조인키) — 추천안만 존재
};

type GenerateResult = {
  ok: boolean;
  site: {
    zone_code: string;
    area_sqm: number;
    buildable_footprint_sqm: number | null;
    max_gfa_sqm: number | null;
    max_floors_est: number | null;
    far_source: string;
    warnings: string[];
    evidence: Evidence[];
  };
  permit: { is_permitted?: boolean; permit_complexity?: number; reason?: string } | null;
  proposals: Proposal[];
  recommendation: { index: number; verdict: string } | null;
  verification?: {
    verdict: string;
    generated?: boolean;
    summary?: string;
    issues?: { severity?: string; note?: string; claim?: string; message?: string; detail?: string }[];
  } | null;
  interpretation?: {
    sections: Record<string, string>;
    input?: Record<string, unknown>;
  } | null;
  search_status: { count: number; skipped_reason: string | null };
  notes: string[];
};

type LawRecord = {
  key: string;
  law_name: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
  url_status?: string;
};

type LawsResult = {
  coverage: { ok: boolean; total_keys: number; resolved: number; unresolved: unknown[] };
  laws: LawRecord[];
};

type DrawingMatch = {
  point_id: string;
  score: number;
  drawing_type?: string | null;
  title?: string | null;
  total_area_sqm?: number | null;
  source_format?: string | null;
  summary?: string | null;
  content_hash?: string | null;
  stored?: boolean;
  has_thumbnail?: boolean;
  thumb_url?: string | null;
};

type SearchResult = { ok: boolean; results: DrawingMatch[]; count: number; skipped_reason: string | null };

/* ── 표시 헬퍼 ── */
const CONF_LABEL: Record<string, string> = {
  ordinance: "실효(조례)",
  statutory: "법정상한",
  rule: "규칙",
  measured: "실측",
  estimated: "추정",
  unknown: "미확인",
};

// 용적률 출처(far_source) 전용 라벨 — confidence enum과 의미 축이 다르므로 분리.
const FAR_SOURCE_LABEL: Record<string, string> = {
  ordinance: "실효(조례)",
  statutory: "법정상한",
  statutory_fallback: "법정(미지정 폴백)",
  unknown: "미확인",
};

const VERDICT_STYLE: Record<string, { label: string; color: string }> = {
  pass: { label: "적합", color: "var(--status-success)" },
  conditional: { label: "조건부", color: "var(--status-warning)" },
  fail: { label: "부적합", color: "var(--status-error)" },
};

// 도면 종류 한글 라벨(검색 필터·결과 표시용).
const DRAWING_TYPE_LABEL: Record<string, string> = {
  site_plan: "배치도",
  floor_plan: "평면도",
  section: "단면도",
  elevation: "입면도",
  parking: "주차설계",
  spec_sheet: "설계스펙",
  bim: "BIM",
  unknown: "미상",
};
const DRAWING_TYPE_OPTIONS = ["", "site_plan", "floor_plan", "section", "elevation", "parking"];

function fmtValue(v: Evidence["value"]): string | number {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "예" : "아니오";
  return v;
}

/** 백엔드 Evidence[] → EvidencePanel EvidenceItem[]. source/link를 법령칩으로 매핑. */
function toEvidenceItems(ev?: Evidence[]): EvidenceItem[] {
  return (ev ?? [])
    .filter((e) => e && e.claim)
    .map((e) => {
      const conf = e.confidence ? CONF_LABEL[String(e.confidence)] ?? String(e.confidence) : "";
      const basis = [e.basis?.trim(), conf ? `근거:${conf}` : ""].filter(Boolean).join(" · ");
      return {
        label: e.claim,
        value: fmtValue(e.value),
        basis: basis || null,
        legalRef: e.source || e.link ? { lawName: e.source || "근거", url: e.link ?? null } : null,
      };
    });
}

function errMessage(e: unknown): string {
  if (e instanceof ApiClientError) {
    if (e.status === 401 || e.status === 403) return "로그인이 필요합니다(또는 권한 없음).";
    return e.message || "요청 처리 중 오류가 발생했습니다.";
  }
  return "네트워크 오류 — 잠시 후 다시 시도해 주세요.";
}

/* ── 소형 표시 컴포넌트 ── */
function Metric({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">
        {value === null || value === undefined || value === "" ? "—" : value}
      </div>
    </div>
  );
}

// 주차 자동배치도(스키매틱) — footprint(m) 좌표를 SVG로 렌더. 최대 변 260px로 스케일.
function ParkingLayoutSvg({
  layout,
}: {
  layout: NonNullable<Candidate["parking_layout"]>;
}) {
  const w = layout.footprint_w_m;
  const d = layout.footprint_d_m;
  if (!(w > 0) || !(d > 0) || !layout.stalls?.length) return null;
  const scale = 260 / Math.max(w, d);
  return (
    <svg
      width={Math.round(w * scale)}
      height={Math.round(d * scale)}
      viewBox={`0 0 ${w} ${d}`}
      preserveAspectRatio="xMinYMin meet"
      className="mt-1 rounded border border-[var(--line)] bg-[var(--surface)]"
      role="img"
      aria-label="주차 자동배치도(스키매틱)"
    >
      <rect x={0} y={0} width={w} height={d} fill="none" stroke="var(--line)" strokeWidth={0.3} />
      {layout.stalls.map((s, i) => (
        <rect
          key={i}
          x={s.x}
          y={s.y}
          width={s.w}
          height={s.l}
          fill="var(--accent-soft)"
          stroke="var(--accent-strong)"
          strokeWidth={0.12}
        />
      ))}
    </svg>
  );
}

// 건물 배치 폴리곤(스키매틱) — 부지 경계 + 이격 가용영역 + 건물 footprint. 최대 변 260px.
function PlacementSvg({
  placement,
}: {
  placement: NonNullable<Candidate["placement"]>;
}) {
  const sw = placement.site.w;
  const sd = placement.site.d;
  if (!(sw > 0) || !(sd > 0)) return null;
  const s = placement.setback_m;
  // 동별 블록(다동) 우선 렌더, 없으면 단일 building으로 폴백.
  const blocks = placement.blocks?.length
    ? placement.blocks
    : placement.building
      ? [placement.building]
      : [];
  const scale = 260 / Math.max(sw, sd);
  return (
    <svg
      width={Math.round(sw * scale)}
      height={Math.round(sd * scale)}
      viewBox={`0 0 ${sw} ${sd}`}
      preserveAspectRatio="xMinYMin meet"
      className="mt-1 rounded border border-[var(--line)] bg-[var(--surface)]"
      role="img"
      aria-label="건물 배치 폴리곤(스키매틱)"
    >
      {/* 부지 경계 */}
      <rect x={0} y={0} width={sw} height={sd} fill="none" stroke="var(--text-tertiary)" strokeWidth={0.4} />
      {/* 이격 가용영역(점선) */}
      {sw - 2 * s > 0 && sd - 2 * s > 0 && (
        <rect
          x={s}
          y={s}
          width={sw - 2 * s}
          height={sd - 2 * s}
          fill="none"
          stroke="var(--line)"
          strokeWidth={0.25}
          strokeDasharray="1 1"
        />
      )}
      {/* 동별 footprint(다동 단지면 여러 개) */}
      {blocks.map((b, i) => (
        <rect
          key={`${b.x}-${b.y}-${i}`}
          x={b.x}
          y={b.y}
          width={b.w}
          height={b.d}
          fill="var(--accent-soft)"
          stroke="var(--accent-strong)"
          strokeWidth={0.4}
        />
      ))}
    </svg>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const s = VERDICT_STYLE[verdict] ?? { label: verdict, color: "var(--text-tertiary)" };
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold text-white"
      style={{ backgroundColor: s.color }}
    >
      {s.label}
    </span>
  );
}

type Props = { projectId?: string | null };

export function DesignGenPanel({ projectId }: Props) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const updateDesignData = useProjectContextStore((s) => s.updateDesignData);
  const markStageComplete = useProjectContextStore((s) => s.markStageComplete);

  // 부지 컨텍스트 기본값(1회 시드 — store 미기록).
  const [areaSqm, setAreaSqm] = useState<number>(() => {
    const a = effectiveLandAreaSqm(siteAnalysis);
    return a && a > 0 ? Math.round(a) : 1000;
  });
  const [zoneCode, setZoneCode] = useState<string>(() => siteAnalysis?.zoneCode || "2R");
  // 용도지역명은 store에 별도 평탄 필드가 없어 빈값 시드(정직 — 사용자가 인허가용 정식 명칭 입력).
  const [zoneName, setZoneName] = useState<string>("");
  const [sigungu, setSigungu] = useState<string>("");
  const [buildingUse, setBuildingUse] = useState<string>("공동주택");
  const [avgUnit, setAvgUnit] = useState<number>(84);
  const [topN, setTopN] = useState<number>(3);
  const [verifyOpt, setVerifyOpt] = useState<boolean>(false);  // AI 검증 포함(선택형)
  const [interpretOpt, setInterpretOpt] = useState<boolean>(false);  // AI 설계 해석 포함(선택형)

  // 업로드(ingest)
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [ingest, setIngest] = useState<IngestResult | null>(null);
  const [ingestErr, setIngestErr] = useState<string | null>(null);
  // 콜드스타트 배치 업로드(표준설계 일괄적재)
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchUploading, setBatchUploading] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchIngestResult | null>(null);
  const [batchErr, setBatchErr] = useState<string | null>(null);

  // 생성(generate)
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [genErr, setGenErr] = useState<string | null>(null);

  // 법규(laws)
  const [laws, setLaws] = useState<LawsResult | null>(null);
  const [lawsLoading, setLawsLoading] = useState(false);
  const [lawsErr, setLawsErr] = useState<string | null>(null);

  // 도면 분류 택소노미(백엔드 단일 출처 — 실무 전수조사 반영). 분야별 그룹.
  const [taxonomy, setTaxonomy] = useState<Record<string, { code: string; ko: string }[]>>({});
  useEffect(() => {
    let alive = true;
    apiClient
      .get<{ by_discipline: Record<string, { code: string; ko: string }[]> }>(
        "/design-gen/drawing-types",
      )
      .then((d) => {
        if (alive) setTaxonomy(d?.by_discipline ?? {});
      })
      .catch(() => {
        /* 실패 시 정적 폴백 라벨/옵션 사용(아래) */
      });
    return () => {
      alive = false;
    };
  }, []);
  // code → 한국어명(택소노미 우선, 없으면 정적 폴백/코드).
  function labelOf(code?: string | null): string {
    if (!code) return "미상";
    for (const items of Object.values(taxonomy)) {
      const hit = items.find((i) => i.code === code);
      if (hit) return hit.ko;
    }
    return DRAWING_TYPE_LABEL[code] ?? code;
  }

  // 설계 코퍼스 현황(축적 가시화) — 분야별 누적 도면 수.
  const [corpus, setCorpus] = useState<{ total: number; by_discipline: Record<string, number> } | null>(null);
  async function refreshCorpus() {
    try {
      const d = await apiClient.get<{ total: number; by_discipline: Record<string, number> }>(
        "/design-gen/corpus-stats",
      );
      setCorpus({ total: d?.total ?? 0, by_discipline: d?.by_discipline ?? {} });
    } catch {
      /* 미가용 시 미표시(정직) */
    }
  }
  useEffect(() => {
    void refreshCorpus();
  }, []);

  // 유사 도면 검색(search)
  const [searchType, setSearchType] = useState<string>("");
  const [searchKeywords, setSearchKeywords] = useState<string>("");
  const [searchRes, setSearchRes] = useState<SearchResult | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  // 추천안 적용(모세혈관 SSOT 반영) — 적용된 설계안 인덱스.
  const [appliedIdx, setAppliedIdx] = useState<number | null>(null);
  // 설계안 피드백(👍👎) — 자가학습 신호(인덱스→verdict).
  const [feedback, setFeedback] = useState<Record<number, "up" | "down">>({});
  // 3D 매스 프리뷰 토글(추천 카드 전용) — per-proposal 독립 토글.
  const [show3d, setShow3d] = useState<Record<number, boolean>>({});

  async function handleIngest() {
    if (!file) return;
    setUploading(true);
    setIngestErr(null);
    setIngest(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (projectId) form.append("project_id", projectId);
      const data = await apiClient.post<IngestResult>("/design-gen/ingest", { body: form });
      setIngest(data);
      refreshCorpus();  // 색인 후 코퍼스 현황 갱신
    } catch (e) {
      setIngestErr(errMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleBatchIngest() {
    if (batchFiles.length === 0) return;
    setBatchUploading(true);
    setBatchErr(null);
    setBatchResult(null);
    try {
      const form = new FormData();
      for (const f of batchFiles) form.append("files", f);
      if (projectId) form.append("project_id", projectId);
      const data = await apiClient.post<BatchIngestResult>("/design-gen/ingest-batch", { body: form });
      setBatchResult(data);
      refreshCorpus();  // 일괄 색인 후 코퍼스 현황 갱신
    } catch (e) {
      setBatchErr(errMessage(e));
    } finally {
      setBatchUploading(false);
    }
  }

  async function handleGenerate() {
    setLoading(true);
    setGenErr(null);
    setResult(null);
    setAppliedIdx(null);
    setFeedback({});
    setShow3d({});
    try {
      const data = await apiClient.post<GenerateResult>("/design-gen/generate", {
        body: {
          area_sqm: areaSqm,
          zone_code: zoneCode || "2R",
          zone_name: zoneName || null,
          sigungu: sigungu || null,
          building_use: buildingUse || null,
          avg_unit_area_sqm: avgUnit,
          top_n: topN,
          project_id: projectId || null,
          verify: verifyOpt,
          interpret: interpretOpt,
        },
      });
      setResult(data);
    } catch (e) {
      setGenErr(errMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleLaws() {
    setLawsLoading(true);
    setLawsErr(null);
    try {
      const q = sigungu ? `?sigungu=${encodeURIComponent(sigungu)}` : "";
      const data = await apiClient.get<LawsResult>(`/design-gen/laws/coverage${q}`);
      setLaws(data);
    } catch (e) {
      setLawsErr(errMessage(e));
    } finally {
      setLawsLoading(false);
    }
  }

  async function handleSearch() {
    setSearchLoading(true);
    setSearchErr(null);
    setSearchRes(null);
    try {
      const data = await apiClient.post<SearchResult>("/design-gen/search", {
        body: {
          drawing_type: searchType || null,
          area_sqm: areaSqm > 0 ? areaSqm : null,
          keywords: searchKeywords || "",
          top_k: 8,
        },
      });
      setSearchRes(data);
    } catch (e) {
      setSearchErr(errMessage(e));
    } finally {
      setSearchLoading(false);
    }
  }

  // 원본/썸네일 조회 — 서버가 인증 테넌트로 presigned URL 발급(클라이언트 키 미전송) → 새 탭.
  async function handleOpenOriginal(contentHash: string, variant: "original" | "thumb" = "original") {
    try {
      const q = variant === "thumb" ? "?variant=thumb" : "";
      const data = await apiClient.get<{ url: string }>(
        `/design-gen/drawings/${encodeURIComponent(contentHash)}/url${q}`,
      );
      if (data?.url) window.open(data.url, "_blank", "noopener,noreferrer");
    } catch {
      // 미보관/미설정 등은 정직 무시(버튼은 stored/has_thumbnail일 때만 노출).
    }
  }

  // 추천 설계안 → 모세혈관 SSOT 반영(클릭 1회 쓰기 — 렌더 중 쓰기 아님 → 무한렌더 무관).
  // 하류(공사비·수지)가 읽는 핵심 필드만 정직 매핑. 미산출 값은 null(가짜값 금지).
  function handleApply(c: Candidate, idx: number) {
    if (!c.estimated_gfa_sqm || c.estimated_gfa_sqm <= 0) return; // 적용할 연면적 없음
    // far 분모는 백엔드가 한도 산정에 쓴 면적 우선(사용자가 입력란을 바꿔도 결과와 정합).
    const denom = result?.site.area_sqm ?? areaSqm;
    const far = denom > 0 ? Math.round((c.estimated_gfa_sqm / denom) * 100) : null;
    updateDesignData({
      totalGfaSqm: c.estimated_gfa_sqm,
      floorCount: c.estimated_floors,
      buildingType: buildingUse || "공동주택",
      bcr: null, // 후보엔 건축면적비 직접 산출 없음 → 정직 null(하류 영향 시 별도 산정)
      far,
      unitCount: c.estimated_units ?? null,
      unitTypes: null,
      efficiencyPct: null,
    });
    markStageComplete("design");
    setAppliedIdx(idx);
  }

  // 설계안 피드백(👍👎) → 기존 성장 피드백 엔드포인트(ai_feedback 적재, 사람승인 게이트).
  // service별 down율 집계(compute_down_rates)로 개선대상(design_orchestrator) 식별 +
  // ★추천안은 ledger_hash(원장 적재 해시)로 키잉 → curate_few_shot이 우수 제안안을
  //   few-shot 예시로 큐레이션(사람 승인 게이트). 미적재(원장 해시 없음)면 도면해시로 정직 폴백.
  async function handleFeedback(
    idx: number, c: Candidate, verdict: "up" | "down", ledgerHash?: string | null,
  ) {
    let correction: string | null = null;
    if (verdict === "down" && typeof window !== "undefined") {
      correction = window.prompt("개선 의견(선택):")?.trim() || null;
    }
    try {
      await apiClient.post("/growth/feedback", {
        body: {
          target_type: "recommendation",
          verdict,
          service: "design_orchestrator",
          // 제안안 단위 큐레이션 우선(원장 해시) → 없으면 주 도면 해시 폴백.
          content_hash: ledgerHash || c.primary_content_hash || null,
          correction,
        },
      });
      setFeedback((f) => ({ ...f, [idx]: verdict }));
    } catch {
      // 피드백 전송 실패는 조용히 무시(본 기능 비차단).
    }
  }

  return (
    <Card>
      <CardContent className="space-y-5 p-5">
        <div>
          <CardTitle className="flex items-center gap-2">
            🏗️ AI 설계생성 <span className="text-xs font-normal text-[var(--text-tertiary)]">검색·조합·인허가·근거</span>
          </CardTitle>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            부지조건으로 인허가 부합 설계안 초안을 생성하고, 모든 산출에 근거·법령링크를 제공합니다.
            AI 보조 초안 — 최종 인허가·설계 책임은 건축사입니다.
          </p>
        </div>

        {/* 부지 조건 입력 */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            대지면적(㎡)
            <NumberInput value={areaSqm} onChange={(v) => setAreaSqm(Math.max(0, v ?? 0))} allowDecimal />
          </label>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            용도지역코드
            <input
              value={zoneCode}
              onChange={(e) => setZoneCode(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
          </label>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            용도지역명(선택)
            <input
              value={zoneName}
              onChange={(e) => setZoneName(e.target.value)}
              placeholder="예: 제2종일반주거지역"
              className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
          </label>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            시군구(조례링크·선택)
            <input
              value={sigungu}
              onChange={(e) => setSigungu(e.target.value)}
              placeholder="예: 서울특별시"
              className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
          </label>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            건축용도
            <input
              value={buildingUse}
              onChange={(e) => setBuildingUse(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
          </label>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            평균 평형(㎡)
            <NumberInput value={avgUnit} onChange={(v) => setAvgUnit(Math.max(0, v ?? 0))} allowDecimal />
          </label>
          <label className="text-xs font-semibold text-[var(--text-secondary)]">
            설계안 개수
            <NumberInput value={topN} onChange={(v) => setTopN(Math.max(1, Math.min(v ?? 1, 10)))} />
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={handleGenerate} disabled={loading || areaSqm <= 0 || avgUnit <= 0}>
            {loading ? "생성 중…" : "설계안 생성"}
          </Button>
          <Button variant="secondary" onClick={handleLaws} disabled={lawsLoading}>
            {lawsLoading ? "조회 중…" : "참조 법규 보기"}
          </Button>
          <label className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
            <input type="checkbox" checked={verifyOpt} onChange={(e) => setVerifyOpt(e.target.checked)} />
            AI 검증 포함(추천안 독립검증 · LLM 호출)
          </label>
          <label className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
            <input type="checkbox" checked={interpretOpt} onChange={(e) => setInterpretOpt(e.target.checked)} />
            AI 설계 해석 포함(추천안 6섹션 · LLM 호출)
          </label>
        </div>
        {genErr && <p className="text-xs text-[var(--status-error)]">{genErr}</p>}

        {/* 도면 업로드(ingest) */}
        <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-semibold text-[var(--text-secondary)]">
              📐 설계파일 업로드 <span className="font-normal text-[var(--text-tertiary)]">xlsx · dxf · ifc · pdf · png · jpg · webp (최대 25MB)</span>
            </div>
            {corpus && corpus.total > 0 && (
              <div className="text-[11px] text-[var(--text-tertiary)]">
                축적 도면 <span className="font-bold text-[var(--accent-strong)]">{corpus.total.toLocaleString()}</span>건
                {Object.keys(corpus.by_discipline).length > 0 &&
                  ` · ${Object.entries(corpus.by_discipline).map(([d, n]) => `${d} ${n}`).join(", ")}`}
              </div>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              type="file"
              accept=".xlsx,.xlsm,.xls,.dxf,.ifc,.pdf,.png,.jpg,.jpeg,.webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-xs text-[var(--text-secondary)]"
            />
            <Button variant="secondary" onClick={handleIngest} disabled={!file || uploading}>
              {uploading ? "업로드 중…" : "업로드·색인"}
            </Button>
          </div>
          {ingestErr && <p className="mt-2 text-xs text-[var(--status-error)]">{ingestErr}</p>}
          {ingest && (
            <div className="mt-2 text-xs text-[var(--text-secondary)]">
              <span className="font-bold text-[var(--text-primary)]">{labelOf(ingest.drawing_type)}</span> · {ingest.source_format} ·{" "}
              {ingest.indexed ? (
                <span style={{ color: "var(--status-success)" }}>색인 완료</span>
              ) : (
                <span style={{ color: "var(--status-warning)" }}>미색인({ingest.index_skip_reason || "사유 미상"})</span>
              )}
              {ingest.stored ? (
                <>
                  {" · "}
                  <span style={{ color: "var(--status-success)" }}>원본 보관</span>
                  {ingest.content_hash && (
                    <button
                      type="button"
                      onClick={() => handleOpenOriginal(ingest.content_hash)}
                      className="ml-1 font-semibold text-[var(--accent-strong)] underline"
                    >
                      원본 보기
                    </button>
                  )}
                  {ingest.has_thumbnail && ingest.content_hash && (
                    <button
                      type="button"
                      onClick={() => handleOpenOriginal(ingest.content_hash, "thumb")}
                      className="ml-1 font-semibold text-[var(--accent-strong)] underline"
                    >
                      미리보기
                    </button>
                  )}
                </>
              ) : (
                <span className="text-[var(--text-tertiary)]"> · 원본 미보관({ingest.store_skip_reason || "사유 미상"})</span>
              )}
              {ingest.warnings?.length > 0 && (
                <ul className="mt-1 list-inside list-disc text-[var(--text-tertiary)]">
                  {ingest.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 콜드스타트 배치 업로드 — 표준설계 다중 파일 일괄 적재(코퍼스 부트스트랩) */}
          <div className="mt-3 border-t border-dashed border-[var(--line)] pt-3">
            <div className="text-[11px] font-semibold text-[var(--text-secondary)]">
              📦 일괄 업로드 <span className="font-normal text-[var(--text-tertiary)]">표준설계 다중 파일을 한 번에 색인(콜드스타트 · 최대 50개)</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input
                type="file"
                multiple
                accept=".xlsx,.xlsm,.xls,.dxf,.ifc,.pdf,.png,.jpg,.jpeg,.webp"
                onChange={(e) => setBatchFiles(e.target.files ? Array.from(e.target.files) : [])}
                className="text-xs text-[var(--text-secondary)]"
              />
              <Button
                variant="secondary"
                onClick={handleBatchIngest}
                disabled={batchFiles.length === 0 || batchUploading}
              >
                {batchUploading ? `업로드 중…(${batchFiles.length})` : `일괄 색인(${batchFiles.length})`}
              </Button>
            </div>
            {batchErr && <p className="mt-2 text-xs text-[var(--status-error)]">{batchErr}</p>}
            {batchResult && (
              <div className="mt-2 text-xs text-[var(--text-secondary)]">
                총 <span className="font-bold text-[var(--text-primary)]">{batchResult.total}</span>건 ·{" "}
                <span style={{ color: "var(--status-success)" }}>색인 {batchResult.indexed}</span>
                {batchResult.not_indexed > 0 && (
                  <span style={{ color: "var(--status-warning)" }}> · 미색인 {batchResult.not_indexed}</span>
                )}
                {batchResult.failed > 0 && (
                  <span style={{ color: "var(--status-error)" }}> · 실패 {batchResult.failed}</span>
                )}
                <ul className="mt-1 max-h-40 overflow-auto list-inside list-disc text-[var(--text-tertiary)]">
                  {batchResult.results.map((r, i) => (
                    <li key={`${r.filename}-${i}`}>
                      <span className="text-[var(--text-secondary)]">{i + 1}. {r.filename || "(이름없음)"}</span>
                      {r.ok ? (
                        r.indexed ? (
                          <span style={{ color: "var(--status-success)" }}> — {labelOf(r.drawing_type || "")} 색인</span>
                        ) : (
                          <span style={{ color: "var(--status-warning)" }}> — 미색인({r.index_skip_reason || "사유 미상"})</span>
                        )
                      ) : (
                        <span style={{ color: "var(--status-error)" }}> — 실패({r.error || "사유 미상"})</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* 유사 도면 검색(search) */}
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="text-xs font-semibold text-[var(--text-secondary)]">
            🔍 유사 도면 검색 <span className="font-normal text-[var(--text-tertiary)]">업로드된 도면을 유형·면적({areaSqm.toLocaleString()}㎡)·키워드로 조회</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <select
              value={searchType}
              onChange={(e) => setSearchType(e.target.value)}
              className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            >
              <option value="">전체 유형</option>
              {Object.keys(taxonomy).length > 0
                ? Object.entries(taxonomy).map(([disc, items]) => (
                    <optgroup key={disc} label={disc}>
                      {items.map((it) => (
                        <option key={it.code} value={it.code}>
                          {it.ko}
                        </option>
                      ))}
                    </optgroup>
                  ))
                : DRAWING_TYPE_OPTIONS.filter(Boolean).map((t) => (
                    <option key={t} value={t}>
                      {DRAWING_TYPE_LABEL[t] ?? t}
                    </option>
                  ))}
            </select>
            <input
              value={searchKeywords}
              onChange={(e) => setSearchKeywords(e.target.value)}
              placeholder="키워드(선택)"
              className="min-w-[140px] flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
            <Button variant="secondary" onClick={handleSearch} disabled={searchLoading}>
              {searchLoading ? "검색 중…" : "유사 도면 검색"}
            </Button>
          </div>
          {searchErr && <p className="mt-2 text-xs text-[var(--status-error)]">{searchErr}</p>}
          {searchRes && (
            <div className="mt-2">
              {searchRes.results.length === 0 ? (
                <p className="text-xs text-[var(--text-tertiary)]">
                  일치하는 도면이 없습니다{searchRes.skipped_reason ? `(${searchRes.skipped_reason})` : ""}. 도면을 업로드하면 검색됩니다.
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {searchRes.results.map((m, idx) => (
                    <div key={`${m.point_id}-${idx}`} className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-[var(--text-primary)]">
                          {labelOf(m.drawing_type)}
                          {m.title ? ` · ${m.title}` : ""}
                        </span>
                        <span className="text-[var(--text-tertiary)]">유사 {(m.score * 100).toFixed(0)}</span>
                      </div>
                      <div className="mt-0.5 text-[var(--text-secondary)]">
                        {m.total_area_sqm != null ? `${m.total_area_sqm.toLocaleString()}㎡` : "면적 미상"}
                        {m.source_format ? ` · ${m.source_format}` : ""}
                      </div>
                      {m.thumb_url && (
                        // 저해상 프록시(presigned·단기·동적 외부 URL) 인라인 미리보기 — 원본 대신
                        // 작은 썸네일만 조회. next/image는 단기 presigned·임의 R2 호스트에 부적합(plain img).
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={m.thumb_url}
                          alt={m.title || "도면 미리보기"}
                          loading="lazy"
                          onError={(e) => {
                            // presigned 만료(600초)·일시오류 시 깨진 이미지 대신 숨김(정직).
                            e.currentTarget.style.display = "none";
                          }}
                          className="mt-1.5 max-h-32 w-full rounded-md border border-[var(--line)] object-contain"
                        />
                      )}
                      {m.summary && <div className="mt-1 line-clamp-2 text-[var(--text-tertiary)]">{m.summary}</div>}
                      {m.stored && m.content_hash && (
                        <button
                          type="button"
                          onClick={() => handleOpenOriginal(m.content_hash as string)}
                          className="mt-1 font-semibold text-[var(--accent-strong)] underline"
                        >
                          원본 보기
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 생성 결과 */}
        {result && (
          <div className="space-y-4">
            {/* 부지 법적 한도 */}
            <div>
              <div className="mb-2 text-xs font-bold text-[var(--text-secondary)]">부지 법적 한도</div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Metric label="건축면적" value={result.site.buildable_footprint_sqm ? `${result.site.buildable_footprint_sqm.toLocaleString()}㎡` : null} />
                <Metric label="최대 연면적" value={result.site.max_gfa_sqm ? `${result.site.max_gfa_sqm.toLocaleString()}㎡` : null} />
                <Metric label="최대 층수(추정)" value={result.site.max_floors_est} />
                <Metric label="용적률 출처" value={FAR_SOURCE_LABEL[result.site.far_source] ?? result.site.far_source} />
              </div>
              <EvidencePanel title="부지 한도 근거" items={toEvidenceItems(result.site.evidence)} className="mt-2" defaultOpen={false} />
              {result.site.warnings?.length > 0 && (
                <ul className="mt-1 list-inside list-disc text-[11px] text-[var(--text-tertiary)]">
                  {result.site.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
            </div>

            {/* 인허가 */}
            {result.permit && (
              <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-xs">
                <span className="font-semibold text-[var(--text-secondary)]">인허가 가능성: </span>
                <span className="font-bold" style={{ color: result.permit.is_permitted ? "var(--status-success)" : "var(--status-error)" }}>
                  {result.permit.is_permitted ? "가능" : "불가/미확인"}
                </span>
                {result.permit.reason && <span className="text-[var(--text-tertiary)]"> — {result.permit.reason}</span>}
              </div>
            )}

            {/* 독립 검증 결과(선택형) — 추천안 할루시네이션/계산오류 검증·정직고지 */}
            {result.verification && (
              <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-xs">
                <span className="font-semibold text-[var(--text-secondary)]">독립 검증: </span>
                <span
                  className="font-bold"
                  style={{
                    color:
                      result.verification.verdict === "pass"
                        ? "var(--status-success)"
                        : result.verification.verdict === "warn"
                          ? "var(--status-warning)"
                          : result.verification.verdict === "fail"
                            ? "var(--status-error)"
                            : "var(--text-tertiary)",
                  }}
                >
                  {result.verification.verdict === "pass"
                    ? "이상 없음"
                    : result.verification.verdict === "warn"
                      ? "주의"
                      : result.verification.verdict === "fail"
                        ? "오류 의심"
                        : "확인 필요"}
                </span>
                {result.verification.summary && (
                  <span className="text-[var(--text-tertiary)]"> — {result.verification.summary}</span>
                )}
                {result.verification.generated === false && (
                  <span className="text-[var(--text-hint)]"> (규칙기반)</span>
                )}
                {result.verification.issues?.length ? (
                  <ul className="mt-1 list-inside list-disc text-[var(--text-tertiary)]">
                    {result.verification.issues.slice(0, 6).map((it, i) => (
                      <li key={i}>
                        [{it.severity || "info"}] {it.note || it.claim || it.message || it.detail || ""}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )}

            {/* AI 설계 해석(선택형) — 추천안 6섹션(왜 이 매스인지·법규부합·개선) */}
            {result.interpretation?.sections && (
              <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2.5 text-xs">
                <div className="mb-1.5 font-semibold text-[var(--text-secondary)]">
                  AI 설계 해석 <span className="text-[var(--text-hint)]">(추천안 · LLM)</span>
                </div>
                <dl className="space-y-1.5">
                  {(
                    [
                      ["design_overview", "설계 개요"],
                      ["mass_strategy", "매스 전략"],
                      ["floor_efficiency", "평면 효율"],
                      ["compliance_review", "법규 준수"],
                      ["circulation_core", "동선·코어"],
                      ["improvement", "개선 제안"],
                    ] as const
                  )
                    .filter(([k]) => (result.interpretation?.sections?.[k] || "").trim())
                    .map(([k, label]) => (
                      <div key={k}>
                        <dt className="font-medium text-[var(--accent-strong)]">{label}</dt>
                        <dd className="text-[var(--text-tertiary)] whitespace-pre-line">
                          {result.interpretation?.sections?.[k]}
                        </dd>
                      </div>
                    ))}
                </dl>
                <div className="mt-1.5 text-[var(--text-hint)]">
                  AI 보조 해석 — 수치는 추천안 데이터 기준, 최종 설계·인허가 책임은 건축사.
                </div>
              </div>
            )}

            {/* 제안 카드 */}
            <div className="space-y-3">
              <div className="text-xs font-bold text-[var(--text-secondary)]">
                설계안 {result.proposals.length}건
                {result.recommendation && (
                  <span className="ml-2 text-[var(--accent-strong)]">· 추천: #{result.recommendation.index + 1}</span>
                )}
              </div>
              {result.proposals.length === 0 && (
                <p className="text-xs text-[var(--text-tertiary)]">
                  생성된 설계안이 없습니다. {result.search_status?.count === 0 ? "참조 도면을 업로드하면 초안이 생성됩니다." : ""}
                </p>
              )}
              {result.proposals.map((p, i) => {
                const c = p.candidate;
                const isRec = result.recommendation?.index === i;
                return (
                  <div
                    key={i}
                    className="rounded-xl border bg-[var(--surface)] p-4"
                    style={{ borderColor: isRec ? "var(--accent-strong)" : "var(--line)" }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-[var(--text-primary)]">설계안 #{i + 1}</span>
                        <VerdictBadge verdict={p.verdict.verdict} />
                        {isRec && <span className="text-[11px] font-bold text-[var(--accent-strong)]">추천</span>}
                      </div>
                      <span className="text-[11px] text-[var(--text-tertiary)]">점수 {(c.score * 100).toFixed(0)}</span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                      <Metric label="연면적" value={c.estimated_gfa_sqm ? `${c.estimated_gfa_sqm.toLocaleString()}㎡` : null} />
                      <Metric label="층수" value={c.estimated_floors} />
                      <Metric label="세대수" value={c.estimated_units} />
                      <Metric label="주차" value={c.parking_required != null ? `${c.parking_required}대` : null} />
                    </div>
                    {/* 주차설계 상세 */}
                    {c.parking_required != null && (
                      <div className="mt-2 text-[11px] text-[var(--text-secondary)]">
                        주차 {c.parking_required}대
                        {c.parking_area_sqm != null && ` · 소요면적 ${c.parking_area_sqm.toLocaleString()}㎡`}
                        {c.parking_basement_floors != null && ` · 지하 약 ${c.parking_basement_floors}층`}
                        {c.parking_feasible != null && (
                          <span style={{ color: c.parking_feasible ? "var(--status-success)" : "var(--status-error)" }}>
                            {" "}· 배치 {c.parking_feasible ? "현실적" : "비현실(재검토)"}
                          </span>
                        )}
                      </div>
                    )}
                    {/* 주차 자동배치도(스키매틱) */}
                    {c.parking_layout && c.parking_layout.stalls_per_floor > 0 && (
                      <div className="mt-2 text-[11px] text-[var(--text-secondary)]">
                        주차 자동배치(스키매틱): 층당 {c.parking_layout.stalls_per_floor}대 ·{" "}
                        {c.parking_layout.floors_for_parking}개층
                        <ParkingLayoutSvg layout={c.parking_layout} />
                        {c.parking_layout.stalls.length < c.parking_layout.stalls_per_floor && (
                          <span className="text-[var(--text-hint)]">
                            배치도는 대표 {c.parking_layout.stalls.length}구획만 표시(전체 층당 {c.parking_layout.stalls_per_floor}대).{" "}
                          </span>
                        )}
                        <span className="text-[var(--text-hint)]">{c.parking_layout.note}</span>
                      </div>
                    )}
                    {/* 건물 배치 폴리곤(스키매틱) — 부지 경계+이격+건물 footprint */}
                    {c.placement && (
                      <div className="mt-2 text-[11px] text-[var(--text-secondary)]">
                        건물 배치(스키매틱): 부지 {c.placement.site.w}×{c.placement.site.d}m · 이격 {c.placement.setback_m}m
                        {c.placement.dong_count && c.placement.dong_count > 1
                          ? ` · ${c.placement.dong_count}개 동(동간거리 ${c.placement.gap_m}m)`
                          : c.placement.building
                            ? ` · 건물 ${c.placement.building.w}×${c.placement.building.d}m(${Math.round(c.placement.building.area_sqm)}㎡)`
                            : " · 배치 불가"}
                        <PlacementSvg placement={c.placement} />
                        {c.placement.setback_binds && (
                          <span style={{ color: "var(--status-warning)" }}>
                            ⚠ 이격이 건폐율보다 배치 제약(실배치 {Math.round(c.placement.buildable_region_sqm)}㎡).{" "}
                          </span>
                        )}
                        <span className="text-[var(--text-hint)]">{c.placement.note}</span>
                        {c.placement.notes?.length > 0 && (
                          <span className="text-[var(--text-hint)]"> {c.placement.notes.join(" · ")}</span>
                        )}
                      </div>
                    )}
                    {/* 도면 세트(분야별 조합) + 커버리지 갭 */}
                    {c.selected && Object.keys(c.selected).length > 0 && (
                      <div className="mt-2 text-[11px] text-[var(--text-secondary)]">
                        도면 세트 {Object.keys(c.selected).length}종
                        {c.disciplines_covered?.length ? ` · 분야: ${c.disciplines_covered.join(", ")}` : ""}
                        {c.missing_disciplines?.length ? (
                          <span style={{ color: "var(--status-warning)" }}>
                            {" "}· 미확보: {c.missing_disciplines.join(", ")}(도면 업로드 시 보강)
                          </span>
                        ) : null}
                      </div>
                    )}
                    {p.verdict.notes?.length > 0 && (
                      <ul className="mt-2 list-inside list-disc text-[11px] text-[var(--text-tertiary)]">
                        {p.verdict.notes.map((n, j) => <li key={j}>{n}</li>)}
                      </ul>
                    )}
                    <EvidencePanel title="설계안 근거" items={toEvidenceItems(p.evidence)} className="mt-2" defaultOpen={false} />
                    {/* 모세혈관 적용 — 연면적이 있어야 하류(공사비·수지)로 전파 가능 */}
                    <div className="mt-3 flex items-center gap-2">
                      <Button
                        variant={appliedIdx === i ? "secondary" : "primary"}
                        onClick={() => handleApply(c, i)}
                        disabled={!c.estimated_gfa_sqm || c.estimated_gfa_sqm <= 0 || appliedIdx === i}
                      >
                        {appliedIdx === i ? "적용됨 ✓" : "이 설계안 적용"}
                      </Button>
                      {appliedIdx === i && (
                        <span className="text-[11px] text-[var(--text-tertiary)]">
                          공사비·수지 등 하류 분석에 연면적·층수·세대수 반영됨
                        </span>
                      )}
                      {/* 자가학습 피드백 — 👍👎(👎는 개선 의견 선택입력)로 성장 루프에 신호 전달 */}
                      <span className="ml-auto inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          aria-label="좋은 설계안"
                          onClick={() => handleFeedback(i, c, "up", p.ledger_hash)}
                          disabled={feedback[i] === "up"}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--surface-soft)] disabled:opacity-50"
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          aria-label="개선 필요"
                          onClick={() => handleFeedback(i, c, "down", p.ledger_hash)}
                          disabled={feedback[i] === "down"}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs hover:bg-[var(--surface-soft)] disabled:opacity-50"
                        >
                          👎
                        </button>
                        {feedback[i] && (
                          <span className="text-[11px] text-[var(--text-tertiary)]">의견 감사합니다</span>
                        )}
                      </span>
                    </div>
                    {/* 3D 매스 프리뷰 — 추천 카드 전용. 치수 데이터 있을 때만 버튼 노출(정직). */}
                    {isRec && (() => {
                      const floors = c.estimated_floors ?? 0;
                      const gfa = c.estimated_gfa_sqm ?? 0;
                      const fpW = c.parking_layout?.footprint_w_m;
                      const fpD = c.parking_layout?.footprint_d_m;
                      const hasFp = typeof fpW === "number" && isFinite(fpW) && fpW > 0
                        && typeof fpD === "number" && isFinite(fpD) && fpD > 0;
                      const canShow3d = floors > 0 && (hasFp || gfa > 0);
                      if (!canShow3d) return null;
                      // 치수 도출: parking_layout footprint 우선, 없으면 gfa/floors 역산.
                      let w: number, d: number;
                      if (hasFp) {
                        w = fpW as number;
                        d = fpD as number;
                      } else {
                        const fp = gfa / floors;
                        const rawD = Math.sqrt(fp / 1.6);
                        d = Math.min(40, Math.max(8, rawD));
                        w = Math.min(120, Math.max(8, fp / d)); // 대형 footprint 시 비현실 폭 방지(개략)
                      }
                      return (
                        <div className="mt-3">
                          <Button
                            variant="secondary"
                            onClick={() => setShow3d((prev) => ({ ...prev, [i]: !prev[i] }))}
                          >
                            🧊 3D 매스 {show3d[i] ? "닫기" : "보기"}
                          </Button>
                          {show3d[i] && (
                            <div className="mt-2">
                              <ProposalMassPreview width={w} depth={d} floors={floors} />
                              <span className="mt-1 block text-[11px] text-[var(--text-hint)]">
                                개략 매스(추정 치수 기준 · 정밀 BIM 아님). 정확한 3D·도면은 &apos;CAD/BIM 스튜디오&apos;에서.
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                );
              })}
            </div>

            {/* 정직 고지 */}
            {result.notes?.length > 0 && (
              <ul className="list-inside list-disc text-[11px] text-[var(--text-tertiary)]">
                {result.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            )}
          </div>
        )}

        {/* 참조 법규 */}
        {lawsErr && <p className="text-xs text-[var(--status-error)]">{lawsErr}</p>}
        {laws && (
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
            <div className="text-xs font-bold text-[var(--text-secondary)]">
              참조 법규 {laws.laws?.length ?? 0}건 ·{" "}
              <span style={{ color: laws.coverage?.ok ? "var(--status-success)" : "var(--status-warning)" }}>
                연결성 {laws.coverage?.resolved ?? 0}/{laws.coverage?.total_keys ?? 0}
                {laws.coverage?.ok ? " 전수 연결" : " 일부 미연결"}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(laws.laws ?? []).map((l) => (
                <LegalRefChip key={l.key} lawName={l.law_name} article={l.article} title={l.title} url={l.url} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
