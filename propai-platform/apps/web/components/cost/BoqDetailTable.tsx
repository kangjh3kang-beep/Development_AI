"use client";

/**
 * BOQ 상세 내역서(수백행) + D4 단가 3중 비교 + AI 해설.
 *  ① POST /api/v1/cost/{pid}/boq → 공종별 코드·물량·단가·금액 내역서 + summary(직접·간접·총·신뢰등급).
 *     각 단가에 price_source·basis_year·qto_source(bim ±5% / derived ±12%) 배지.
 *  ② GET /api/v1/cost/unit-prices → 표준(품셈)/시장(KCCI)/실적(null) 단가 3중 비교.
 *  ③ ai_cost_analysis(있으면) AI 해설 카드.
 *  ④ summary 카드 "이 적산 결과를 수지분석에 반영" — BOQ 합계를 SSOT costData(source:"boq")로
 *     1방향 주입. 수지 화면의 기존 공사비 오버라이드 라인이 costData를 소비하므로 백엔드 무변경,
 *     cost 갱신 stamp가 수지·금융 staleness를 자동 트리거한다.
 * 정직성 note·전문 적산사 검토 배지.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Bot, Download } from "lucide-react";
import { apiClient, apiV1BaseUrl } from "@/lib/api-client";
import { PYEONG_SQM } from "@/lib/formatters";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { isValidLocale } from "@/i18n/config";
import { BOQ_AUTO_API, type BoqMasterSummaryResponse } from "@/components/cost/boqAutoTypes";
import type {
  BoqEstimateListItem,
  BoqEstimatesListResponse,
  BoqResponse,
  UnitPricesResponse,
} from "@/components/cost/cmTypes";

const fcls =
  "w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

/** 공종별 마스터 집계(record/배열 양형)의 합계 — 허브 요약카드용(BoqAutoWorkspace 탭별 정규화는 불필요). */
function sumMasterTotals(res: BoqMasterSummaryResponse | null): { items: number; sections: number } {
  const src = res?.disciplines;
  if (!src) return { items: 0, sections: 0 };
  const rows = Array.isArray(src) ? src : Object.values(src);
  return rows.reduce<{ items: number; sections: number }>(
    (acc, d) => ({
      items: acc.items + (d?.unique_items ?? 0),
      sections: acc.sections + (d?.sections ?? 0),
    }),
    { items: 0, sections: 0 },
  );
}

function won(v?: number | null): string {
  if (v == null || isNaN(v)) return "—";
  return `${Math.round(v).toLocaleString()}원`;
}
function eok(v?: number | null): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`;
}

function QtoBadge({ source }: { source?: string }) {
  const isBim = source === "bim";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
        isBim ? "bg-emerald-500/15 text-emerald-400" : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
      }`}
    >
      {isBim ? "BIM ±5%" : "추정 ±12%"}
    </span>
  );
}

