"use client";

/**
 * 토지필지 종합분석 P0 — 견적·선별(무과금).
 *
 * ## 왜 이 화면이 있는가
 * 등기 발급·권리분석은 건당 3,200원(발급 1,200원+분석 2,000원)이고, 건물이 있으면
 * 토지·건물이 별개 등기라 ×2가 된다. 20필지를 그대로 돌리면 최대 12.8만원이
 * **버튼 한 번에** 빠진다. 이 화면은 발급 **전에** 그 비용을 보여주고, 사용자가
 * 돈을 쓸 필지를 스스로 고르게 한다 — 그게 존재 이유의 전부다.
 *
 * ## 정직성 규칙(백엔드 계약을 그대로 따른다 — 여기서 새로 단정하지 않는다)
 * - 비용은 **범위**로 보여준다(min≠max면 뭉개지 않는다).
 * - `billing_basis==="issued_count"` → 실제 청구는 **발급 성공분만**이라는 사실을 항상 노출한다.
 * - `geometry.missing`이 있으면 그 필지 목록과 함께 "제척 위상판정 불가" 경고를 보여준다.
 * - `preview.note`는 그대로 노출한다 — 핵심필지는 **후보**이지 확정이 아니다(단정 문구 신설 금지).
 *
 * ## 재사용
 * - API 호출: 공용 `apiClient.post`(POST /registry/survey/quote — 무과금·인증필요).
 * - 마크다운 굵게(**) 렌더: 공용 `MarkdownLite`(백엔드 note 필드가 ** 강조를 포함한다).
 * - 다필지 소스: 프로젝트 SSOT(`useProjectContextStore.siteAnalysis.parcels`)에서 불러오기 지원
 *   (이미 PNU·geometry를 보유한 필지는 폴리곤 재획득 없이 정확한 위상판정 입력이 된다).
 * - 새 필지는 지번 여러 줄 붙여넣기(줄바꿈 분리) — 저장소에 이 패턴을 뽑아낸 표준 컴포넌트가
 *   없어(BulkParcelBatchPanel의 PNU 텍스트영역·RegistryAnalysisWorkspaceClient의 등기부 텍스트영역이
 *   가장 가까운 선례) 그 스타일을 따라 이 화면 안에 인라인으로 구현했다.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Calculator, Layers, Loader2, ListPlus, Trash2 } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { ParcelPurchaseStrategyPanel } from "./ParcelPurchaseStrategyPanel";
import { normalizePnu, parcelDedupKey, parcelDisplayAddress, projectParcelIdentityKey } from "@/lib/pnu";
import { withCommas } from "@/lib/formatters";
import { MarkdownLite } from "@/components/common/MarkdownLite";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

/** 화면 안에서만 쓰는 필지 입력 행 — 백엔드 요청 payload보다 표시용 필드(key)가 더 있다. */
interface QuoteParcelRow {
  key: string;
  /** 백엔드로 보내는 값 — **표시용과 분리한다**(표시 라벨을 그대로 보내면 계약이 흔들린다). */
  address: string;
  /** 화면 표기 전용. 동 단위 주소만 온 경우 PNU 에서 파생한 지번을 붙여 **행을 구분 가능**하게 한다. */
  label?: string;
  pnu?: string | null;
  geometry?: unknown;
  /** true=건물 있음 · false=토지만 · undefined=미상(모르면 절대 false로 접지 않는다). */
  hasBuilding?: boolean;
  source: "paste" | "project";
}

interface SurveyQuoteResponse {
  quote: {
    parcel_count: number;
    fee_per_unit: { issue: number; analysis: number; total: number };
    units: { min: number; max: number };
    estimated_cost: { min: number; max: number };
    building_status: { with_building: number; land_only: number; unknown: number };
    geometry: { available: number; missing: string[]; note: string };
    billing_basis: string;
    note: string;
  };
  preview: {
    available: boolean;
    graph?: {
      articulation_points?: string[];
      critical_parcels?: { CRITICAL?: string[]; IMPORTANT?: string[]; NORMAL?: string[] };
    } | null;
    note?: string;
  };
}

function wonRange(min: number, max: number): string {
  const a = `${withCommas(Math.round(min))}원`;
  if (Math.round(min) === Math.round(max)) return a;
  return `${withCommas(Math.round(min))}~${withCommas(Math.round(max))}원`;
}

