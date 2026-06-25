"use client";

/**
 * 부동산 등기정보 분석 — 법무사·변호사 AI 권리분석.
 *
 * 주소 검색/프로젝트 연동 + (등기부 미연동 시) 등기부등본 텍스트 직접 입력 →
 * 소유정보·소유기간·매입금액·보유지분·가등기·압류·근저당·매도청구 가능여부 분석.
 * 토지 소유구분·특성(공부)도 함께 제공.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ClipboardList, FileText, Receipt, Scale, ScrollText, Settings } from "lucide-react";
import Link from "next/link";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { analyzeRegistry } from "@/lib/registry-analyze";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import type { Locale } from "@/i18n/config";

const EMPTY_ROWS: LandRow[] = [];
const toOwnerType = (s?: string | null): LandRow["owner_type"] =>
  s?.includes("국") || s?.includes("공") ? "국공유지" : s ? "사유지" : "";

type Owner = { name?: string; share?: string | null; acquisition_date?: string | null };
type Land = {
  pnu?: string | null; owner_type?: string | null; land_category?: string | null;
  land_area_sqm?: number | null; official_price_per_sqm?: number | null; zone_type?: string | null;
  ownership_form?: string | null; owner_count?: number | null; owners?: Owner[]; registry_owner?: string | null;
};
type AI = {
  generated?: boolean;
  ownership?: { current_owner?: string; share?: string; acquisition_date?: string; acquisition_cause?: string; acquisition_price?: string; ownership_period?: string };
  provisional_registration?: { exists?: boolean | null; detail?: string };
  seizure?: Array<{ type?: string; holder?: string; detail?: string; date?: string }>;
  mortgage?: Array<{ max_claim?: string; mortgagee?: string; date?: string }>;
  other_rights?: string[];
  baseline_right?: string;
  acquired_extinguished?: string;
  right_to_demand_sale?: { possible?: string; reason?: string };
  rights_analysis?: string;
  risks?: string[];
  safety_grade?: string;
  summary?: string;
};
type Result = { status: string; origin?: string; land?: Land | null; message?: string; ai?: AI | null;
  fetched?: { owner?: string; registry_office?: string; doc_title?: string; has_pdf?: boolean; pdf_url?: string | null } | null };

const GRADE: Record<string, string> = {
  안전: "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]",
  주의: "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
  위험: "border-[var(--status-error)]/30 bg-[var(--status-error)]/10 text-[var(--status-error)]",
};

export function RegistryAnalysisWorkspaceClient({ locale }: { locale: Locale }) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const _rawSite = useProjectContextStore((s) => s.siteAnalysis);
  // 활성 프로젝트일 때만 컨텍스트 부지정보 사용 — 약식 검색이 등기/토지조서로 새지 않도록.
  const siteAnalysis = projectId ? _rawSite : null;
  // 토지조서와 동일 스토어 공유(프로젝트 단일 출처) — 지번 추가/삭제·분석결과가 양 페이지에 반영
  const rows = useLandScheduleStore((s) => s.byProject[projectId || "_default"] ?? EMPTY_ROWS);
  const addRow = useLandScheduleStore((s) => s.addRow);
  const removeRow = useLandScheduleStore((s) => s.removeRow);
  const updateRow = useLandScheduleStore((s) => s.updateRow);
  const setRows = useLandScheduleStore((s) => s.setRows);
  const [addr, setAddr] = useState("");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [realty, setRealty] = useState<"2" | "1" | "3" | "0">("2"); // 2토지(기본)·1집합건물·3건물
  const [dong, setDong] = useState("");
  const [ho, setHo] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null); // 지번별 분석 중
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  // ★다필지 일괄 결과(필지별 누적) — 단일 result만 덮어써 마지막 1건만 보이던 부정합 해소.
  const [batchResults, setBatchResults] = useState<{ jibun: string; rowId: string; result: Result | null }[] | null>(null);
  const [newJibun, setNewJibun] = useState("");

  const run = useCallback(async (overrideAddr?: string, rowId?: string): Promise<Result | null> => {
    const target = (typeof overrideAddr === "string" ? overrideAddr : addr) || siteAnalysis?.address || "";
    if (!target && !text.trim()) { setError("주소를 선택하거나 등기부 내용을 입력하세요."); return null; }
    if (rowId) setBusyId(rowId); else setLoading(true);
    setError(""); setResult(null); setProgress("");
    try {
      // 비동기 작업 제출+폴링(모바일 안정) — 화면 전환/잠금 후 복귀해도 결과 유지
      const r = await analyzeRegistry<Result>({
        address: target || undefined, pnu: siteAnalysis?.pnu || undefined,
        registry_text: text.trim() || undefined,
        realty_type: realty, dong: realty === "1" ? dong || undefined : undefined,
        ho: realty === "1" ? ho || undefined : undefined,
        // 부지분석에서 확보한 토지정보 동봉 → 백엔드 재조회(~31s) 생략
        land_hint: siteAnalysis
          ? {
              pnu: siteAnalysis.pnu || undefined,
              zone_type: siteAnalysis.zoneCode || undefined,
              // ★다필지면 통합면적 우선(대표값이 통합을 덮어써도 정확한 면적 사용)
              land_area_sqm: effectiveLandAreaSqm(siteAnalysis) || undefined,
            }
          : undefined,
      }, setProgress);
      setResult(r);
      // 등기분석정보 우선: 프로젝트 필지 행에 소유자·지분·소유구분·면적·PDF write-back
      // (정의된 값만 patch — undefined 전달 시 기존 값이 지워지는 것 방지)
      if (rowId) {
        const own = r.ai?.ownership || {};
        const ld = r.land || {};
        const patch: Partial<LandRow> = {};
        if (own.current_owner && own.current_owner !== "데이터 없음") patch.owner = own.current_owner;
        if (own.share && own.share !== "데이터 없음") patch.share = own.share;
        if (ld.land_area_sqm != null) patch.area_sqm = ld.land_area_sqm;
        const ot = toOwnerType(ld.owner_type);
        if (ot) patch.owner_type = ot;
        if (r.fetched?.pdf_url) patch.pdf_url = r.fetched.pdf_url;
        if (Object.keys(patch).length) updateRow(projectId, rowId, patch);
      }
      return r;
    } catch (e) {
      setError(e instanceof Error ? e.message : "등기 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
      return null;
    } finally {
      if (rowId) setBusyId(null); else setLoading(false);
      setProgress("");
    }
  }, [addr, text, siteAnalysis, realty, dong, ho, projectId, updateRow]);

  // 프로젝트 선택 시 필지 목록이 비어있으면 부지분석 필지로 시드(토지조서와 동일 규칙)
  useEffect(() => {
    if (!projectId || rows.length > 0) return;
    const parcels = siteAnalysis?.parcels;
    const mk = (jibun: string, area: number | null, ot: string): LandRow => ({
      id: Math.random().toString(36).slice(2, 9), jibun, owner: "", share: "",
      area_sqm: area, owner_type: toOwnerType(ot), expected_price: null, purchase_price: null,
      contracted: false, land_use_consent: false, district_consent: false, operator_consent: false, pdf_url: null,
    });
    if (parcels && parcels.length) setRows(projectId, parcels.map((p) => mk(p.address, p.areaSqm ?? null, p.ownerType)));
    // 폴백 단일행: 다필지면 통합면적 우선(대표값 덮어쓰기 면역).
    else if (siteAnalysis?.address) setRows(projectId, [mk(siteAnalysis.address, effectiveLandAreaSqm(siteAnalysis), "")]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, siteAnalysis]);

  // ★다필지 일괄 분석(순차 — CODEF 과부하 방지). 필지별 결과를 누적 보관(마지막 1건만 남던 부정합 해소).
  const analyzeAll = useCallback(async () => {
    setBatchResults([]);
    const acc: { jibun: string; rowId: string; result: Result | null }[] = [];
    for (const r of rows) {
      const j = r.jibun.trim();
      if (!j) continue;
      const res = await run(j, r.id);
      acc.push({ jibun: j, rowId: r.id, result: res });
      setBatchResults([...acc]);
    }
    // 종료 후 첫 성공(권리분석 ai) 필지를 상세로 고정(데스크 시세추정과 동일 UX — 마지막 1건이 남던 비대칭 해소).
    const first = acc.find((x) => x.result?.ai);
    if (first?.result) setResult(first.result);
  }, [rows, run]);

  // 토지조서 등에서 ?addr= 로 진입 시 자동 프리필 + 1회 실행
  const autoRan = useRef(false);
  useEffect(() => {
    if (autoRan.current || typeof window === "undefined") return;
    const p = new URLSearchParams(window.location.search).get("addr");
    if (p) { autoRan.current = true; setAddr(p); void run(p); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ai = result?.ai;
  const land = result?.land;
  const own = ai?.ownership || {};

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <ScrollText className="size-6 shrink-0 text-[var(--accent-strong)]" aria-hidden />
            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="cc-meta">REGISTRY · RIGHTS ANALYSIS</span>
                <span className="cc-chip-data">법무 AI</span>
              </div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">등기부등본 열람·분석</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                법무사·변호사 AI가 등기부등본을 분석해 소유정보·소유기간·매입금액·지분·가등기·압류·근저당·매도청구 가능여부를 제공합니다.
                <span className="ml-1 font-bold text-[var(--accent-strong)]">발급·열람 건당 1,200원 · 권리분석(AI) 건당 2,000원 (동일 물건 재조회 무료).</span>
              </p>
            </div>
          </div>
          <div className="mt-5">
            {/* 대상지 주소: 부지분석에서 주소가 확정된 프로젝트 진입 시엔 읽기전용 요약으로 표시(중복 입력 제거).
                신규(주소 미보유) 상태에서만 검색·입력 노출. 확정 주소(siteAnalysis.address)는 run()에서
                addr 폴백으로 그대로 사용되어 분석에 반영된다. */}
            {!siteAnalysis?.address ? (
              <ProjectAddressInput value={addr} onChange={setAddr} label="분석 대상지 주소"
                placeholder="프로젝트를 선택하거나 주소를 검색/입력하세요" pickerLabel="분석 히스토리" disabled={loading} />
            ) : (
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3.5 py-2.5">
                <p className="text-[11px] font-semibold text-[var(--text-tertiary)]">분석 대상지 주소</p>
                <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{siteAnalysis.address}</p>
              </div>
            )}
          </div>
          {/* 부동산 구분(토지/집합건물/건물) + 집합건물 동/호 */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">부동산 구분</span>
            {([["2", "토지"], ["1", "집합건물(아파트/오피스텔)"], ["3", "건물"]] as const).map(([v, label]) => (
              <button key={v} onClick={() => setRealty(v)} disabled={loading}
                className={`rounded-lg px-3 py-1.5 text-[11px] font-bold ${realty === v ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)]"}`}>
                {label}
              </button>
            ))}
            {realty === "1" && (
              <>
                <input value={dong} onChange={(e) => setDong(e.target.value)} placeholder="동(예:101)" disabled={loading}
                  className="w-24 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-[11px] text-[var(--text-primary)]" />
                <input value={ho} onChange={(e) => setHo(e.target.value)} placeholder="호(예:1203)" disabled={loading}
                  className="w-24 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-[11px] text-[var(--text-primary)]" />
              </>
            )}
          </div>
          <div className="mt-3">
            <button onClick={() => setShowText((v) => !v)} className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
              {showText ? "− 등기부 직접 입력 닫기" : "+ 등기부등본 내용 직접 입력 (연동 미설정 시)"}
            </button>
            {showText && (
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} disabled={loading}
                placeholder="등기부등본 갑구·을구 내용을 붙여넣으세요 (소유권/근저당/압류 등). 연동(CODEF) 설정 시 주소만으로 자동 조회됩니다."
                className="mt-2 w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
            )}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button onClick={() => run()} disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {loading ? "등기 분석 중…" : (<span className="inline-flex items-center gap-1.5"><Scale className="size-4" aria-hidden />등기 권리분석</span>)}
            </button>
            {loading && progress && <span className="text-xs text-[var(--text-secondary)]">{progress}</span>}
            {error && <span className="text-xs font-semibold text-[var(--status-error)]">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {/* 프로젝트 필지 목록 — 토지조서와 동일 데이터(공유). 지번 추가/삭제·지번별 분석·PDF */}
      {projectId && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]"><Receipt className="size-4" aria-hidden />프로젝트 필지 ({rows.length}) — 단일/다필지 일괄 분석</p>
              <button onClick={() => void analyzeAll()} disabled={loading || !!busyId || rows.length === 0}
                className="rounded-xl bg-[var(--accent-strong)] px-3.5 py-1.5 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
                {busyId ? "분석 중…" : (<span className="inline-flex items-center gap-1.5"><Scale className="size-4" aria-hidden />전체 분석</span>)}
              </button>
            </div>
            <div className="mt-3 space-y-1.5">
              {rows.map((r) => (
                <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2">
                  <span className="min-w-[160px] flex-1 truncate text-xs font-semibold text-[var(--text-primary)]" title={r.jibun}>{r.jibun || "(지번 미입력)"}</span>
                  {r.owner && <span className="truncate text-[11px] text-[var(--text-secondary)]">소유 {r.owner}{r.share ? ` · ${r.share}` : ""}</span>}
                  {r.area_sqm != null && <span className="text-[11px] text-[var(--text-tertiary)]">{Math.round(r.area_sqm).toLocaleString()}㎡</span>}
                  <button onClick={() => { setAddr(r.jibun); void run(r.jibun, r.id); }} disabled={!r.jibun.trim() || busyId === r.id}
                    className="rounded-lg bg-[var(--surface-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] disabled:opacity-50">
                    {busyId === r.id ? "…" : "분석"}
                  </button>
                  {r.pdf_url && (
                    <a href={r.pdf_url} target="_blank" rel="noopener noreferrer"
                      className="rounded-lg border border-[var(--accent-strong)]/40 px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)]">PDF ↓</a>
                  )}
                  <button onClick={() => removeRow(projectId, r.id)} title="지번 삭제" className="text-[var(--status-error)]">✕</button>
                </div>
              ))}
            </div>
            {/* ★일괄 권리분석 결과(필지별 누적) — 마지막 1건만 보이던 부정합 해소. '상세'로 전체 분석 표시 */}
            {batchResults && batchResults.length > 0 && (
              <div className="mt-3 space-y-1.5 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]/40 p-3">
                <p className="text-[11px] font-bold text-[var(--text-secondary)]">
                  일괄 권리분석 결과 ({batchResults.filter((b) => b.result?.ai).length}/{batchResults.length})
                </p>
                {batchResults.map((b, i) => {
                  const grade = b.result?.ai?.safety_grade;
                  return (
                    <div key={i} className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="min-w-[150px] flex-1 truncate font-semibold text-[var(--text-primary)]" title={b.jibun}>{b.jibun}</span>
                      {grade ? (
                        <span className={`rounded-full border px-2 py-0.5 font-bold ${GRADE[grade] || "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>안전성 {grade}</span>
                      ) : (
                        <span className="text-[var(--text-hint)]">{b.result?.status === "ok" ? "분석" : b.result?.message ? "미확보" : "실패"}</span>
                      )}
                      {b.result?.ai?.summary && <span className="hidden max-w-[40%] truncate text-[var(--text-secondary)] sm:inline">{b.result.ai.summary}</span>}
                      {b.result && (
                        <button onClick={() => setResult(b.result)}
                          className="rounded-lg bg-[var(--surface-strong)] px-2 py-0.5 font-bold text-[var(--accent-strong)]">상세</button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input value={newJibun} onChange={(e) => setNewJibun(e.target.value)} placeholder="지번 주소 추가(예: …동 56-20)"
                onKeyDown={(e) => { if (e.key === "Enter" && newJibun.trim()) { addRow(projectId, { jibun: newJibun.trim() }); setNewJibun(""); } }}
                className="min-w-[200px] flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
              <button onClick={() => { if (newJibun.trim()) { addRow(projectId, { jibun: newJibun.trim() }); setNewJibun(""); } }}
                className="rounded-lg border border-dashed border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">＋ 지번 추가</button>
            </div>
          </CardContent>
        </Card>
      )}

      {result && (
        <>
          {/* 발급 등기부 PDF (서버 저장, 만료 후 자동삭제) */}
          {result.fetched?.pdf_url && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 shadow-[var(--shadow-md)]">
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
                <p className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]"><FileText className="size-4 shrink-0" aria-hidden />발급된 등기부등본 원본(PDF) — 서버 저장(30일 후 자동삭제)</p>
                <div className="flex gap-2">
                  <a href={result.fetched.pdf_url} target="_blank" rel="noopener noreferrer"
                    className="rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]">PDF 보기 ↗</a>
                  <a href={result.fetched.pdf_url} download
                    className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90">다운로드 ↓</a>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 토지 소유구분·특성(공부) — 항상 제공 */}
          {land && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="text-sm font-black text-[var(--accent-strong)]">🟫 토지 소유·특성 정보 (공부 + 등기)</p>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {[
                    ["소유형태", land.ownership_form || "-"],
                    ["소유자수", land.owner_count != null ? `${land.owner_count}인` : "-"],
                    ["소유구분(공부)", land.owner_type || "-"],
                    ["지목", land.land_category || "-"],
                    ["용도지역", land.zone_type || "-"],
                    ["면적", land.land_area_sqm != null ? `${Math.round(land.land_area_sqm).toLocaleString()}㎡` : "-"],
                    ["공시지가(㎡)", land.official_price_per_sqm ? `${Math.round(land.official_price_per_sqm).toLocaleString()}원` : "-"],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="cc-num mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                    </div>
                  ))}
                </div>
                {/* 소유자별 지분(공동소유 등) */}
                {land.owners && land.owners?.length > 0 && (
                  <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                    <p className="text-[11px] font-bold text-[var(--text-secondary)]">소유자별 지분 ({land.ownership_form || "-"})</p>
                    <div className="mt-1.5 space-y-1">
                      {(land.owners ?? []).map((o, i) => (
                        <div key={i} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span className="font-semibold text-[var(--text-primary)]">{o.name || "-"}</span>
                          <span className="text-[var(--text-secondary)]">
                            {o.share || "-"}{o.acquisition_date ? ` · 취득 ${o.acquisition_date}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <p className="mt-2 text-[11px] text-[var(--text-hint)]">※ 소유형태·소유자·지분은 등기부 분석 기반, 지목·용도지역·공시지가는 공부(토지대장/이용계획) 기반입니다.</p>
              </CardContent>
            </Card>
          )}

          {/* 등기부 미확보 안내 */}
          {result.status !== "ok" && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--status-warning)]"><Settings className="size-4" aria-hidden />등기부 분석 안내</p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">{result.message}</p>
                <p className="mt-2 text-[11px] text-[var(--text-hint)]">위의 ‘등기부등본 내용 직접 입력’으로 분석하거나, 등기부 API(CODEF) 설정을 완료하세요.</p>
              </CardContent>
            </Card>
          )}

          {/* 등기 권리분석(법무사·변호사 AI) */}
          {ai && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]"><Scale className="size-4" aria-hidden />등기 권리분석 (법무사·변호사 AI)</p>
                  {ai.safety_grade && (
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${GRADE[ai.safety_grade] || "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>
                      안전성 {ai.safety_grade}
                    </span>
                  )}
                </div>
                {ai.summary && <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{ai.summary}</p>}

                {/* 소유정보 */}
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {[
                    ["소유자", own.current_owner],
                    ["보유지분", own.share],
                    ["취득일", own.acquisition_date],
                    ["취득원인", own.acquisition_cause],
                    ["매입금액", own.acquisition_price],
                    ["보유기간", own.ownership_period],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v || "기재 없음"}</p>
                    </div>
                  ))}
                </div>

                {/* 권리 상태 */}
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <RightBlock title="가등기" tone={ai.provisional_registration?.exists ? "rose" : "emerald"}
                    body={ai.provisional_registration?.exists ? (ai.provisional_registration?.detail || "있음") : "없음"} />
                  <RightBlock title="매도청구 가능여부" tone="sky"
                    body={`${ai.right_to_demand_sale?.possible || "-"}${ai.right_to_demand_sale?.reason ? ` — ${ai.right_to_demand_sale.reason}` : ""}`} />
                  <RightBlock title="압류·가압류·경매" tone={(ai.seizure?.length ?? 0) > 0 ? "rose" : "emerald"}
                    body={(ai.seizure?.length ?? 0) > 0 ? ai.seizure!.map((s) => `${s.type || ""} ${s.holder || ""} ${s.detail || ""}`).join(" / ") : "없음"} />
                  <RightBlock title="근저당 등 (을구)" tone={(ai.mortgage?.length ?? 0) > 0 ? "amber" : "emerald"}
                    body={(ai.mortgage?.length ?? 0) > 0 ? ai.mortgage!.map((m) => `채권최고액 ${m.max_claim || "-"} (${m.mortgagee || "-"})`).join(" / ") : "없음"} />
                </div>

                {/* 법무사 핵심판단: 말소기준권리·인수/소멸 */}
                {(ai.baseline_right || ai.acquired_extinguished) && (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {ai.baseline_right && (
                      <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]/40 p-3">
                        <p className="text-xs font-bold text-[var(--accent-strong)]">말소기준권리</p>
                        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{ai.baseline_right}</p>
                      </div>
                    )}
                    {ai.acquired_extinguished && (
                      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                        <p className="text-xs font-bold text-[var(--text-primary)]">인수 / 소멸 권리</p>
                        <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{ai.acquired_extinguished}</p>
                      </div>
                    )}
                  </div>
                )}
                {ai.rights_analysis && (
                  <div className="mt-4">
                    <p className="text-xs font-bold text-[var(--text-primary)]">권리관계 종합 분석</p>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{ai.rights_analysis}</p>
                  </div>
                )}
                {(ai.risks?.length ?? 0) > 0 && (
                  <div className="mt-3">
                    <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--status-error)]"><AlertTriangle className="size-3.5" aria-hidden />권리 리스크</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                      {ai.risks!.map((r, i) => <li key={i}>· {r}</li>)}
                    </ul>
                  </div>
                )}
                <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 본 분석은 참고용이며 법률자문이 아닙니다. 정확한 권리관계는 등기부등본 원본·전문가 확인이 필요합니다.</p>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* 하단 서브메뉴: 토지조서 연동 */}
      <Card className="rounded-[var(--radius-2xl)] border-[var(--line)] shadow-[var(--shadow-sm)]">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]"><ClipboardList className="size-4 shrink-0" aria-hidden />여러 필지의 소유·지분·매입가·계약/동의를 한눈에 관리하려면 토지조서로 이동하세요.</p>
          <Link href={`/${locale}/land-schedule`} className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90">
            토지조서 바로가기 →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function RightBlock({ title, body, tone }: { title: string; body: string; tone: string }) {
  const cls: Record<string, string> = {
    rose: "border-[var(--status-error)]/30 text-[var(--status-error)]", amber: "border-[var(--status-warning)]/30 text-[var(--status-warning)]",
    emerald: "border-[var(--status-success)]/30 text-[var(--status-success)]", sky: "border-[var(--status-info)]/30 text-[var(--status-info)]",
  };
  return (
    <div className={`rounded-xl border bg-[var(--surface-soft)] p-3 ${cls[tone] || "border-[var(--line)]"}`}>
      <p className="text-xs font-bold">{title}</p>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{body}</p>
    </div>
  );
}
