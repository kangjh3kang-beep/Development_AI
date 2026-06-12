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
  type BoqAutoDraftDiscipline,
  type BoqAutoDraftItem,
  type BoqAutoDraftRequest,
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

/** 드래프트 응답에서 탭 키에 해당하는 공종 블록 찾기(key→한글명 순 매칭). */
function findDraftDiscipline(
  draft: BoqAutoDraftResponse | null,
  key: BoqDisciplineKey,
): BoqAutoDraftDiscipline | null {
  if (!draft?.disciplines) return null;
  const meta = BOQ_DISCIPLINES.find((d) => d.key === key);
  return (
    draft.disciplines.find(
      (d) => d.key === key || (meta && d.discipline === meta.label),
    ) ?? null
  );
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
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState("");

  /* ── ③ 드래프트 생성 ── */
  const [draft, setDraft] = useState<BoqAutoDraftResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [draftError, setDraftError] = useState("");
  // 공종별 페이지(1-base) — 탭 전환에도 유지.
  const [pageByKey, setPageByKey] = useState<Partial<Record<BoqDisciplineKey, number>>>({});
  // 섹션 접기 상태 — key: `${disciplineKey}:${sectionCode}` (true = 접힘).
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const buildRequest = useCallback((): BoqAutoDraftRequest => {
    return {
      gfa_sqm: gfaNum,
      ...(unitValid ? { unit_count: unitNum } : {}),
      project_id: projectId,
    };
  }, [gfaNum, unitValid, unitNum, projectId]);

  const handleGenerate = useCallback(async () => {
    if (!gfaValid || generating) return;
    setGenerating(true);
    setDraftError("");
    setApplyResult(null);
    setApplyError("");
    try {
      const res = await apiClient.post<BoqAutoDraftResponse>(BOQ_AUTO_API.draft, {
        body: buildRequest() as unknown as Record<string, unknown>,
      });
      setDraft(res);
      setPageByKey({});
      setCollapsed({});
    } catch (e) {
      setDraftError(errorMessage(e, "공내역 드래프트 생성에 실패했습니다."));
    } finally {
      setGenerating(false);
    }
  }, [gfaValid, generating, buildRequest]);

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
      const res = await fetch(`${apiV1BaseUrl()}${BOQ_AUTO_API.export}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          ...buildRequest(),
          ...(draft?.draft_id ? { draft_id: draft.draft_id } : {}),
        }),
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
      anchor.download = `boq_auto_${projectId}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "엑셀 내보내기에 실패했습니다.");
    } finally {
      setExporting(false);
    }
  }, [gfaValid, exporting, buildRequest, draft?.draft_id, projectId]);

  /* ── ⑥ 수지 반영 후보(apply-cost) — store 직접 쓰기 금지, 후보 표기만 ── */
  const handleApplyCost = useCallback(async () => {
    if (!gfaValid || applying) return;
    setApplying(true);
    setApplyError("");
    try {
      const res = await apiClient.post<BoqApplyCostResponse>(BOQ_AUTO_API.applyCost, {
        body: {
          ...buildRequest(),
          ...(draft?.draft_id ? { draft_id: draft.draft_id } : {}),
        } as unknown as Record<string, unknown>,
      });
      setApplyResult(res);
    } catch (e) {
      setApplyResult(null);
      setApplyError(errorMessage(e, "수지 반영 후보 산출에 실패했습니다."));
    } finally {
      setApplying(false);
    }
  }, [gfaValid, applying, buildRequest, draft?.draft_id]);

  /* ── 활성 탭 파생 데이터(순수 계산 — 결정론) ── */
  const activeDiscipline = useMemo(
    () => findDraftDiscipline(draft, activeKey),
    [draft, activeKey],
  );
  const activeItems = useMemo(
    () => activeDiscipline?.items ?? [],
    [activeDiscipline],
  );
  const totalRows = activeDiscipline?.total_item_count ?? activeItems.length;
  const pageCount = Math.max(1, Math.ceil(activeItems.length / PAGE_SIZE));
  const page = Math.min(pageByKey[activeKey] ?? 1, pageCount);
  const pageItems = useMemo(
    () => activeItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [activeItems, page],
  );
  const pageSections = useMemo(() => groupBySection(pageItems), [pageItems]);

  // 신뢰도 낮음(low) 항목 수 — 전 공종 합산(상단 고정 경고용).
  const lowConfidenceCount = useMemo(() => {
    if (!draft?.disciplines) return 0;
    let n = 0;
    for (const d of draft.disciplines) {
      for (const it of d.items ?? []) {
        if ((it.confidence ?? "").toLowerCase() === "low") n += 1;
      }
    }
    return n;
  }, [draft]);

  const provenanceText =
    master?.project?.provenance ??
    draft?.badges?.provenance ??
    "실적 공내역서 1건(n=1) 기반 표준항목 — 참고치";

  /* ═══ 렌더 ═══ */

  return (
    <div className="grid gap-6">
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

        {/* 액션 줄 */}
        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line)] px-6 py-4">
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={!gfaValid || generating}
            className="rounded-xl bg-[var(--accent)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-white shadow-[var(--shadow-glow)] hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            {generating ? "생성 중…" : "공내역 드래프트 생성"}
          </button>
          <button
            type="button"
            onClick={() => void handleExport()}
            disabled={!gfaValid || exporting}
            className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
          >
            {exporting ? "엑셀 준비 중…" : "엑셀 다운로드 (전체 항목)"}
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
            {lowConfidenceCount > 0 && (
              <span className="rounded-full border border-[var(--status-error)]/40 bg-[var(--status-error)]/10 px-2.5 py-1 text-[10px] font-black text-[var(--status-error)]">
                신뢰도 낮음 항목 {fmt(lowConfidenceCount)}건 — 개별 확인 필요
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
                  {activeDiscipline?.truncated ? (
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
                                <th className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">근거</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sec.items.map((it) => {
                                const low = (it.confidence ?? "").toLowerCase() === "low";
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
                                      {fmtQty(it.qty)}
                                    </td>
                                    <td className="px-4 py-2">
                                      <span
                                        title={basisTitle}
                                        className="inline-flex cursor-help items-center gap-1 rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]"
                                      >
                                        {it.driver?.trim() || "근거 보기"}
                                      </span>
                                      {low && (
                                        <span
                                          title="이 항목의 파라메트릭 신뢰도가 낮습니다 — 전문 적산 검토에서 우선 확인하세요."
                                          className="ml-1 inline-flex cursor-help items-center rounded-full border border-[var(--status-error)]/40 bg-[var(--status-error)]/10 px-2 py-0.5 text-[9px] font-black text-[var(--status-error)]"
                                        >
                                          신뢰도 낮음
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
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <CandidateKpi
                label="총액 후보"
                value={applyResult.total_won != null ? `${fmt(applyResult.total_won)} 원` : "산출 불가"}
                highlight
              />
              <CandidateKpi
                label="직접비"
                value={applyResult.direct_won != null ? `${fmt(applyResult.direct_won)} 원` : "—"}
              />
              <CandidateKpi
                label="간접비"
                value={applyResult.indirect_won != null ? `${fmt(applyResult.indirect_won)} 원` : "—"}
              />
              <CandidateKpi
                label="㎡당 후보"
                value={applyResult.per_sqm_won != null ? `${fmt(applyResult.per_sqm_won)} 원/㎡` : "—"}
              />
            </div>

            <EvidencePanel
              title="후보 산출 근거"
              items={
                [
                  applyResult.source
                    ? { label: "단가 출처", value: applyResult.source }
                    : null,
                  applyResult.priced_item_count != null
                    ? {
                        label: "단가 매칭",
                        value: `${fmt(applyResult.priced_item_count)}건`,
                        basis:
                          applyResult.unpriced_item_count != null
                            ? `미매칭 ${fmt(applyResult.unpriced_item_count)}건 — 미매칭분은 총액에서 제외(가짜값 금지)`
                            : null,
                      }
                    : null,
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
              이 금액은 <b>후보치</b>이며 수지(costData)에 자동 반영되지 않습니다. 반영하려면{" "}
              <b>공사비(COST) 모듈</b>의 기존 “공사비 정밀 분석 → 수지 반영” 흐름에서
              검토 후 적용하세요(이 화면은 출처·근거 확인용입니다).
              {applyResult.note || applyResult.badges?.note ? (
                <span className="mt-1 block text-[10px] text-[var(--text-hint)]">
                  {String(applyResult.note ?? applyResult.badges?.note)}
                </span>
              ) : null}
            </div>
          </div>
        </section>
      )}
    </div>
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