export function ParcelSurveyQuotePanel({ locale }: { locale: Locale }) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectParcels = useProjectContextStore((s) => s.siteAnalysis?.parcels);

  const [rows, setRows] = useState<QuoteParcelRow[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [rawText, setRawText] = useState("");

  const [quote, setQuote] = useState<SurveyQuoteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const reqId = useRef(0);

  // 붙여넣은 지번을 목록에 추가 — 줄바꿈 분리, 빈 줄 제거, 이미 있는 주소는 중복 추가 안 함.
  const addFromPaste = () => {
    const lines = rawText
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (lines.length === 0) return;
    setRows((prev) => {
      // 붙여넣기 행은 PNU 가 없어 주소가 곧 키다 — 그래도 **같은 헬퍼**를 쓴다(규칙 분기 방지).
      const existing = new Set(prev.map((r) => parcelDedupKey(r)).filter(Boolean) as string[]);
      const added: QuoteParcelRow[] = [];
      for (const addr of lines) {
        const k = parcelDedupKey({ address: addr });
        if (!k || existing.has(k)) continue;
        existing.add(k);
        added.push({ key: `paste:${addr}:${prev.length + added.length}`, address: addr, source: "paste" });
      }
      return [...prev, ...added];
    });
    setRawText("");
  };

  // 프로젝트 SSOT에 이미 등록된 필지 불러오기 — geometry·pnu를 보유하고 있으면 그대로 넘어와
  // 재획득 없이도 위상판정(제척 가능/불가)이 가능해진다.
  const addFromProject = () => {
    if (!projectParcels || projectParcels.length === 0) return;
    setRows((prev) => {
      // ★★근본수정 — 종전에는 **주소로** 중복제거해서, 같은 동의 필지 77개가 **1건으로 접혔다**
      //   (신고: "현재 프로젝트 필지 불러오기 (77)" 인데 목록에 1건).
      //   필지의 정체성은 주소가 아니라 **PNU** 다. 같은 함수가 React key 는 이미
      //   `p.pnu || p.address` 로 잡고 있었는데 중복제거만 주소로 남아 있었다.
      //   저장소 기준선도 `pnu || address` 다(GlobalAddressSearch·satong-map-selection 등).
      const existing = new Set(prev.map((r) => parcelDedupKey(r)).filter(Boolean) as string[]);
      const added: QuoteParcelRow[] = [];
      for (const [i, p] of projectParcels.entries()) {
        // ★규칙은 `projectParcelIdentityKey` 한 곳에만 있다(종전엔 여기 인라인 + 테스트에 재구현).
        //   ★★종전 조건은 `p.pnu ?` 였다 — **참/거짓만** 보므로 PNU 칸에 들어앉은 가짜
        //   (`'store-rep-<주소>'`·성명)가 truthy 라 **인덱스 탈출구를 건너뛰었다.**
        //   가짜는 주소에서 파생되므로 동 단위 주소를 공유하면 **전원 같은 키** = 77→1 재발.
        const pnu = normalizePnu(p.pnu);
        const k = projectParcelIdentityKey(p, i);
        if (existing.has(k)) continue;
        existing.add(k);
        added.push({
          key: `project:${pnu || p.address}:${i}`,
          address: p.address,
          label: parcelDisplayAddress(p.address, pnu),
          // ★가짜 PNU 를 행에 담지 않는다 — 담으면 견적 요청 본문에 그대로 실려 나가고,
          //   서버는 그것을 echo 하며 `jibun:null·area_sqm:0` 을 돌려준다(볼트 2026-08-20 실측).
          pnu,
          geometry: p.geometry ?? undefined,
          // builtYear가 있으면 건축물 존재 확인 신호. 없다고 "토지만"으로 단정하지 않는다(모름=undefined).
          hasBuilding: typeof p.builtYear === "number" ? true : undefined,
          source: "project",
        });
      }
      return [...prev, ...added];
    });
  };

  useEffect(() => {
    // 새로 추가된 행은 기본 선택 상태로 켠다(기존 선택은 보존).
    setSelected((prev) => {
      const next = { ...prev };
      for (const r of rows) if (!(r.key in next)) next[r.key] = true;
      return next;
    });
  }, [rows]);

  const removeRow = (key: string) => {
    setRows((prev) => prev.filter((r) => r.key !== key));
    setSelected((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const allSelected = rows.length > 0 && rows.every((r) => selected[r.key]);
  const toggleAll = () => {
    const next: Record<string, boolean> = {};
    for (const r of rows) next[r.key] = !allSelected;
    setSelected(next);
  };

  const selectedRows = useMemo(() => rows.filter((r) => selected[r.key]), [rows, selected]);

  // 선택 변경(체크박스·추가·삭제) 시 견적 재계산 — 서명이 바뀔 때만 재호출한다.
  const signature = useMemo(
    () =>
      JSON.stringify(
        selectedRows.map((r) => [r.address, r.pnu ?? null, r.hasBuilding ?? null, Boolean(r.geometry)]),
      ),
    [selectedRows],
  );

  useEffect(() => {
    // ★선택 0건이어도 reqId는 반드시 올린다 — 안 올리면 이미 나간 요청이 나중에 도착했을 때
    //   "최신 요청과 같다"고 오판해 방금 비운 견적 위에 옛 응답을 덮어쓴다(레이스).
    const myReq = ++reqId.current;
    if (selectedRows.length === 0) {
      setQuote(null);
      setError("");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const body = {
      parcels: selectedRows.map((r) => ({
        // ★형제 누락 봉합 — 이 `address` 는 등기 조회 키다(`/registry/survey/quote`).
        //   지번 없는 동 단위 주소는 등기조회를 깨뜨린다(2026-08-18 실측).
        //   파생 지번은 바로 아래 함께 보내는 그 PNU 에서 나오므로 모순될 수 없다.
        address: parcelDisplayAddress(r.address, r.pnu),
        ...(r.pnu ? { pnu: r.pnu } : {}),
        ...(r.hasBuilding != null ? { has_building: r.hasBuilding } : {}),
        ...(r.geometry ? { geometry: r.geometry } : {}),
      })),
    };
    apiClient
      .post<SurveyQuoteResponse>("/registry/survey/quote", { body, timeoutMs: 30000 })
      .then((r) => {
        if (reqId.current !== myReq) return; // 더 최신 요청이 이미 나감 — 이 응답은 버린다.
        setQuote(r);
      })
      .catch((e: unknown) => {
        if (reqId.current !== myReq) return;
        setError(e instanceof Error ? e.message : "견적 조회에 실패했습니다.");
        setQuote(null);
      })
      .finally(() => {
        if (reqId.current === myReq) setLoading(false);
      });
    // signature가 selectedRows의 판정 입력을 전부 반영하므로 selectedRows 자체는 의존성에서 뺀다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  const q = quote?.quote;
  const preview = quote?.preview;

  // ★P2 매입전략은 **이 패널의 선택을 그대로 받는 후속 단계**다(계획서 §6: 신규 화면 0개).
  //   견적(P0·무과금)에서 비용을 확인한 뒤 진입하며, 실행은 그 패널이 확인을 한 번 더 받는다.
  const strategyParcels = useMemo(
    () =>
      selectedRows.map((r) => ({
        address: r.address,
        pnu: r.pnu ?? null,
        hasBuilding: r.hasBuilding ?? null,
        geometry: r.geometry,
      })),
    [selectedRows],
  );

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <Calculator className="size-6 shrink-0 text-[var(--accent-strong)]" aria-hidden />
            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="cc-meta">REGISTRY · SURVEY QUOTE</span>
                <span className="cc-chip-data">무과금</span>
              </div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">발급 전 비용 견적·선별</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)] break-keep">
                등기 발급·권리분석은 건당 과금됩니다. 이 화면은 <span className="font-bold text-[var(--accent-strong)]">발급하지 않고</span> 예상
                비용과 지금 알 수 있는 것을 먼저 보여줍니다 — 비용을 쓸 필지를 선별한 뒤 실제 발급으로 넘어가세요.
              </p>
            </div>
          </div>

          {/* 입력 — 지번 여러 줄 붙여넣기(줄바꿈 분리) */}
          <div className="mt-5 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                필지 지번 입력
              </span>
              {projectId && projectParcels && projectParcels.length > 0 && (
                <button
                  onClick={addFromProject}
                  className="rounded-lg border border-[var(--line)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] hover:border-[var(--accent-strong)]"
                >
                  <span className="inline-flex items-center gap-1">
                    <Layers className="size-3.5" aria-hidden />
                    현재 프로젝트 필지 불러오기 ({projectParcels.length})
                  </span>
                </button>
              )}
            </div>
            <textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              rows={4}
              placeholder={"지번을 한 줄에 하나씩 붙여넣으세요\n예) 서울특별시 동작구 상도동 211-376"}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            <button
              onClick={addFromPaste}
              disabled={!rawText.trim()}
              className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
            >
              <span className="inline-flex items-center gap-1.5">
                <ListPlus className="size-3.5" aria-hidden />
                목록에 추가
              </span>
            </button>
          </div>

          {/* 필지 목록 — 선별 UI(체크박스) */}
          {rows.length > 0 && (
            <div className="mt-5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[11px] font-bold text-[var(--text-secondary)]">
                  필지 목록 ({rows.length}) · 선택 {selectedRows.length}건
                </p>
                <button onClick={toggleAll} className="text-[11px] font-bold text-[var(--accent-strong)] hover:underline">
                  {allSelected ? "전체 해제" : "전체 선택"}
                </button>
              </div>
              <div className="mt-2 space-y-1.5">
                {rows.map((r) => (
                  <label
                    key={r.key}
                    className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2"
                  >
                    <input
                      type="checkbox"
                      checked={Boolean(selected[r.key])}
                      onChange={(e) => setSelected((prev) => ({ ...prev, [r.key]: e.target.checked }))}
                      className="size-4 accent-[var(--accent-strong)]"
                    />
                    <span className="min-w-[160px] flex-1 truncate text-xs font-semibold text-[var(--text-primary)]" title={r.label || r.address}>
                      {r.label || r.address}
                    </span>
                    {r.pnu && <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]">PNU 확보</span>}
                    {r.geometry ? (
                      <span className="rounded-full bg-[var(--status-success)]/10 px-2 py-0.5 text-[10px] font-bold text-[var(--status-success)]">폴리곤 확보</span>
                    ) : (
                      <span className="rounded-full bg-[var(--status-warning)]/10 px-2 py-0.5 text-[10px] font-bold text-[var(--status-warning)]">폴리곤 미확보</span>
                    )}
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); removeRow(r.key); }}
                      title="목록에서 제거"
                      className="ml-auto text-[var(--status-error)]"
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </button>
                  </label>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 견적 결과 */}
      {rows.length > 0 && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-6">
            <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
              <Calculator className="size-4" aria-hidden /> 예상 비용
            </p>

            {selectedRows.length === 0 && (
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">선택된 필지가 없습니다. 위 목록에서 견적을 볼 필지를 선택하세요.</p>
            )}

            {loading && (
              <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
                <Loader2 className="size-3.5 animate-spin" aria-hidden /> 견적 계산 중…
              </p>
            )}

            {error && !loading && (
              <p className="mt-2 text-xs font-semibold text-[var(--status-error)]">{error}</p>
            )}

            {q && !loading && (
              <div className="mt-3 space-y-4">
                <div>
                  <p className="text-2xl font-black text-[var(--text-primary)]">{wonRange(q.estimated_cost.min, q.estimated_cost.max)}</p>
                  <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">
                    필지당 발급 {withCommas(q.fee_per_unit.issue)}원 + 분석 {withCommas(q.fee_per_unit.analysis)}원 = {withCommas(q.fee_per_unit.total)}원
                    (건물이 있으면 토지·건물 별개 등기라 ×2) · 선택 {q.parcel_count}필지
                  </p>
                </div>

                {/* 건축물 유무 미상이면 그게 "범위"로 나온 이유다 — 반드시 문장으로 설명 */}
                {q.building_status.unknown > 0 && (
                  <p className="rounded-xl border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-3 py-2 text-[11px] font-semibold text-[var(--text-primary)] break-keep">
                    건축물 유무가 확인되지 않은 필지가 {q.building_status.unknown}건 있어, 위 비용은 최솟값(전부 토지로 가정)~최댓값(전부 건물 있음으로
                    가정)의 범위로 표시됩니다. (건물 있음 {q.building_status.with_building}건 · 토지만 {q.building_status.land_only}건)
                  </p>
                )}

                {/* billing_basis=issued_count — 과대공포 방지를 위해 항상 노출 */}
                <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2.5">
                  <MarkdownLite text={q.note} className="text-[11px] leading-relaxed text-[var(--text-secondary)]" />
                </div>

                {/* geometry.missing — 제척 위상판정 불가 경고 + 대상 목록 */}
                {q.geometry.missing.length > 0 && (
                  <div className="rounded-xl border border-[var(--status-error)]/30 bg-[var(--status-error)]/10 px-3 py-2.5">
                    <p className="inline-flex items-center gap-1.5 text-[11px] font-black text-[var(--status-error)]">
                      <AlertTriangle className="size-3.5" aria-hidden /> 폴리곤 미확보 {q.geometry.missing.length}필지 — 제척 가능/불가 위상판정 불가
                    </p>
                    <MarkdownLite text={q.geometry.note} className="mt-1 text-[11px] text-[var(--text-secondary)]" />
                    <ul className="mt-1.5 flex flex-wrap gap-1.5">
                      {q.geometry.missing.map((id) => (
                        <li key={id} className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]" title={id}>
                          {id}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 무료 미리보기 — preview.note를 그대로 노출(핵심필지는 "후보", 여기서 새로 단정하지 않는다) */}
                {preview && (
                  <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2.5">
                    <p className="text-[11px] font-black text-[var(--text-primary)]">등기 없이 지금 알 수 있는 것</p>
                    {preview.available && preview.graph?.articulation_points && preview.graph.articulation_points.length > 0 && (
                      <p className="mt-1 text-[11px] font-semibold text-[var(--text-secondary)]">
                        제척 불가 후보 {preview.graph.articulation_points.length}필지
                      </p>
                    )}
                    {preview.note && <MarkdownLite text={preview.note} className="mt-1 text-[11px] text-[var(--text-secondary)]" />}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ★P2 매입전략 — 견적 뒤에 온다(순서가 곧 안내다: 비용을 본 뒤 유료 실행) */}
      <ParcelPurchaseStrategyPanel parcels={strategyParcels} />

      <Link href={`/${locale}/registry-analysis`} className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
        ← 등기부등본 열람으로 돌아가기
      </Link>
    </div>
  );
}
