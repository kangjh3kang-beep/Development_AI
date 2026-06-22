"use client";

/**
 * P1-4 분양가 그룹핑 — 세대 그리드에서 층/라인/향/평형 클릭·범위선택 → 그룹 일괄단가 적용.
 * 적용: +%(RATE)·+원(FIXED)·절대 평당단가(OVERRIDE_PSQM). POST /sales/pricing/group-apply.
 * 총매출(GET /sales/pricing/revenue)을 적용 전/후로 보여 즉시 영향 확인.
 */
import { AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { salesApi } from "@/lib/salesApi";

type Unit = { id: string; dong: string; ho: string; floor: number; line?: string; aspect?: string; type_name?: string };
const eok = (man?: number) => (man && man > 0 ? `${(man / 10000).toLocaleString(undefined, { maximumFractionDigits: 1 })}억` : "-");

// ★[iter-2 gap 거짓0 해소] round-trip 잔차(gap)를 eok()(만원→억, 소수1) 로 환산하면 1~499 만원
//   (수만~수백만원) 잔차가 전부 '−0억'으로 뭉개져 가짜 완벽수렴으로 보인다. gap 전용 적응형 포맷:
//   |gap|<1만원이면 '○원', 1만원~1억 미만이면 '○○만원', 1억 이상이면 '○.○억'. (gap 은 만원 단위)
const fmtGap = (gapMan: number): string => {
  const abs = Math.abs(gapMan);
  if (abs < 1) return `${Math.round(abs * 10000).toLocaleString()}원`;   // 1만원 미만 → 원 단위
  if (abs < 10000) return `${Math.round(abs).toLocaleString()}만원`;      // 1억 미만 → 만원 단위
  return `${(abs / 10000).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`;  // 1억 이상 → 억
};

export default function PriceGroupingPanel({ siteCode, roundId, onChanged }: { siteCode: string; roundId: string; onChanged?: () => void }) {
  const api = salesApi(siteCode);
  const [units, setUnits] = useState<Unit[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<"RATE" | "FIXED" | "OVERRIDE_PSQM">("RATE");
  const [value, setValue] = useState("");
  const [revenue, setRevenue] = useState<number | null>(null);
  const [breakdown, setBreakdown] = useState<{ label: string; amount_10k: number; vat_10k: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [target, setTarget] = useState("");      // 목표 총매출(억)
  const [solveBusy, setSolveBusy] = useState(false);
  // ★[iter-3 warning 종단배선] 백엔드 decompose 가 만든 원가구성 경고(흡수금지·왜곡·음수clamp)를
  //   배열로 받아 배너로 노출한다(과거엔 폐기돼 화면서 안 보였음 — dead 채널 해소).
  const [warnings, setWarnings] = useState<{ message: string; unit_count?: number }[]>([]);

  const loadRevenue = useCallback(() => {
    api.get<{ total_revenue_10k: number; breakdown?: { label: string; amount_10k: number; vat_10k: number }[] }>(`/pricing/revenue?round_id=${roundId}`)
      .then((r) => { setRevenue(r?.total_revenue_10k ?? 0); setBreakdown(r?.breakdown || []); })
      .catch(() => setRevenue(null));
  }, [siteCode, roundId]);

  useEffect(() => {
    api.get<Unit[]>("/units?limit=2000").then((r) => setUnits(r || [])).catch(() => setUnits([]));
    loadRevenue();
  }, [siteCode, roundId, loadRevenue]);

  // 동 → 층(내림차순) → 세대
  const byDong = useMemo(() => {
    const g: Record<string, Record<number, Unit[]>> = {};
    for (const u of units) ((g[u.dong] ??= {})[u.floor] ??= []).push(u);
    return g;
  }, [units]);
  const lines = useMemo(() => Array.from(new Set(units.map((u) => u.line).filter(Boolean))) as string[], [units]);
  const aspects = useMemo(() => Array.from(new Set(units.map((u) => u.aspect).filter(Boolean))) as string[], [units]);

  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectBy = (pred: (u: Unit) => boolean, add = true) =>
    setSel((s) => { const n = new Set(s); for (const u of units) if (pred(u)) (add ? n.add(u.id) : n.delete(u.id)); return n; });

  const apply = async () => {
    const v = Number(value);
    if (sel.size === 0) { setMsg("세대를 선택하세요."); return; }
    if (!v) { setMsg("값을 입력하세요."); return; }
    setBusy(true); setMsg(""); setWarnings([]);
    try {
      // RATE 는 %를 비율로(예: 10 → 0.10). FIXED/OVERRIDE_PSQM 은 원 단위 그대로.
      const payloadVal = mode === "RATE" ? v / 100 : v;
      const r = await api.post<{ ok: boolean; total_revenue_10k?: number; applied_units?: number; group_reused?: boolean; warnings?: { message: string; unit_count?: number }[]; note?: string }>(
        "/pricing/group-apply", { round_id: roundId, unit_ids: Array.from(sel), mode, value: payloadVal });
      if (r?.ok) {
        // group_reused=true 면 더블클릭·재시도가 새 그룹을 만들지 않고 기존 그룹을 재사용했다는 멱등 표시.
        setMsg(`${r.applied_units}세대 적용 — 총매출 ${eok(r.total_revenue_10k)}${r.group_reused ? " (기존 그룹 갱신)" : ""}`);
        setRevenue(r.total_revenue_10k ?? revenue);
        setWarnings(r.warnings || []);
        setSel(new Set());
        onChanged?.();
      } else setMsg(r?.note || "적용 실패");
    } catch { setMsg("적용 실패(권한·라운드 확인)."); }
    finally { setBusy(false); }
  };

  const solveTarget = async () => {
    const eokVal = Number(target);
    if (!eokVal) { setMsg("목표 총매출(억)을 입력하세요."); return; }
    setSolveBusy(true); setMsg(""); setWarnings([]);
    try {
      const r = await api.post<{ ok: boolean; base_unit_price?: number; achieved_total_10k?: number; gap_10k?: number; gap_won?: number; warnings?: { message: string; unit_count?: number }[]; note?: string }>(
        "/pricing/solve-base", { round_id: roundId, target_total_10k: Math.round(eokVal * 10000) });
      if (r?.ok) {
        setWarnings(r.warnings || []);
        // round-trip 잔차(목표−실달성)를 정직 표기 — 세대별 반올림 누적으로 0 이 아닐 수 있음.
        // gap_won(원, floor 편향 없는 정확값)이 오면 만원으로 환산해 쓰고, 없으면 gap_10k 폴백.
        const gapMan = r.gap_won != null ? r.gap_won / 10000 : (r.gap_10k ?? 0);
        // 0 이 아니면 적응형 포맷으로 표기(거짓 −0억 금지). 부호: 양수=미달, 음수=초과.
        const gapTxt = Math.round(Math.abs(gapMan) * 10000) >= 1
          ? ` · 오차 ${gapMan > 0 ? "미달 −" : "초과 +"}${fmtGap(gapMan)}(반올림)` : " · 정확 수렴";
        setMsg(`역산 완료 — 기준단가 ${r.base_unit_price?.toLocaleString()}원/㎡, 달성 ${eok(r.achieved_total_10k)}${gapTxt}`);
        setRevenue(r.achieved_total_10k ?? revenue); onChanged?.();
      } else setMsg(r?.note || "역산 실패");
    } catch { setMsg("역산 실패(권한·면적 확인)."); }
    finally { setSolveBusy(false); }
  };

  if (units.length === 0)
    return <p className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-3 text-xs text-[var(--text-hint)]">세대가 없습니다. 먼저 동·호표를 생성하세요.</p>;

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold text-[var(--text-secondary)]">④ 그룹핑 일괄단가 <span className="font-normal text-[var(--text-hint)]">(층/라인/향 선택 → 적용)</span></p>
        <p className="text-[11px] text-[var(--text-tertiary)]">현재 총매출 <b className="text-[var(--accent-strong)]">{eok(revenue ?? undefined)}</b> · 선택 {sel.size}세대</p>
      </div>
      {breakdown.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-tertiary)]">
          <span className="text-[var(--text-hint)]">원가구성:</span>
          {breakdown.map((b) => (
            <span key={b.label} className="rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-1.5 py-0.5">
              {b.label} {eok(b.amount_10k)}{b.vat_10k > 0 ? ` (VAT ${eok(b.vat_10k)})` : ""}
            </span>
          ))}
        </div>
      )}

      {/* ★[iter-3 warning 배너] 원가구성 경고(흡수금지·왜곡·음수clamp) 정직 노출 — Σ구성≠분양가·
          VAT 과세표준 과소합산 신호. 운영자가 원가구성 비율(합=1)·정액 설정을 점검하도록 안내. */}
      {warnings.length > 0 && (
        <div className="mb-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-2.5 py-1.5">
          <p className="flex items-center gap-1.5 text-[11px] font-bold text-amber-600"><AlertTriangle className="size-3.5 shrink-0" aria-hidden />원가구성 경고 — 분양가 합과 구성요소 합이 어긋날 수 있습니다(원가구성 비율 합=1 점검)</p>
          <ul className="mt-1 space-y-0.5">
            {warnings.map((w, i) => (
              <li key={i} className="text-[10px] leading-snug text-amber-600/90">
                · {w.message}{w.unit_count != null ? ` (세대 ${w.unit_count})` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* P1-3 목표 총매출 → 기준단가 역산 */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5">
        <span className="text-[11px] font-bold text-[var(--text-secondary)]">목표 총매출 역산</span>
        <input type="number" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="목표(억)"
          className="w-24 rounded-md border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
        <button onClick={solveTarget} disabled={solveBusy}
          className="rounded-md border border-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">{solveBusy ? "역산 중…" : "기준단가 역산"}</button>
        <span className="text-[10px] text-[var(--text-hint)]">목표액을 균일 기준단가로 환산해 전 타입 반영(이후 그룹/가중치로 조정)</span>
      </div>

      {/* 빠른 선택 */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="text-[var(--text-hint)]">빠른선택:</span>
        {lines.map((ln) => <button key={`l${ln}`} onClick={() => selectBy((u) => u.line === ln)} className="rounded-md border border-[var(--line)] px-2 py-0.5 text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">{ln}라인</button>)}
        {aspects.map((a) => <button key={`a${a}`} onClick={() => selectBy((u) => u.aspect === a)} className="rounded-md border border-[var(--line)] px-2 py-0.5 text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">{a}</button>)}
        <button onClick={() => setSel(new Set())} className="rounded-md border border-rose-500/30 px-2 py-0.5 text-rose-500">선택해제</button>
      </div>

      {/* 그리드(동→층 내림차순, 셀=호 클릭, 층 라벨 클릭=층 전체) */}
      <div className="max-h-72 space-y-2 overflow-auto">
        {Object.entries(byDong).map(([dong, floors]) => (
          <div key={dong}>
            <p className="mb-1 text-[11px] font-bold text-[var(--text-secondary)]">{dong}동</p>
            {Object.keys(floors).map(Number).sort((a, b) => b - a).map((f) => (
              <div key={f} className="mb-0.5 flex items-center gap-1">
                <button onClick={() => selectBy((u) => u.dong === dong && u.floor === f)}
                  className="w-9 shrink-0 rounded bg-[var(--surface-strong)] px-1 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)] hover:text-[var(--accent-strong)]">{f}F</button>
                <div className="flex flex-wrap gap-1">
                  {floors[f].map((u) => (
                    <button key={u.id} onClick={() => toggle(u.id)} title={`${u.ho} ${u.type_name || ""} ${u.aspect || ""}`}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${sel.has(u.id) ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)]"}`}>{u.ho}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* 적용 바 */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-[var(--line)] pt-2">
        <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}
          className="rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-xs text-[var(--text-primary)]">
          <option value="RATE">＋% 가산</option><option value="FIXED">＋원 가산</option><option value="OVERRIDE_PSQM">평당단가(절대, 원/㎡)</option>
        </select>
        <input type="number" value={value} onChange={(e) => setValue(e.target.value)}
          placeholder={mode === "RATE" ? "예:10 (=+10%)" : mode === "FIXED" ? "예:5000000(원)" : "예:7740000(원/㎡)"}
          className="w-40 rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
        <button onClick={apply} disabled={busy || sel.size === 0}
          className="rounded-md bg-[var(--accent-strong)] px-3 py-1 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50">{busy ? "적용 중…" : `선택 ${sel.size}세대 적용`}</button>
        {msg && <span className="text-[11px] text-[var(--text-tertiary)]">{msg}</span>}
      </div>
    </div>
  );
}
