"use client";

/**
 * BoqAutoWorkspace — 공내역서(BOQ) 자동작성 워크스페이스 (B5).
 *
 * 흐름: ①파라미터(SSOT designData 자동 채움 + 출처배지) → ②공종 탭(마스터 summary)
 *      → ③생성(POST /boq-auto/draft) → 섹션 그룹 테이블(품명|규격|단위|수량|근거)
 *      → ④정직성 배지 상단 고정 → ⑤엑셀 다운로드(blob) → ⑥수지 반영 후보(apply-cost).
 *
 * 원칙:
 *  - 가짜값 금지: SSOT(designData)에 값이 없으면 빈칸 + 수동입력 유도(placeholder 채움 없음).
 *  - 결정론: LLM 0 — 표시·그룹핑·페이지네이션 전부 순수 계산.
 *  - store 직접 쓰기 금지: apply-cost 결과는 "후보" 표기 + 기존 수지(COST) 흐름 안내만.
 *  - 항목 수천 개 대응: 섹션 접기 + 공종당 표시 200행 페이지 제한 + "엑셀로 전체" 안내.
 *  - 디자인 토큰(CSS 변수)만 사용, apiClient v1만 사용(엑셀 blob만 동일 베이스 직접 fetch).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient, apiV1BaseUrl, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { FieldSourceBadge } from "@/components/common/FieldSourceBadge";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import {
  BOQ_AUTO_API,
  BOQ_DISCIPLINES,
  type BoqApplyCostResponse,
  type BoqAutoDraftDisciplineBlock,
  type BoqAutoDraftItem,
  type BoqAutoDraftResponse,
  type BoqDisciplineKey,
  type BoqMasterDisciplineSummary,
  type BoqMasterSummaryResponse,
} from "@/components/cost/boqAutoTypes";

/* ── 표시 상수 ── */

// 공종당 테이블 표시 한도(행) — 초과분은 엑셀 다운로드 안내(렌더 폭주 방지).
const PAGE_SIZE = 200;

function fmt(n: number): string {
  return new Intl.NumberFormat("ko-KR").format(n);
}

/** unknown 값에서 유한 숫자만 추출(아니면 null) — 가짜값 금지. */
function asNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** 수량 표기 — 소수 2자리까지(정수는 그대로), 비수치는 "—"(가짜값 금지). */
function fmtQty(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const rounded = Math.round(n * 100) / 100;
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(rounded);
}

function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiClientError) {
    const payload = e.payload as { detail?: string; message?: string } | null;
    return payload?.detail || payload?.message || `${fallback} (HTTP ${e.status})`;
  }
  return e instanceof Error && e.message ? e.message : fallback;
}

/* ── 마스터 요약 정규화 — record(한글키)·배열 양형 허용 ── */

function normalizeMasterDisciplines(
  res: BoqMasterSummaryResponse | null,
): Map<BoqDisciplineKey, BoqMasterDisciplineSummary> {
  const out = new Map<BoqDisciplineKey, BoqMasterDisciplineSummary>();
  const src = res?.disciplines;
  if (!src) return out;

  const entries: Array<[string, BoqMasterDisciplineSummary]> = Array.isArray(src)
    ? src.map((d) => [String(d.key ?? d.discipline ?? d.file ?? ""), d])
    : Object.entries(src);

  for (const [rawKey, value] of entries) {
    const matched = BOQ_DISCIPLINES.find(
      (d) =>
        rawKey === d.key ||
        rawKey === d.label ||
        value?.key === d.key ||
        value?.discipline === d.label ||
        (typeof value?.file === "string" && value.file === d.file),
    );
    if (matched) out.set(matched.key, value);
  }
  return out;
}

/**
 * 탭 키에 해당하는 공종 항목 추출 — 실제 백엔드는 disciplines 를 record(한글 공종명 키)로
 * 반환한다. record/배열 양형을 방어적으로 정규화한다(가짜 항목 생성 없음).
 */
function getDisciplineItems(
  draft: BoqAutoDraftResponse | null,
  key: BoqDisciplineKey,
): { items: BoqAutoDraftItem[]; total: number; truncated: boolean } {
  const disc = draft?.disciplines;
  const meta = BOQ_DISCIPLINES.find((d) => d.key === key);
  if (!disc || !meta) return { items: [], total: 0, truncated: false };
  if (Array.isArray(disc)) {
    const found = disc.find((d) => d.key === key || d.discipline === meta.label) ?? null;
    const items = found?.items ?? [];
    return { items, total: found?.total_item_count ?? items.length, truncated: !!found?.truncated };
  }
  const rec = disc as Record<string, BoqAutoDraftDisciplineBlock>;
  const block = rec[meta.label] ?? rec[meta.key] ?? null;
  const items = block?.items ?? [];
  return { items, total: block?.item_count ?? items.length, truncated: false };
}

/** 전 공종 항목 평탄화(record/배열 양형) — 신뢰도 집계 등 전역 통계용. */
function allDraftItems(draft: BoqAutoDraftResponse | null): BoqAutoDraftItem[] {
  const disc = draft?.disciplines;
  if (!disc) return [];
  const lists = Array.isArray(disc)
    ? disc.map((d) => d?.items ?? [])
    : Object.values(disc).map((b) => b?.items ?? []);
  return lists.flat().filter(Boolean) as BoqAutoDraftItem[];
}

