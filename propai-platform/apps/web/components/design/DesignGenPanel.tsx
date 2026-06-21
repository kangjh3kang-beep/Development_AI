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

import { useState } from "react";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { NumberInput } from "@/components/common/NumberInput";

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
  warnings: string[];
  spec: Record<string, unknown>;
};

type Candidate = {
  primary_drawing_type: string;
  scale_factor: number | null;
  estimated_gfa_sqm: number | null;
  estimated_floors: number | null;
  estimated_units: number | null;
  estimated_parking: number | null;
  parking_required: number | null;
  parking_area_sqm: number | null;
  parking_basement_floors: number | null;
  parking_feasible: boolean | null;
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

type Proposal = { candidate: Candidate; verdict: Verdict; evidence: Evidence[] };

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

  // 업로드(ingest)
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [ingest, setIngest] = useState<IngestResult | null>(null);
  const [ingestErr, setIngestErr] = useState<string | null>(null);

  // 생성(generate)
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [genErr, setGenErr] = useState<string | null>(null);

  // 법규(laws)
  const [laws, setLaws] = useState<LawsResult | null>(null);
  const [lawsLoading, setLawsLoading] = useState(false);
  const [lawsErr, setLawsErr] = useState<string | null>(null);

  // 유사 도면 검색(search)
  const [searchType, setSearchType] = useState<string>("");
  const [searchKeywords, setSearchKeywords] = useState<string>("");
  const [searchRes, setSearchRes] = useState<SearchResult | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  // 추천안 적용(모세혈관 SSOT 반영) — 적용된 설계안 인덱스.
  const [appliedIdx, setAppliedIdx] = useState<number | null>(null);

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
    } catch (e) {
      setIngestErr(errMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleGenerate() {
    setLoading(true);
    setGenErr(null);
    setResult(null);
    setAppliedIdx(null);
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
        </div>
        {genErr && <p className="text-xs text-[var(--status-error)]">{genErr}</p>}

        {/* 도면 업로드(ingest) */}
        <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="text-xs font-semibold text-[var(--text-secondary)]">
            📐 설계파일 업로드 <span className="font-normal text-[var(--text-tertiary)]">xlsx · dxf · ifc · pdf · png · jpg · webp (최대 25MB)</span>
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
              <span className="font-bold text-[var(--text-primary)]">{ingest.drawing_type}</span> · {ingest.source_format} ·{" "}
              {ingest.indexed ? (
                <span style={{ color: "var(--status-success)" }}>색인 완료</span>
              ) : (
                <span style={{ color: "var(--status-warning)" }}>미색인({ingest.index_skip_reason || "사유 미상"})</span>
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
              {DRAWING_TYPE_OPTIONS.map((t) => (
                <option key={t || "all"} value={t}>
                  {t ? DRAWING_TYPE_LABEL[t] : "전체 유형"}
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
                          {m.drawing_type ? DRAWING_TYPE_LABEL[m.drawing_type] ?? m.drawing_type : "미상"}
                          {m.title ? ` · ${m.title}` : ""}
                        </span>
                        <span className="text-[var(--text-tertiary)]">유사 {(m.score * 100).toFixed(0)}</span>
                      </div>
                      <div className="mt-0.5 text-[var(--text-secondary)]">
                        {m.total_area_sqm != null ? `${m.total_area_sqm.toLocaleString()}㎡` : "면적 미상"}
                        {m.source_format ? ` · ${m.source_format}` : ""}
                      </div>
                      {m.summary && <div className="mt-1 line-clamp-2 text-[var(--text-tertiary)]">{m.summary}</div>}
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
                    </div>
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