export function BoqDetailTable({ projectId: projectIdProp }: { projectId?: string }) {
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const designData = useProjectContextStore((s) => s.designData);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);
  const projectId = projectIdProp || ctxProjectId || "default";
  // 상세 워크플로우(BoqAutoWorkspace)는 실제 프로젝트 선택 시에만 연결(더미 "default" 방지).
  const hasRealProject = !!(projectIdProp || ctxProjectId);
  const routeParams = useParams() as { locale?: string };
  const locale = isValidLocale(routeParams?.locale ?? "") ? (routeParams.locale as string) : "ko";

  // P2 T3: BOQ 허브 요약(마스터 통계 + 상세 워크플로우 진입) — BoqAutoWorkspace 자체는
  // 임베드하지 않고 요약 카드+링크로만 연결(중복 렌더 금지).
  const [masterSummary, setMasterSummary] = useState<BoqMasterSummaryResponse | null>(null);
  useEffect(() => {
    let cancelled = false;
    void apiClient
      .get<BoqMasterSummaryResponse>(BOQ_AUTO_API.masterSummary, { useMock: false, timeoutMs: 20000 })
      .then((res) => {
        if (!cancelled) setMasterSummary(res);
      })
      .catch(() => {
        /* 마스터 요약 실패는 조용히 무시 — 상세적산(BOQ) 본 기능은 계속 이용 가능 */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const masterTotals = useMemo(() => sumMasterTotals(masterSummary), [masterSummary]);

  const [bt, setBt] = useState("apartment");
  const [gfa, setGfa] = useState<string>(
    designData?.totalGfaSqm ? String(Math.round(designData.totalGfaSqm)) : "",
  );
  const [floorsAbove, setFloorsAbove] = useState<string>(
    designData?.floorCount ? String(designData.floorCount) : "15",
  );
  const [floorsBelow, setFloorsBelow] = useState<string>("2");
  const [structure, setStructure] = useState("RC");

  const [boq, setBoq] = useState<BoqResponse | null>(null);
  const [prices, setPrices] = useState<UnitPricesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  // T3: use_llm 옵트인 — 기존 동작(AI 해설 항상 포함)을 보존하기 위해 기본 true로 명시 전송.
  const [useLlm, setUseLlm] = useState(true);
  // 수지 반영용 — BOQ 실행 시점의 연면적 스냅샷(이후 입력 변경과 무관하게 결과와 정합 유지).
  const [boqGfaSqm, setBoqGfaSqm] = useState<number | null>(null);
  const [applied, setApplied] = useState(false);

  // T5: 영속 BOQ 조회 — "저장된 적산 목록"(GET /estimates) + 선택 시 단건 로드(GET /estimate/{id}).
  const [savedList, setSavedList] = useState<BoqEstimateListItem[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [loadingEstimateId, setLoadingEstimateId] = useState<string | null>(null);
  // F-2: "저장된 적산 목록" 각 행 엑셀 다운로드(GET /export-excel?estimate_id=) 진행 상태.
  const [exportingEstimateId, setExportingEstimateId] = useState<string | null>(null);
  const [exportErr, setExportErr] = useState("");

  const refreshSavedList = useCallback(async () => {
    setSavedLoading(true);
    try {
      const res = await apiClient.get<BoqEstimatesListResponse>(
        `/cost/${projectId}/estimates`, { useMock: false, timeoutMs: 20000 },
      );
      setSavedList(res.items ?? []);
    } catch {
      /* 목록 조회 실패는 조용히 무시 — 신규 적산 실행은 계속 가능 */
    } finally {
      setSavedLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void refreshSavedList();
  }, [refreshSavedList]);

  const loadSavedEstimate = useCallback(async (estimateId: string) => {
    setLoadingEstimateId(estimateId);
    setErr("");
    try {
      const res = await apiClient.get<BoqResponse & { total_gfa_sqm?: number }>(
        `/cost/estimate/${estimateId}`, { useMock: false, timeoutMs: 20000 },
      );
      setBoq(res);
      setBoqGfaSqm(res.total_gfa_sqm ?? null);
      setApplied(false);
    } catch {
      setErr("저장된 적산을 불러오지 못했습니다.");
    } finally {
      setLoadingEstimateId(null);
    }
  }, []);

  // F-2: 저장된 적산(estimate) 1건을 Excel(원가계산서)로 다운로드 — GET /export-excel?estimate_id=
  // (BE 기존 additive 쿼리 — BoqAutoWorkspace.handleExport와 동일한 Bearer+blob 패턴, apiClient는
  //  JSON 파싱 전제라 바이너리 다운로드에 부적합해 여기서만 raw fetch를 쓴다).
  const downloadExcel = useCallback(async (estimateId: string) => {
    if (exportingEstimateId) return;
    setExportingEstimateId(estimateId);
    setExportErr("");
    try {
      const token = typeof window !== "undefined"
        ? window.localStorage.getItem("propai_access_token") ?? "" : "";
      const res = await fetch(
        `${apiV1BaseUrl()}/cost/${projectId}/export-excel?estimate_id=${encodeURIComponent(estimateId)}`,
        { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } },
      );
      const ct = res.headers.get("content-type") ?? "";
      if (!res.ok || ct.includes("application/json")) {
        let msg = `엑셀 다운로드에 실패했습니다 (HTTP ${res.status}).`;
        try { const j = await res.json(); msg = j?.detail || j?.message || msg; } catch { /* noop */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cost_sheet_${projectId}_${estimateId.slice(0, 8)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportErr(e instanceof Error ? e.message : "엑셀 다운로드에 실패했습니다.");
    } finally {
      setExportingEstimateId(null);
    }
  }, [projectId, exportingEstimateId]);

  const run = useCallback(async () => {
    const gfaNum = Number(gfa);
    if (!gfaNum || gfaNum <= 0) {
      setErr("연면적(GFA)을 입력하세요.");
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const [boqRes, priceRes] = await Promise.all([
        apiClient.post<BoqResponse>(`/cost/${projectId}/boq`, {
          body: {
            building_type: bt,
            total_gfa_sqm: gfaNum,
            floor_count_above: Number(floorsAbove) || 1,
            floor_count_below: Number(floorsBelow) || 0,
            structure_type: structure,
            persist: true,
            use_llm: useLlm,
          },
          useMock: false,
          timeoutMs: 60000,
        }),
        apiClient
          .get<UnitPricesResponse>("/cost/unit-prices", { useMock: false, timeoutMs: 30000 })
          .catch(() => null),
      ]);
      setBoq(boqRes);
      setBoqGfaSqm(gfaNum);
      setApplied(false); // 새 적산 결과 — 이전 "반영됨" 표시 해제
      if (priceRes) setPrices(priceRes);
      void refreshSavedList(); // persist:true로 새 적산이 저장됐으므로 목록 갱신
    } catch {
      setErr("BOQ 상세적산에 실패했습니다. 입력값을 확인하세요.");
    } finally {
      setLoading(false);
    }
  }, [bt, gfa, floorsAbove, floorsBelow, structure, projectId, useLlm, refreshSavedList]);

  // BOQ 합계 → 수지 costData 1방향 주입(WP-08). CostData는 full replace 계약이므로
  // BOQ summary가 제공하지 않는 분해 항목(지상/지하/조경·신뢰범위)은 가짜값 대신 null 유지
  // (confidence_band는 문자열 라벨이라 수치 범위로 환산하지 않는다).
  const applyToFeasibility = useCallback(() => {
    const s = boq?.summary;
    if (!s || !(s.total > 0)) return;
    const perSqm = boqGfaSqm && boqGfaSqm > 0 ? s.total / boqGfaSqm : null;
    updateCostData({
      totalConstructionCostWon: s.total,
      perSqmWon: perSqm,
      perPyeongWon: perSqm != null ? perSqm * PYEONG_SQM : null,
      abovegroundWon: null,
      undergroundWon: null,
      landscapeWon: null,
      directWon: s.direct ?? null,
      indirectWon: s.indirect ?? null,
      rangeMinWon: null,
      rangeMaxWon: null,
      source: "boq",
    });
    setApplied(true);
  }, [boq, boqGfaSqm, updateCostData]);

  const items = boq?.items ?? [];
  const summary = boq?.summary;

  const priceItems = useMemo(() => prices?.items ?? [], [prices]);

  return (
    <section className="grid gap-5">
      <div>
        <h2 className="text-xl font-black text-[var(--text-primary)]">상세 내역서 (BOQ) · 단가 3중 비교</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          공종별 물량·단가·금액 내역서와 표준/시장(KCCI)/실적 단가 3중 비교를 제공합니다. 산출물은 원가계산서로 영속화됩니다.
        </p>
      </div>

      {/* P2 T3: BOQ 허브 요약 — 실적 공내역서(5공종·414섹션) 마스터 통계 + 상세 워크플로우
          진입(BoqAutoWorkspace 임베드 없이 요약 카드+링크로만 연결·중복 렌더 금지). */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]/10 p-5">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-black text-[var(--text-primary)]">
              공내역서(BOQ) 자동작성 — 실적기반 상세 워크플로우
            </h3>
            <span
              title="표준항목 마스터는 실적 공내역서 1건(표본) 기반 참고치입니다."
              className="rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 px-2 py-0.5 text-[9px] font-black text-[var(--status-warning)]"
            >
              실적 1건 기반 참고치
            </span>
          </div>
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
            {masterSummary?.project?.name ? (
              <>
                {masterSummary.project.name}
                {masterSummary.project.gfa_sqm ? ` · GFA ${Math.round(masterSummary.project.gfa_sqm).toLocaleString()}㎡` : ""}
                {masterTotals.items > 0 ? ` · 표준항목 ${masterTotals.items.toLocaleString()}개 · ${masterTotals.sections.toLocaleString()}섹션(5공종)` : ""}
              </>
            ) : (
              "5공종(건축·기계소방·전기통신소방·조경·토목) 표준항목으로 연면적 기반 공내역 드래프트를 자동 생성합니다."
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {hasRealProject ? (
            <>
              <Link
                href={`/${locale}/projects/${projectId}/boq`}
                className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-xs font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90"
              >
                공내역 드래프트 생성하기 →
              </Link>
              <Link
                href={`/${locale}/projects/${projectId}/boq`}
                className="rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-4 py-2.5 text-xs font-bold text-[var(--accent-strong)] hover:opacity-90"
              >
                전체 화면에서 열기
              </Link>
            </>
          ) : (
            <span className="rounded-xl border border-[var(--line)] px-5 py-2.5 text-xs font-bold text-[var(--text-hint)]">
              프로젝트 선택 후 이용 가능
            </span>
          )}
        </div>
      </div>

      {/* T5: 저장된 적산 목록 — 영속화된 BOQ 재조회 */}
      <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-black text-[var(--text-primary)]">저장된 적산 목록</h3>
          <button
            onClick={() => void refreshSavedList()}
            disabled={savedLoading}
            className="text-[11px] font-bold text-[var(--accent-strong)] hover:opacity-80 disabled:opacity-50"
          >
            {savedLoading ? "새로고침 중…" : "새로고침"}
          </button>
        </div>
        {savedList.length === 0 ? (
          <p className="text-[11px] text-[var(--text-hint)]">
            {savedLoading ? "불러오는 중…" : "저장된 적산이 없습니다. 아래에서 BOQ 상세적산을 실행하면 자동 저장됩니다."}
          </p>
        ) : (
          <ul className="grid gap-2">
            {savedList.map((it) => (
              <li
                key={it.estimate_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)]/60 bg-[var(--surface-strong)] px-4 py-2.5"
              >
                <span className="text-[11px] text-[var(--text-secondary)]">
                  {it.building_type} · {it.structure_type} · {Math.round(it.total_gfa_sqm).toLocaleString()}㎡ ·{" "}
                  <b className="text-[var(--text-primary)]">{eok(it.total_won)}</b> · 신뢰등급 {it.confidence_grade || "—"} ·{" "}
                  {new Date(it.created_at).toLocaleString("ko-KR")}
                </span>
                <span className="flex items-center gap-1.5">
                  <button
                    onClick={() => void loadSavedEstimate(it.estimate_id)}
                    disabled={loadingEstimateId === it.estimate_id}
                    className="rounded-lg border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-3 py-1.5 text-[10px] font-black text-[var(--accent-strong)] hover:opacity-90 disabled:opacity-50"
                  >
                    {loadingEstimateId === it.estimate_id ? "불러오는 중…" : "불러오기"}
                  </button>
                  {/* F-2: orphan 해소 — 저장된 적산 각 건을 원가계산서 Excel로 다운로드. */}
                  <button
                    onClick={() => void downloadExcel(it.estimate_id)}
                    disabled={exportingEstimateId === it.estimate_id}
                    className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-[10px] font-black text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] disabled:opacity-50"
                  >
                    <Download className="size-3" aria-hidden />
                    {exportingEstimateId === it.estimate_id ? "내려받는 중…" : "엑셀 다운로드"}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        {exportErr && <p className="mt-2 text-[10px] font-semibold text-rose-400">{exportErr}</p>}
      </div>

      {/* 건축개요 입력 */}
      <div className="grid gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">건축유형</span>
          <select value={bt} onChange={(e) => setBt(e.target.value)} className={fcls}>
            <option value="apartment">아파트/공동주택</option>
            <option value="officetel">오피스텔</option>
            <option value="office">업무시설</option>
            <option value="townhouse">연립·다세대</option>
            <option value="warehouse">지식산업센터/창고</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">연면적(㎡)</span>
          <input value={gfa} onChange={(e) => setGfa(e.target.value)} inputMode="decimal" className={fcls} placeholder="예: 30000" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">구조</span>
          <select value={structure} onChange={(e) => setStructure(e.target.value)} className={fcls}>
            {["RC", "SRC", "SC", "PC"].map((s) => (
              <option key={s} value={s}>{s}조</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지상 층수</span>
          <input value={floorsAbove} onChange={(e) => setFloorsAbove(e.target.value)} inputMode="numeric" className={fcls} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지하 층수</span>
          <input value={floorsBelow} onChange={(e) => setFloorsBelow(e.target.value)} inputMode="numeric" className={fcls} />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={run}
          disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "상세적산 중…" : "BOQ 상세적산 실행"}
        </button>
        <UseLlmToggle
          checked={useLlm}
          onChange={setUseLlm}
          hint="AI 공사비 해설 텍스트 생성"
          disabled={loading}
        />
        {err && <span className="text-xs font-semibold text-rose-400">{err}</span>}
      </div>

      {/* AI 해설 */}
      {boq?.ai_cost_analysis && (
        <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5">
          <div className="mb-2 flex items-center gap-2">
            <Bot className="size-4 text-[var(--accent-strong)]" aria-hidden />
            <h3 className="text-sm font-black text-[var(--text-primary)]">AI 공사비 해설</h3>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-secondary)]">
            {boq.ai_cost_analysis}
          </p>
        </div>
      )}

      {/* summary */}
      {summary && (
        <div className="grid gap-3">
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">총 공사비</p>
              <p className="mt-2 text-2xl font-[1000] text-[var(--accent-strong)]">{eok(summary.total)}</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">직접비</p>
              <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{eok(summary.direct)}</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">간접비</p>
              <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{eok(summary.indirect)}</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">신뢰등급</p>
              <p className="mt-2 text-lg font-[1000] text-[var(--text-primary)]">{summary.confidence_grade || "—"}</p>
              {summary.confidence_band && (
                <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{summary.confidence_band}</p>
              )}
            </div>
          </div>
          {/* WP-08: BOQ 합계 → 수지 costData 주입 — cost stamp가 수지·금융 staleness를 트리거 */}
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-5 py-4">
            <button
              onClick={applyToFeasibility}
              disabled={!(summary.total > 0)}
              className="rounded-xl border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-5 py-2.5 text-xs font-black text-[var(--accent-strong)] hover:opacity-90 disabled:opacity-50"
            >
              이 적산 결과를 수지분석에 반영
            </button>
            {applied ? (
              <span className="text-[11px] font-bold text-emerald-400">
                반영됨 — 공사비 컨텍스트(출처: BOQ)가 갱신되어 수지·금융 재계산이 제안됩니다.
              </span>
            ) : (
              <span className="text-[11px] text-[var(--text-hint)]">
                총·직접·간접 공사비를 수지분석 공통 컨텍스트에 주입합니다(출처: BOQ).
                {!(boqGfaSqm && boqGfaSqm > 0) &&
                  " 연면적 미확인 — ㎡·평당 단가는 데이터 없음으로 처리됩니다."}
              </span>
            )}
          </div>
        </div>
      )}

      {/* BOQ 내역서 테이블 */}
      {items.length > 0 && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-black text-[var(--text-primary)]">공종별 내역서 ({items.length}행)</h3>
            {boq?.estimate_id && (
              <span className="text-[10px] text-[var(--text-hint)]">원가계산서 ID: {boq.estimate_id.slice(0, 8)}…</span>
            )}
          </div>
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0">
                <tr className="bg-[var(--surface-strong)] text-[var(--text-tertiary)]">
                  <th className="px-3 py-2 text-left font-bold">코드</th>
                  <th className="px-3 py-2 text-left font-bold">공종</th>
                  <th className="px-3 py-2 text-right font-bold">물량</th>
                  <th className="px-3 py-2 text-left font-bold">단위</th>
                  <th className="px-3 py-2 text-right font-bold">단가</th>
                  <th className="px-3 py-2 text-right font-bold">금액</th>
                  <th className="px-3 py-2 text-left font-bold">출처</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={`${it.code}-${i}`} className="border-t border-[var(--line)]/60">
                    <td className="px-3 py-2 font-mono text-[var(--text-tertiary)]">{it.code}</td>
                    <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">
                      {it.name}
                      {it.work_type && (
                        <span className="ml-1 text-[9px] text-[var(--text-hint)]">{it.work_type}</span>
                      )}
                      {/* P2 T2: 공종분류 SSOT 대공종(work_breakdown) — additive 그룹핑 칩. */}
                      {it.wb_name && (
                        <span className="ml-1.5 rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">
                          {it.wb_name}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                      {it.quantity != null ? Math.round(it.quantity).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-[var(--text-tertiary)]">{it.unit || "—"}</td>
                    <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{won(it.unit_price)}</td>
                    <td className="px-3 py-2 text-right font-bold text-[var(--text-primary)]">{won(it.amount)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">
                          {it.price_source}
                          {it.price_basis_year ? ` ${it.price_basis_year}` : ""}
                        </span>
                        <QtoBadge source={it.qto_source} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {boq?.badges?.note && (
            <p className="mt-3 text-[11px] text-[var(--text-hint)]">{boq.badges.note}</p>
          )}
        </div>
      )}

      {/* D4 단가 3중 비교 */}
      {priceItems.length > 0 && (
        <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
          <h3 className="mb-1 text-sm font-black text-[var(--text-primary)]">단가 3중 비교 (표준 · 시장 · 실적)</h3>
          <p className="mb-3 text-[11px] text-[var(--text-hint)]">
            표준=품셈/단가DB, 시장=KCCI 변동모델(시뮬레이션 · 실시세 API 아님), 실적=실데이터 없음(정직성 표기).
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[var(--text-tertiary)]">
                  <th className="px-3 py-2 text-left font-bold">자재</th>
                  <th className="px-3 py-2 text-left font-bold">단위</th>
                  <th className="px-3 py-2 text-right font-bold">표준</th>
                  <th className="px-3 py-2 text-right font-bold">시장(KCCI)</th>
                  <th className="px-3 py-2 text-right font-bold">실적</th>
                  <th className="px-3 py-2 text-left font-bold">기준연도</th>
                </tr>
              </thead>
              <tbody>
                {priceItems.map((p, i) => {
                  const diff =
                    p.market != null && p.standard > 0
                      ? ((p.market - p.standard) / p.standard) * 100
                      : null;
                  return (
                    <tr key={`${p.code}-${i}`} className="border-t border-[var(--line)]/60">
                      <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">{p.name}</td>
                      <td className="px-3 py-2 text-[var(--text-tertiary)]">{p.unit}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{won(p.standard)}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                        {p.market != null ? won(p.market) : <span className="text-[var(--text-hint)]">—</span>}
                        {diff != null && (
                          <span className={`ml-1 text-[9px] font-bold ${diff >= 0 ? "text-rose-400" : "text-emerald-400"}`}>
                            {diff >= 0 ? "+" : ""}{diff.toFixed(0)}%
                          </span>
                        )}
                        {p.market != null && p.market_source === "simulation" && (
                          <span className="ml-1 rounded bg-amber-500/15 px-1 py-0.5 text-[8px] font-bold text-amber-400">
                            시뮬레이션
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-hint)]">데이터 없음</td>
                      <td className="px-3 py-2 text-[var(--text-tertiary)]">{p.basis_year ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {prices?.note && <p className="mt-3 text-[11px] text-[var(--text-hint)]">{prices.note}</p>}
        </div>
      )}
    </section>
  );
}