/* ── 섹션 그룹핑(순서 보존) ── */

interface SectionGroup {
  code: string;
  name: string;
  items: BoqAutoDraftItem[];
}

function groupBySection(items: BoqAutoDraftItem[]): SectionGroup[] {
  const order: string[] = [];
  const map = new Map<string, SectionGroup>();
  for (const it of items) {
    const code = it.section_code || "(섹션 미지정)";
    let g = map.get(code);
    if (!g) {
      g = { code, name: it.section_name || code, items: [] };
      map.set(code, g);
      order.push(code);
    }
    g.items.push(it);
  }
  return order.map((c) => map.get(c)!);
}

/* ═══════════════════════════════════════════════════════════════════ */

export default function BoqAutoWorkspace({ projectId }: { projectId: string }) {
  /* ── SSOT(designData) — 연면적·세대수 자동 채움 원천 ── */
  const designData = useProjectContextStore((s) => s.designData);
  const getFieldProvenance = useProjectContextStore((s) => s.getFieldProvenance);

  /* ── ① 파라미터 상태(문자열 입력 + 출처 추적) ── */
  const [gfaInput, setGfaInput] = useState("");
  const [unitInput, setUnitInput] = useState("");
  // "이 화면에서 사용자가 직접 수정했는가" — true면 SSOT 자동 채움이 덮지 않는다.
  const [gfaEdited, setGfaEdited] = useState(false);
  const [unitEdited, setUnitEdited] = useState(false);

  // SSOT 자동 채움 — designData.totalGfaSqm / unitCount 실존(>0) 시에만(가짜값 금지).
  useEffect(() => {
    if (!gfaEdited && designData?.totalGfaSqm && designData.totalGfaSqm > 0) {
      setGfaInput(String(designData.totalGfaSqm));
    }
  }, [designData?.totalGfaSqm, gfaEdited]);
  useEffect(() => {
    if (!unitEdited && designData?.unitCount && designData.unitCount > 0) {
      setUnitInput(String(designData.unitCount));
    }
  }, [designData?.unitCount, unitEdited]);

  const gfaNum = Number(gfaInput);
  const unitNum = Number(unitInput);
  const gfaValid = Number.isFinite(gfaNum) && gfaNum > 0;
  const unitValid = unitInput.trim() !== "" && Number.isFinite(unitNum) && unitNum > 0;

  // 출처배지: 이 화면 수정 = user, SSOT 채움 = store provenance(설계에서 수동이면 그대로 수동).
  const gfaFromSsot =
    !gfaEdited && !!designData?.totalGfaSqm && designData.totalGfaSqm > 0;
  const unitFromSsot =
    !unitEdited && !!designData?.unitCount && designData.unitCount > 0;
  const gfaProv = gfaFromSsot ? getFieldProvenance("design", "totalGfaSqm") : null;
  const unitProv = unitFromSsot ? getFieldProvenance("design", "unitCount") : null;

  /* ── ② 마스터 요약 ── */
  const [master, setMaster] = useState<BoqMasterSummaryResponse | null>(null);
  const [masterError, setMasterError] = useState("");
  const [masterLoading, setMasterLoading] = useState(false);

  const fetchMaster = useCallback(async () => {
    setMasterLoading(true);
    setMasterError("");
    try {
      const res = await apiClient.get<BoqMasterSummaryResponse>(
        BOQ_AUTO_API.masterSummary,
      );
      setMaster(res);
    } catch (e) {
      setMaster(null);
      setMasterError(errorMessage(e, "마스터 요약을 불러오지 못했습니다."));
    } finally {
      setMasterLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMaster();
  }, [fetchMaster]);

  const masterByKey = useMemo(() => normalizeMasterDisciplines(master), [master]);

  /* ── 탭 ── */
  const [activeKey, setActiveKey] = useState<BoqDisciplineKey>("architecture");

  /* ── ⑥ 수지 반영 후보 상태 — 생성 핸들러가 초기화하므로 먼저 선언 ── */
  const [applyResult, setApplyResult] = useState<BoqApplyCostResponse | null>(null);
  // apply-cost 호출 당시의 GFA 스냅샷 — ㎡당 후보를 산정한 분모와 일치시킨다(입력 변경 후 불일치 방지).
  const [appliedGfa, setAppliedGfa] = useState<number | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState("");

  /* ── ③ 드래프트 생성 ── */
  const [draft, setDraft] = useState<BoqAutoDraftResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [draftError, setDraftError] = useState("");
  // 생성 모드: plain(수량만) · priced(N3 단가/금액) · bim(N2 프로젝트 BIM 병합).
  const [mode, setMode] = useState<"plain" | "priced" | "bim">("plain");
  // 공종별 페이지(1-base) — 탭 전환에도 유지.
  const [pageByKey, setPageByKey] = useState<Partial<Record<BoqDisciplineKey, number>>>({});
  // 섹션 접기 상태 — key: `${disciplineKey}:${sectionCode}` (true = 접힘).
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // 백엔드 계약: { params: { gfa_sqm, households? }, disciplines? } (+ project_id는 BIM/적용용).
  const buildParams = useCallback(
    () => ({ gfa_sqm: gfaNum, ...(unitValid ? { households: unitNum } : {}) }),
    [gfaNum, unitValid, unitNum],
  );
  const buildDraftBody = useCallback(
    (): Record<string, unknown> => ({ params: buildParams() }),
    [buildParams],
  );
  const buildProjectBody = useCallback(
    (): Record<string, unknown> => ({ params: buildParams(), project_id: projectId }),
    [buildParams, projectId],
  );

  const handleGenerate = useCallback(async () => {
    if (!gfaValid || generating) return;
    setGenerating(true);
    setDraftError("");
    setApplyResult(null);
    setAppliedGfa(null);
    setApplyError("");
    try {
      // 모드별 엔드포인트 — priced(단가/금액), bim(프로젝트 실측 병합), plain(수량만).
      const endpoint =
        mode === "priced" ? BOQ_AUTO_API.pricedDraft
          : mode === "bim" ? BOQ_AUTO_API.fromProject
          : BOQ_AUTO_API.draft;
      const body = mode === "bim" ? buildProjectBody() : buildDraftBody();
      const res = await apiClient.post<BoqAutoDraftResponse>(endpoint, { body });
      setDraft(res);
      setPageByKey({});
      setCollapsed({});
    } catch (e) {
      setDraftError(errorMessage(e, "공내역 드래프트 생성에 실패했습니다."));
    } finally {
      setGenerating(false);
    }
  }, [gfaValid, generating, mode, buildDraftBody, buildProjectBody]);

  /* ── ⑤ 엑셀 내보내기(blob — apiV1BaseUrl 직접 fetch, 기존 PDF 다운로드 패턴) ── */
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  const handleExport = useCallback(async () => {
    if (!gfaValid || exporting) return;
    setExporting(true);
    setExportError("");
    try {
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem("propai_access_token") ?? ""
          : "";
      // priced 모드는 금액 엑셀(/draft/priced/export), 그 외는 단가 빈칸 엑셀(/draft/export).
      const path = mode === "priced" ? BOQ_AUTO_API.pricedExport : BOQ_AUTO_API.export;
      const res = await fetch(`${apiV1BaseUrl()}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(buildDraftBody()),
      });
      if (!res.ok) throw new Error(`엑셀 내보내기에 실패했습니다 (HTTP ${res.status}).`);
      const contentType = res.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        // 파일 대신 JSON이 오면 빈 파일 다운로드 방지 — 서버 메시지 정직 표기.
        const payload = (await res.json()) as { detail?: string; message?: string };
        throw new Error(payload?.detail || payload?.message || "엑셀이 아직 준비되지 않았습니다.");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const tag = mode === "priced" ? "priced_" : mode === "bim" ? "parametric_" : "";
      anchor.download = `boq_${tag}${projectId}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "엑셀 내보내기에 실패했습니다.");
    } finally {
      setExporting(false);
    }
  }, [gfaValid, exporting, mode, buildDraftBody, projectId]);

  /* ── ⑥ 수지 반영 후보(apply-cost) — store 직접 쓰기 금지, 후보 표기만 ── */
  const handleApplyCost = useCallback(async () => {
    if (!gfaValid || applying) return;
    setApplying(true);
    setApplyError("");
    try {
      const res = await apiClient.post<BoqApplyCostResponse>(BOQ_AUTO_API.applyCost, {
        body: buildProjectBody(),
      });
      setApplyResult(res);
      setAppliedGfa(gfaNum);  // 이 총액을 만든 GFA 스냅샷(㎡당 분모 정합)
    } catch (e) {
      setApplyResult(null);
      setAppliedGfa(null);
      setApplyError(errorMessage(e, "수지 반영 후보 산출에 실패했습니다."));
    } finally {
      setApplying(false);
    }
  }, [gfaValid, applying, buildProjectBody, gfaNum]);

  /* ── 활성 탭 파생 데이터(순수 계산 — 결정론) ── */
  const activeView = useMemo(
    () => getDisciplineItems(draft, activeKey),
    [draft, activeKey],
  );
  const activeItems = activeView.items;
  const totalRows = activeView.total;
  const pageCount = Math.max(1, Math.ceil(activeItems.length / PAGE_SIZE));
  const page = Math.min(pageByKey[activeKey] ?? 1, pageCount);
  const pageItems = useMemo(
    () => activeItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [activeItems, page],
  );
  const pageSections = useMemo(() => groupBySection(pageItems), [pageItems]);

  // N1 표본 분포: 실적 누적(n>=3, "실적 N건 …") vs 단일표본(n=1). 일부 일반화 시 안내.
  const generalizedCount = useMemo(
    () => allDraftItems(draft).filter((it) => (it.confidence ?? "").includes("실적")).length,
    [draft],
  );
  // N3 단가결합 통계 + N2 BIM 병합 통계(있을 때만 배지 노출).
  const pricing = draft?.summary?.pricing ?? null;
  const bimMerge = draft?.summary?.bim_merge ?? null;
  // 활성 공종에 금액(amount)이 하나라도 있으면 금액 열을 표시.
  const hasAmounts = useMemo(
    () => activeItems.some((it) => typeof it.amount === "number" && Number.isFinite(it.amount)),
    [activeItems],
  );

  // apply-cost 결과(실제 백엔드 형태) 파생값 — boq_builder 개산 + N3 단가결합 정밀경로.
  const builderEstimate = applyResult?.cost_estimate ?? null;
  const builderSummary = (builderEstimate?.summary ?? {}) as Record<string, unknown>;
  const builderTotal = asNum(builderEstimate?.total_construction_cost_won);
  const builderDirect = asNum(builderSummary.direct);
  const builderIndirect = asNum(builderSummary.indirect);
  // ㎡당은 백엔드 미반환 → 총액을 만든 GFA 스냅샷(appliedGfa)으로 나눈다(라이브 입력 변경 무관·정합).
  const builderPerSqm =
    builderTotal != null && appliedGfa != null && appliedGfa > 0
      ? Math.round(builderTotal / appliedGfa)
      : null;
  const pricedEst = applyResult?.priced_cost_estimate ?? null;

  const provenanceText =
    master?.project?.provenance ??
    draft?.badges?.provenance ??
    "실적 공내역서 1건(n=1) 기반 표준항목 — 참고치";

  /* ═══ 렌더 ═══ */

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* ── ① 파라미터 패널 ── */}
      <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] bg-[var(--surface-soft)] px-6 py-4">
          <h2 className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">
            공내역서(BOQ) 자동작성 — 파라메트릭 표준항목
          </h2>
          <span className="rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
            단가 빈칸 · 수량 채움(실무 공내역 표준)
          </span>
        </div>

        <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
          {/* 연면적 */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">
                연면적 GFA (㎡) <span className="text-[var(--status-error)]">*</span>
              </span>
              {gfaInput.trim() !== "" && (
                <FieldSourceBadge
                  source={gfaEdited ? "user" : gfaProv?.source ?? "auto"}
                  updatedAt={!gfaEdited ? gfaProv?.updatedAt : undefined}
                />
              )}
            </div>
            <input
              type="number"
              inputMode="decimal"
              min={0}
              value={gfaInput}
              onChange={(e) => {
                setGfaEdited(true);
                setGfaInput(e.target.value);
              }}
              placeholder="예: 50000"
              className="mt-1.5 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-sm font-bold text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            {gfaFromSsot ? (
              <p className="mt-1 text-[10px] text-[var(--text-hint)]">
                설계(SSOT)에서 자동 채움 — 수정하면 이 화면에서만 적용됩니다.
              </p>
            ) : (
              !gfaValid && (
                <p className="mt-1 text-[10px] text-[var(--text-hint)]">
                  설계 SSOT에 연면적이 없습니다 — 직접 입력하세요(필수).
                </p>
              )
            )}
          </div>

          {/* 세대수 */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">
                세대수 (선택)
              </span>
              {unitInput.trim() !== "" && (
                <FieldSourceBadge
                  source={unitEdited ? "user" : unitProv?.source ?? "auto"}
                  updatedAt={!unitEdited ? unitProv?.updatedAt : undefined}
                />
              )}
            </div>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              value={unitInput}
              onChange={(e) => {
                setUnitEdited(true);
                setUnitInput(e.target.value);
              }}
              placeholder="예: 480"
              className="mt-1.5 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-sm font-bold text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            <p className="mt-1 text-[10px] text-[var(--text-hint)]">
              {unitFromSsot
                ? "설계(SSOT)에서 자동 채움 — 세대 드라이버 항목에 사용됩니다."
                : "설계 SSOT에 세대수가 없으면 비워둘 수 있습니다(GFA 드라이버만 적용)."}
            </p>
          </div>

          {/* 표본 출처(마스터) */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">
              표준항목 마스터 출처
            </span>
            {master?.project ? (
              <p className="mt-1.5 text-[11px] leading-5 text-[var(--text-secondary)]">
                <span className="font-bold text-[var(--text-primary)]">
                  {master.project.name ?? "표본 프로젝트"}
                </span>
                {master.project.gfa_sqm ? (
                  <> · GFA {fmt(master.project.gfa_sqm)}㎡</>
                ) : null}
                {master.project.sample_count != null ? (
                  <> · 표본 n={master.project.sample_count}</>
                ) : null}
              </p>
            ) : (
              <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">
                {masterLoading
                  ? "마스터 요약 불러오는 중…"
                  : masterError || "마스터 요약 미수신"}
              </p>
            )}
            <p className="mt-1 text-[10px] text-[var(--text-hint)]">{provenanceText}</p>
          </div>
        </div>

        {/* 생성 모드 토글 — plain(수량만) · priced(단가/금액) · bim(프로젝트 BIM 병합) */}
        <div className="flex flex-wrap items-center gap-2 border-t border-[var(--line)] px-6 pt-4">
          <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
            생성 모드
          </span>
          {([
            { k: "plain", label: "수량만(공내역 표준)", hint: "단가 빈칸 · 물량만 채움" },
            { k: "priced", label: "단가·금액 결합(N3)", hint: "단가DB/도면참고단가 결합 — 부분 커버리지·정직표기" },
            { k: "bim", label: "BIM 실측 병합(N2)", hint: "프로젝트 BIM 물량 1:1 우선 — 없으면 추정 유지" },
          ] as const).map((m) => (
            <button
              key={m.k}
              type="button"
              onClick={() => setMode(m.k)}
              aria-pressed={mode === m.k}
              title={m.hint}
              className={`rounded-lg border px-3 py-1.5 text-[10px] font-black transition-colors ${
                mode === m.k
                  ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]/20 text-[var(--accent-strong)]"
                  : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]/50"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* 액션 줄 */}
        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line)] px-6 py-4">
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={!gfaValid || generating}
            className="rounded-xl bg-[var(--accent)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-white shadow-[var(--shadow-glow)] hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            {generating
              ? "생성 중…"
              : mode === "priced"
                ? "단가·금액 결합 생성"
                : mode === "bim"
                  ? "BIM 병합 드래프트 생성"
                  : "공내역 드래프트 생성"}
          </button>
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={!gfaValid || exporting}
            title={
              mode === "bim"
                ? "BIM 병합 전용 엑셀 경로는 아직 없습니다 — 내려받는 파일은 추정(parametric) 물량 기준입니다(화면의 BIM 실측치는 미반영)."
                : undefined
            }
            className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
          >
            {exporting
              ? "엑셀 준비 중…"
              : mode === "priced"
                ? "금액 엑셀 다운로드"
                : mode === "bim"
                  ? "엑셀 (추정 물량)"
                  : "엑셀 다운로드 (전체 항목)"}
          </button>
          <button
            type="button"
            onClick={() => void handleApplyCost()}
            disabled={!gfaValid || applying || !draft}
            title={!draft ? "먼저 드래프트를 생성하세요." : undefined}
            className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
          >
            {applying ? "산출 중…" : "수지 반영 후보 보기"}
          </button>
          {draftError && (
            <span className="text-[11px] font-semibold text-[var(--status-error)]">{draftError}</span>
          )}
          {exportError && (
            <span className="text-[11px] font-semibold text-[var(--status-error)]">{exportError}</span>
          )}
          {applyError && (
            <span className="text-[11px] font-semibold text-[var(--status-error)]">{applyError}</span>
          )}
        </div>
      </section>

      {/* ── ④ 정직성 경고·배지 — 드래프트 생성 후 상단 고정 ── */}
      {draft && (
        <div className="sticky top-0 z-20 rounded-xl border border-[var(--status-warning)]/40 bg-[var(--surface-strong)] px-4 py-3 shadow-[var(--shadow-md)]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 px-2.5 py-1 text-[10px] font-black text-[var(--status-warning)]">
              전문 적산(QS) 검토 필수
            </span>
            <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[10px] font-bold text-[var(--text-tertiary)]">
              {provenanceText}
            </span>
            {/* N3 단가결합 커버리지 — 부분 단가·정직 표기. */}
            {pricing && (pricing.priced_count ?? 0) > 0 && (
              <span
                title={`단가 결합 ${fmt(pricing.priced_count ?? 0)}/${fmt(pricing.total_items ?? 0)}건. 미매칭은 단가 빈칸(가짜 단가 금지). 출처: ${pricing.by_source ? Object.entries(pricing.by_source).map(([k, v]) => `${k} ${v}`).join(" · ") : "-"}`}
                className="rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)]/20 px-2.5 py-1 text-[10px] font-black text-[var(--accent-strong)]"
              >
                단가 결합 {pricing.coverage_pct ?? 0}% ({fmt(pricing.priced_count ?? 0)}/{fmt(pricing.total_items ?? 0)})
              </span>
            )}
            {/* N2 BIM 실측 병합 커버리지(0건이면 안내). */}
            {bimMerge && (
              <span
                title="BIM 실측 물량이 work_code 기준 1:1 매칭된 항목 수 — 나머지는 파라메트릭(추정). 단위불일치·모호매칭은 미적용(허위분배 금지)."
                className="rounded-full border border-[var(--status-info)]/40 bg-[var(--status-info)]/10 px-2.5 py-1 text-[10px] font-black text-[var(--status-info)]"
              >
                {(bimMerge.bim_matched_count ?? 0) > 0
                  ? `BIM 실측 병합 ${fmt(bimMerge.bim_matched_count ?? 0)}/${fmt(bimMerge.bim_rows_count ?? 0)}건`
                  : (() => {
                      // by_source 기반 — 사용자 입력(user) 항목을 추정으로 오기재하지 않는다(정직).
                      const by = bimMerge.by_source ?? {};
                      const parts = [
                        (by.parametric ?? 0) > 0 ? `추정 ${fmt(by.parametric ?? 0)}건` : null,
                        (by.user ?? 0) > 0 ? `입력 ${fmt(by.user ?? 0)}건` : null,
                      ].filter(Boolean);
                      return `BIM 실측 0건${parts.length ? ` — ${parts.join(" · ")}` : " — 추정 유지"}`;
                    })()}
              </span>
            )}
            {/* N1 실적 누적: 일부 항목이 n>=3로 일반화되면 표기. */}
            {generalizedCount > 0 && (
              <span
                title="실적 N건(n≥3) 누적으로 표본평균·CV 기반으로 전환된 항목 수. 나머지는 단일표본(n=1) 참고치."
                className="rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 px-2.5 py-1 text-[10px] font-black text-[var(--status-warning)]"
              >
                실적 누적 반영 {fmt(generalizedCount)}건
              </span>
            )}
            {draft.badges?.note && (
              <span className="text-[10px] font-semibold text-[var(--text-hint)]">
                {String(draft.badges.note)}
              </span>
            )}
          </div>
          {(draft.warnings?.length ?? 0) > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[10px] font-semibold text-[var(--status-warning)]">
              {draft.warnings!.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── ② 공종 탭 ── */}
      <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
          {BOQ_DISCIPLINES.map((d) => {
            const sum = masterByKey.get(d.key);
            const active = d.key === activeKey;
            return (
              <button
                key={d.key}
                type="button"
                onClick={() => setActiveKey(d.key)}
                aria-pressed={active}
                className={`rounded-xl border px-4 py-2 text-[11px] font-black transition-colors ${
                  active
                    ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]/20 text-[var(--accent-strong)]"
                    : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]/50"
                }`}
              >
                {d.label}
                {sum?.unique_items != null && (
                  <span className="ml-1.5 text-[9px] font-bold text-[var(--text-hint)]">
                    {fmt(sum.unique_items)}항목
                    {sum.sections != null ? ` · ${fmt(sum.sections)}섹션` : ""}
                  </span>
                )}
              </button>
            );
          })}
          {masterError && !masterLoading && (
            <button
              type="button"
              onClick={() => void fetchMaster()}
              className="ml-auto text-[10px] font-bold text-[var(--status-error)] underline-offset-2 hover:underline"
              title={masterError}
            >
              마스터 요약 실패 — 다시 시도
            </button>
          )}
        </div>

        {/* ── ③ 섹션 그룹 테이블 ── */}
        <div className="p-4">
          {!draft ? (
            <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-xs text-[var(--text-hint)]">
              연면적(필수)·세대수(선택)를 확인한 뒤 “공내역 드래프트 생성”을 누르면
              5공종 표준항목에 파라메트릭 수량이 채워진 공내역 드래프트가 표시됩니다.
              <br />
              단가·금액은 채우지 않습니다(공내역 표준) — 금액 후보는 “수지 반영 후보 보기”로 확인하세요.
            </div>
          ) : activeItems.length === 0 ? (
            <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-xs text-[var(--text-hint)]">
              이 공종의 드래프트 항목이 없습니다(서버 응답 기준 — 가짜 항목을 만들지 않습니다).
            </div>
          ) : (
            <>
              {/* 표시 한도 안내 + 페이지 */}
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-semibold text-[var(--text-tertiary)]">
                  총 {fmt(totalRows)}행 중{" "}
                  <span className="font-black text-[var(--text-primary)]">
                    {fmt((page - 1) * PAGE_SIZE + 1)}–{fmt((page - 1) * PAGE_SIZE + pageItems.length)}
                  </span>
                  행 표시 (공종당 {fmt(PAGE_SIZE)}행 제한 — 전체는 “엑셀 다운로드”로 확인)
                  {activeView.truncated ? (
                    <span className="ml-1 text-[var(--status-warning)]">
                      · 서버 응답도 일부 생략됨
                    </span>
                  ) : null}
                </p>
                {pageCount > 1 && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        setPageByKey((p) => ({ ...p, [activeKey]: Math.max(1, page - 1) }))
                      }
                      disabled={page <= 1}
                      className="rounded-lg border border-[var(--line)] px-2.5 py-1 text-[10px] font-bold text-[var(--text-secondary)] disabled:opacity-40"
                    >
                      ← 이전
                    </button>
                    <span className="text-[10px] font-black text-[var(--text-tertiary)]">
                      {page} / {pageCount}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setPageByKey((p) => ({
                          ...p,
                          [activeKey]: Math.min(pageCount, page + 1),
                        }))
                      }
                      disabled={page >= pageCount}
                      className="rounded-lg border border-[var(--line)] px-2.5 py-1 text-[10px] font-bold text-[var(--text-secondary)] disabled:opacity-40"
                    >
                      다음 →
                    </button>
                  </div>
                )}
              </div>

              {/* 섹션 아코디언 */}
              <div className="space-y-2">
                {pageSections.map((sec) => {
                  const cKey = `${activeKey}:${sec.code}`;
                  const isCollapsed = collapsed[cKey] === true;
                  return (
                    <div
                      key={cKey}
                      className="overflow-hidden rounded-xl border border-[var(--line)]"
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setCollapsed((c) => ({ ...c, [cKey]: !isCollapsed }))
                        }
                        aria-expanded={!isCollapsed}
                        className="flex w-full items-center justify-between gap-2 bg-[var(--surface-soft)] px-4 py-2.5 text-left"
                      >
                        <span className="text-[11px] font-black text-[var(--text-primary)]">
                          <span className="mr-2 text-[var(--accent-strong)]">{sec.code}</span>
                          {sec.name}
                          <span className="ml-2 text-[10px] font-bold text-[var(--text-hint)]">
                            {fmt(sec.items.length)}항목(이 페이지)
                          </span>
                        </span>
                        <span className="text-[10px] font-bold text-[var(--accent-strong)]">
                          {isCollapsed ? "펼치기" : "접기"}
                        </span>
                      </button>

                      {!isCollapsed && (
                        <div className="overflow-x-auto">
                          <table className="w-full border-collapse text-left">
                            <thead>
                              <tr className="border-t border-[var(--line)] bg-[var(--surface-strong)]">
                                <th className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">품명</th>
                                <th className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">규격</th>
                                <th className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">단위</th>
                                <th className="px-4 py-2 text-right text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">수량</th>
                                {hasAmounts && (
                                  <th className="px-4 py-2 text-right text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">금액(원)</th>
                                )}
                                <th className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">근거</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sec.items.map((it) => {
                                // N1: 일반화(n>=3) 항목은 "실적 N건…", 그 외 단일표본(n=1).
                                const generalized = (it.confidence ?? "").includes("실적");
                                const basisTitle = [
                                  it.basis?.trim()
                                    ? `근거: ${it.basis.trim()}`
                                    : "근거 산식 미제공(서버 응답 기준)",
                                  it.qty_sample != null
                                    ? `표본 수량: ${fmtQty(it.qty_sample)} (GFA 238,504㎡ 실적 기준)`
                                    : null,
                                  it.driver ? `드라이버: ${it.driver}` : null,
                                ]
                                  .filter(Boolean)
                                  .join("\n");
                                return (
                                  <tr
                                    key={it.id}
                                    className="border-t border-[var(--line)] hover:bg-[var(--surface-soft)]/60"
                                  >
                                    <td className="px-4 py-2 text-[12px] font-bold text-[var(--text-primary)]">
                                      {it.name}
                                    </td>
                                    <td className="px-4 py-2 text-[11px] text-[var(--text-secondary)]">
                                      {it.spec?.trim() || "—"}
                                    </td>
                                    <td className="px-4 py-2 text-[11px] text-[var(--text-secondary)]">
                                      {it.unit?.trim() || "—"}
                                    </td>
                                    <td className="px-4 py-2 text-right text-[12px] font-black tabular-nums text-[var(--text-primary)]">
                                      <span className="inline-flex items-center justify-end gap-1">
                                        {fmtQty(it.qty)}
                                        <QtySourceChip item={it} />
                                      </span>
                                    </td>
                                    {hasAmounts && (
                                      <td className="px-4 py-2 text-right text-[12px] font-black tabular-nums text-[var(--text-primary)]">
                                        {typeof it.amount === "number" && Number.isFinite(it.amount) ? (
                                          <span className="inline-flex items-center justify-end gap-1">
                                            {fmt(it.amount)}
                                            <PriceSourceChip item={it} />
                                          </span>
                                        ) : (
                                          <span
                                            title="단가 미결합 — 가짜 단가를 만들지 않습니다(공종키·단위 미매칭)."
                                            className="text-[var(--text-hint)]"
                                          >
                                            —
                                          </span>
                                        )}
                                      </td>
                                    )}
                                    <td className="px-4 py-2">
                                      <span
                                        title={basisTitle}
                                        className="inline-flex cursor-help items-center gap-1 rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]"
                                      >
                                        {it.driver?.trim() || "근거 보기"}
                                      </span>
                                      {generalized && (
                                        <span
                                          title={`실적 N건(n≥3) 누적 표본평균·CV 기반으로 전환됨 — ${it.confidence ?? ""}`}
                                          className="ml-1 inline-flex cursor-help items-center rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 px-2 py-0.5 text-[9px] font-black text-[var(--status-warning)]"
                                        >
                                          {it.confidence}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </section>

      {/* ── ⑥ 수지 반영 후보 결과 — 후보 표기 + 기존 수지 흐름 안내(직접 반영 없음) ── */}
      {applyResult && (
        <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] bg-[var(--surface-soft)] px-6 py-4">
            <h3 className="text-[11px] font-black uppercase tracking-[0.25em] text-[var(--text-primary)]">
              수지 반영 후보 (단가 결합 시산)
            </h3>
            <span className="rounded-full border border-[var(--status-info)]/40 bg-[var(--status-info)]/10 px-2.5 py-1 text-[9px] font-black text-[var(--status-info)]">
              후보치 — 자동 반영 안 함
            </span>
          </div>
          <div className="grid gap-4 p-6">
            {/* boq_builder 개산 경로(기본) */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <CandidateKpi
                label="개산 총액 후보"
                value={builderTotal != null ? `${fmt(builderTotal)} 원` : "산출 불가"}
                highlight
              />
              <CandidateKpi
                label="직접비"
                value={builderDirect != null ? `${fmt(builderDirect)} 원` : "—"}
              />
              <CandidateKpi
                label="간접비"
                value={builderIndirect != null ? `${fmt(builderIndirect)} 원` : "—"}
              />
              <CandidateKpi
                label="㎡당 후보"
                value={builderPerSqm != null ? `${fmt(builderPerSqm)} 원/㎡` : "—"}
              />
            </div>

            {/* N3 단가결합 직접비 → 12단계 법정요율(결합 0건이면 비표시 — 정직) */}
            {pricedEst && (
              <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]/10 p-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)]">
                    단가결합 정밀경로 (boq_priced — 12단계 법정요율)
                  </span>
                  <span className="text-[10px] font-bold text-[var(--text-hint)]">
                    커버리지 {pricedEst.coverage_pct ?? 0}% ({fmt(pricedEst.priced_count ?? 0)}/{fmt(pricedEst.total_items ?? 0)}건) · 부분합
                  </span>
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <CandidateKpi
                    label="결합 직접비"
                    value={pricedEst.direct_cost_won != null ? `${fmt(pricedEst.direct_cost_won)} 원` : "—"}
                  />
                  <CandidateKpi
                    label="법정요율 총액"
                    value={pricedEst.total_construction_cost_won != null ? `${fmt(pricedEst.total_construction_cost_won)} 원` : "—"}
                    highlight
                  />
                  <CandidateKpi
                    label="단가 결합 금액합"
                    value={pricedEst.priced_amount_won != null ? `${fmt(pricedEst.priced_amount_won)} 원` : "—"}
                  />
                </div>
              </div>
            )}

            <EvidencePanel
              title="후보 산출 근거"
              items={
                [
                  applyResult.cost_estimate?.source
                    ? { label: "개산 경로", value: String(applyResult.cost_estimate.source) }
                    : null,
                  pricedEst
                    ? {
                        label: "단가 결합",
                        value: `${fmt(pricedEst.priced_count ?? 0)}/${fmt(pricedEst.total_items ?? 0)}건 (커버리지 ${pricedEst.coverage_pct ?? 0}%)`,
                        basis: "미매칭 항목은 직접비에서 제외(가짜 단가 금지) — 부분 커버리지·전문 적산 검토 필수",
                      }
                    : { label: "단가 결합", value: "결합 0건", basis: "공종키·단위 매칭 단가 없음 — 개산(boq_builder) 경로만 표기(정직)" },
                  gfaValid
                    ? {
                        label: "스케일 기준",
                        value: `GFA ${fmt(gfaNum)}㎡`,
                        basis: `표본 GFA ${master?.project?.gfa_sqm ? fmt(master.project.gfa_sqm) : "238,504"}㎡ 대비 파라메트릭`,
                      }
                    : null,
                ].filter(Boolean) as EvidenceItem[]
              }
            />

            <div className="rounded-xl border border-[var(--status-info)]/30 bg-[var(--status-info)]/5 px-4 py-3 text-[11px] leading-5 text-[var(--text-secondary)]">
              이 금액은 <b>후보치</b>이며 수지(costData)에 자동 반영되지 않습니다(persisted=false). 반영하려면{" "}
              <b>공사비(COST) 모듈</b>의 기존 “공사비 정밀 분석 → 수지 반영” 흐름에서
              검토 후 적용하세요(이 화면은 출처·근거 확인용입니다).
              {(applyResult.badges?.length ?? 0) > 0 ? (
                <span className="mt-1 block text-[10px] text-[var(--text-hint)]">
                  {applyResult.badges!.join(" · ")}
                </span>
              ) : null}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── 단가 출처 칩(N3 단가결합) — DB/도면참고 정직 표기 ── */
function PriceSourceChip({ item }: { item: BoqAutoDraftItem }) {
  const src = item.price_source ?? "";
  if (!src) return null;
  const isRef = src === "도면참고단가";
  const isFallback = src === "fallback";
  const label = isRef ? "도면참고" : isFallback ? "기준단가" : "단가DB";
  const title = isRef
    ? "전기 도면 참고 재료단가(재료비만 — 노무·경비 별도). 출처 정직 표기."
    : isFallback
      ? "단가 SSOT fallback(표준품셈 기준값) — DB 미보유 키."
      : `단가 SSOT(${src})${item.price_key ? ` · 키: ${item.price_key}` : ""}`;
  return (
    <span
      title={title}
      className={`inline-flex cursor-help items-center rounded-full border px-1.5 py-0.5 text-[8px] font-black ${
        isRef
          ? "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 text-[var(--status-warning)]"
          : "border-[var(--accent-strong)]/40 bg-[var(--accent-soft)]/20 text-[var(--accent-strong)]"
      }`}
    >
      {label}
    </span>
  );
}

/* ── 수량 출처 칩(N2 BIM 병합) — BIM실측/입력/추정 정직 표기 ── */
function QtySourceChip({ item }: { item: BoqAutoDraftItem }) {
  const src = (item.qty_source ?? "").toLowerCase();
  if (src === "bim") {
    const orig = item.qty_parametric;
    const title =
      `BIM 실측 물량으로 교체됨${orig != null ? ` (추정 ${fmtQty(orig)} → 실측)` : ""}` +
      (item.bim_work_code ? ` · ${item.bim_work_code}` : "");
    return (
      <span
        title={title}
        className="inline-flex cursor-help items-center rounded-full border border-[var(--status-info)]/40 bg-[var(--status-info)]/10 px-1.5 py-0.5 text-[8px] font-black text-[var(--status-info)]"
      >
        BIM실측
      </span>
    );
  }
  if (src === "user") {
    return (
      <span
        title="사용자가 입력한 수량 — BIM·파라메트릭이 덮지 않습니다(우선순위 최상)."
        className="inline-flex cursor-help items-center rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)]/20 px-1.5 py-0.5 text-[8px] font-black text-[var(--accent-strong)]"
      >
        입력
      </span>
    );
  }
  return (
    <span
      title="파라메트릭(실적 원단위 비례) 추정 수량 — BIM 실측 미보유."
      className="inline-flex cursor-help items-center rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-1.5 py-0.5 text-[8px] font-bold text-[var(--text-hint)]"
    >
      추정
    </span>
  );
}

/* ── 후보 KPI 카드(로컬 부품) ── */
function CandidateKpi({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 ${
        highlight
          ? "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]/20"
          : "border-[var(--line)] bg-[var(--surface-soft)]"
      }`}
    >
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
        {label}
      </p>
      <p
        className={`mt-2 text-lg font-[1000] tracking-tight ${
          highlight ? "text-[var(--accent)]" : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
