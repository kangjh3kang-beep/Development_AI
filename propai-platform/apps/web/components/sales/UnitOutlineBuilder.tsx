"use client";

/**
 * 동·호표 건축개요 빌더 — 건축개요(대지면적/용적률/건폐율) 자동 로드 +
 * 동/라인/층 추가·삭제 + 상가(층별 평/호수 가변) 생성.
 * → POST /sales/units/generate { source_type:"OUTLINE", params:{ blocks:[...] } }
 */

import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Construction, DraftingCompass } from "lucide-react";
import { salesApi } from "@/lib/salesApi";
import { ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";

// 일시적 인프라 오류(배포 전환·게이트웨이)는 짧게 재시도해 사용자에게 노출하지 않는다.
const _TRANSIENT = new Set([0, 502, 503, 504]);
async function _withRetry<T>(fn: () => Promise<T>, max = 2): Promise<T> {
  for (let n = 0; ; n++) {
    try {
      return await fn();
    } catch (e) {
      const st = e instanceof ApiClientError ? e.status : 0;
      if (_TRANSIENT.has(st) && n < max) {
        await new Promise((r) => setTimeout(r, 700 * (n + 1)));
        continue;
      }
      throw e;
    }
  }
}
function _errMsg(e: unknown, fallback: string): string {
  const st = e instanceof ApiClientError ? e.status : 0;
  if (st === 401 || st === 403) return "권한이 없습니다(시행사·대행사만 생성 가능). 현장 재진입 후 다시 시도하세요.";
  if (st === 422 || st === 400) return "입력값을 확인하세요(동/층/호수).";
  if (_TRANSIENT.has(st)) return "일시적 연결 오류입니다. 잠시 후 다시 시도해 주세요.";
  return `${fallback}${st ? ` (오류 ${st})` : ""}.`;
}

type FloorSpec = { floor: number; units: number; type_name: string };
type Block = {
  name: string;
  mode: "uniform" | "retail";
  floors: number;
  units_per_floor: number;
  aspect: string;
  type_name: string;
  floors_spec: FloorSpec[];
};

const newBlock = (n: number): Block => ({
  name: String(101 + n),
  mode: "uniform",
  floors: 15,
  units_per_floor: 4,
  aspect: "남향",
  type_name: "84A",
  floors_spec: [{ floor: 1, units: 6, type_name: "상가-A" }],
});

const fieldCls =
  "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export function UnitOutlineBuilder({
  siteCode,
  open,
  onClose,
  onDone,
}: {
  siteCode: string;
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const sa = useProjectContextStore((s) => s.siteAnalysis);
  const [blocks, setBlocks] = useState<Block[]>([newBlock(0)]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const total = useMemo(
    () =>
      blocks.reduce(
        (a, b) =>
          a +
          (b.mode === "uniform"
            ? (b.floors || 0) * (b.units_per_floor || 0)
            : (b.floors_spec ?? []).reduce((s, f) => s + (f.units || 0), 0)),
        0,
      ),
    [blocks],
  );

  if (!open || typeof document === "undefined") return null;

  const patch = (i: number, p: Partial<Block>) =>
    setBlocks((arr) => arr.map((b, idx) => (idx === i ? { ...b, ...p } : b)));
  const patchFloor = (bi: number, fi: number, p: Partial<FloorSpec>) =>
    setBlocks((arr) =>
      arr.map((b, idx) =>
        idx === bi ? { ...b, floors_spec: (b.floors_spec ?? []).map((f, j) => (j === fi ? { ...f, ...p } : f)) } : b,
      ),
    );

  // 🏗 설계(BIM)에서 자동 생성 — 프로젝트 최신 설계의 층수·평형배분으로 동·호표 생성
  const submitFromDesign = async () => {
    setBusy(true); setErr("");
    try {
      const r = await _withRetry(() =>
        salesApi(siteCode).post<{ generated: number }>("/units/generate", { source_type: "DESIGN_AI" }),
      );
      if ((r?.generated ?? 0) > 0) onDone();
      else setErr("설계 데이터가 없습니다. 먼저 프로젝트에서 건축설계(BIM)를 생성하세요.");
    } catch (e) {
      setErr(_errMsg(e, "설계 자동 생성 실패(설계 데이터 확인)"));
    } finally { setBusy(false); }
  };

  const submit = async () => {
    if (total <= 0) { setErr("생성할 세대가 없습니다. 동·층·호수를 입력하세요."); return; }
    setBusy(true); setErr("");
    try {
      const payloadBlocks = blocks.map((b) =>
        b.mode === "retail"
          ? {
              name: b.name,
              aspect: b.aspect || undefined,
              floors_spec: b.floors_spec
                .filter((f) => f.units > 0)
                .map((f) => ({ floor: f.floor, units: f.units, type_name: f.type_name || undefined })),
            }
          : {
              name: b.name,
              floors: b.floors,
              units_per_floor: b.units_per_floor,
              aspect: b.aspect || undefined,
              types: b.type_name ? [{ name: b.type_name }] : undefined,
            },
      );
      await _withRetry(() =>
        salesApi(siteCode).post("/units/generate", {
          source_type: "OUTLINE",
          params: { blocks: payloadBlocks },
        }),
      );
      onDone();
    } catch (e) {
      setErr(_errMsg(e, "동·호표 생성에 실패했습니다"));
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow-lg)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-3">
          <h2 className="text-base font-black text-[var(--text-primary)]">동·호표 생성 (건축개요)</h2>
          <button onClick={onClose} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">✕</button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {/* 건축개요(프로젝트 부지분석에서 자동 로드) */}
          <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
            <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--accent-strong)]"><DraftingCompass className="size-3.5" aria-hidden />건축개요 (프로젝트 부지분석 연동)</p>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ["대지면적", (() => { const a = effectiveLandAreaSqm(sa); return a ? `${a.toLocaleString()}㎡` : "-"; })()],
                ["용도지역", sa?.zoneCode || "-"],
                ["건폐율", sa?.ordinance?.effectiveBcr ? `${sa.ordinance.effectiveBcr}%` : "-"],
                ["용적률", sa?.ordinance?.effectiveFar ? `${sa.ordinance.effectiveFar}%` : "-"],
              ].map(([k, v]) => (
                <div key={k}>
                  <p className="text-[10px] text-[var(--text-tertiary)]">{k}</p>
                  <p className="text-sm font-bold text-[var(--text-primary)]">{v}</p>
                </div>
              ))}
            </div>
            {!sa?.landAreaSqm && (
              <p className="mt-1 text-[11px] text-[var(--text-hint)]">※ 건축개요가 없으면 동·층만으로 생성됩니다. 프로젝트 부지분석 완료 시 자동 반영됩니다.</p>
            )}
          </div>

          {/* 동 빌더 */}
          {blocks.map((b, i) => (
            <div key={i} className="rounded-xl border border-[var(--line)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <input className={`${fieldCls} w-24`} value={b.name} onChange={(e) => patch(i, { name: e.target.value })} placeholder="동(예:101)" />
                <div className="flex overflow-hidden rounded-lg border border-[var(--line)]">
                  {(["uniform", "retail"] as const).map((m) => (
                    <button key={m} onClick={() => patch(i, { mode: m })}
                      className={`px-3 py-1.5 text-xs font-bold ${b.mode === m ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)]"}`}>
                      {m === "uniform" ? "공동주택/오피스텔" : "상가(층별 가변)"}
                    </button>
                  ))}
                </div>
                {blocks.length > 1 && (
                  <button onClick={() => setBlocks((arr) => arr.filter((_, idx) => idx !== i))} className="ml-auto h-8 w-8 rounded-lg border border-rose-500/30 text-rose-500 hover:bg-rose-500/10">✕</button>
                )}
              </div>

              {b.mode === "uniform" ? (
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">층수</span>
                    <input type="number" className={fieldCls} value={b.floors} onChange={(e) => patch(i, { floors: Number(e.target.value) })} /></label>
                  <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">층당 호수(라인)</span>
                    <input type="number" className={fieldCls} value={b.units_per_floor} onChange={(e) => patch(i, { units_per_floor: Number(e.target.value) })} /></label>
                  <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">향</span>
                    <input className={fieldCls} value={b.aspect} onChange={(e) => patch(i, { aspect: e.target.value })} placeholder="남향" /></label>
                  <label className="flex flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">평형(타입)</span>
                    <input className={fieldCls} value={b.type_name} onChange={(e) => patch(i, { type_name: e.target.value })} placeholder="84A" /></label>
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  <div className="flex gap-2 px-1 text-[10px] font-bold text-[var(--text-tertiary)]">
                    <span className="w-20">층</span><span className="w-24">호수</span><span className="flex-1">평형/명칭</span><span className="w-8" />
                  </div>
                  {(b.floors_spec ?? []).map((f, fi) => (
                    <div key={fi} className="flex items-center gap-2">
                      <input type="number" className={`${fieldCls} w-20`} value={f.floor} onChange={(e) => patchFloor(i, fi, { floor: Number(e.target.value) })} />
                      <input type="number" className={`${fieldCls} w-24`} value={f.units} onChange={(e) => patchFloor(i, fi, { units: Number(e.target.value) })} />
                      <input className={`${fieldCls} flex-1`} value={f.type_name} onChange={(e) => patchFloor(i, fi, { type_name: e.target.value })} placeholder="예: 1F-30평" />
                      <button onClick={() => patch(i, { floors_spec: (b.floors_spec ?? []).filter((_, j) => j !== fi) })} className="h-8 w-8 rounded-lg border border-rose-500/30 text-rose-500 hover:bg-rose-500/10">✕</button>
                    </div>
                  ))}
                  <button onClick={() => patch(i, { floors_spec: [...b.floors_spec, { floor: (b.floors_spec.at(-1)?.floor ?? 0) + 1, units: 6, type_name: "" }] })}
                    className="rounded-lg border border-dashed border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">＋ 층 추가</button>
                </div>
              )}
            </div>
          ))}
          <button onClick={() => setBlocks((arr) => [...arr, newBlock(arr.length)])}
            className="rounded-xl border border-dashed border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--accent-strong)] hover:border-[var(--accent-strong)]">＋ 동 추가</button>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[var(--line)] px-5 py-3">
          <div className="text-sm">
            <span className="text-[var(--text-secondary)]">생성 예정: </span>
            <b className="text-[var(--accent-strong)]">{total.toLocaleString()}세대/호실</b>
            {err && <span className="ml-3 text-xs font-semibold text-rose-500">{err}</span>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={onClose} className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-sm font-bold text-[var(--text-secondary)]">취소</button>
            <button onClick={submitFromDesign} disabled={busy} title="프로젝트 최신 건축설계(BIM)의 층수·평형배분으로 자동 생성"
              className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-sm font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">
              <Construction className="size-4" aria-hidden /> 설계(BIM)에서 자동
            </button>
            <button onClick={submit} disabled={busy} className="rounded-xl bg-[var(--accent-strong)] px-5 py-2 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {busy ? "생성 중…" : "동·호표 생성"}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
