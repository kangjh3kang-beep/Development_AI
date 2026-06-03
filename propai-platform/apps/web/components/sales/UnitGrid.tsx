"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { salesApi } from "@/lib/salesApi";
import { useSalesStore, type Unit } from "@/store/useSalesStore";

const Grid3D = dynamic(() => import("@/components/sales/Grid3D"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[480px] items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] text-sm text-[var(--text-tertiary)]">
      3D 엔진 로딩 중…
    </div>
  ),
});

const COLOR: Record<string, string> = {
  AVAILABLE: "bg-emerald-500/15 border-emerald-500/40 text-emerald-300",
  HOLD: "bg-amber-500/15 border-amber-500/40 text-amber-300",
  APPLIED: "bg-sky-500/15 border-sky-500/40 text-sky-300",
  CONTRACTED: "bg-rose-500/15 border-rose-500/40 text-rose-300",
  CANCELLED: "bg-zinc-500/15 border-zinc-500/40 text-zinc-400 line-through",
};
const LABELS: Record<string, string> = {
  AVAILABLE: "분양가능", HOLD: "보류", APPLIED: "청약", CONTRACTED: "계약", CANCELLED: "취소",
};

export default function UnitGrid({ siteCode }: { siteCode: string }) {
  const units = useSalesStore((s) => s.units);
  const select = useSalesStore((s) => s.select);
  const setUnits = useSalesStore((s) => s.setUnits);
  const [view, setView] = useState<"2D" | "3D">("2D");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    salesApi(siteCode)
      .get<Unit[]>("/units?limit=2000")
      .then((u) => { if (alive) setUnits(u || []); })
      .catch(() => { if (alive) setUnits([]); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [siteCode, setUnits]);

  const byDong = useMemo(() => {
    const g: Record<string, Record<number, Unit[]>> = {};
    for (const u of units) {
      (g[u.dong] ??= {})[u.floor] ??= [];
      g[u.dong][u.floor].push(u);
    }
    return g;
  }, [units]);

  const stats = useMemo(() => {
    const c: Record<string, number> = { AVAILABLE: 0, HOLD: 0, APPLIED: 0, CONTRACTED: 0, CANCELLED: 0 };
    for (const u of units) c[u.status] = (c[u.status] ?? 0) + 1;
    const total = units.length;
    const active = total - (c.CANCELLED || 0);
    const soldRatio = active ? Math.round(((c.CONTRACTED || 0) / active) * 1000) / 10 : 0;
    return { c, total, soldRatio };
  }, [units]);

  return (
    <div className="space-y-4">
      {units.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
          {[
            ["총 세대", `${stats.total}`],
            ["분양률", `${stats.soldRatio}%`],
            ["분양가능", `${stats.c.AVAILABLE}`],
            ["보류", `${stats.c.HOLD}`],
            ["청약", `${stats.c.APPLIED}`],
            ["계약", `${stats.c.CONTRACTED}`],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-2.5 text-center">
              <p className="text-[10px] text-[var(--text-tertiary)]">{k}</p>
              <p className="text-base font-black text-[var(--text-primary)]">{v}</p>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {(["2D", "3D"] as const).map((v) => (
          <button key={v} onClick={() => setView(v)}
            className={`rounded-lg px-3 py-1.5 text-sm font-bold ${view === v ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)]"}`}>
            {v}
          </button>
        ))}
        <div className="ml-auto flex flex-wrap gap-3 text-xs">
          {Object.entries(LABELS).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1.5 text-[var(--text-secondary)]">
              <i className={`inline-block h-3 w-3 rounded ${COLOR[k].split(" ")[0]}`} />{v}
            </span>
          ))}
        </div>
      </div>

      {loading && <p className="text-sm text-[var(--text-tertiary)]">세대 정보를 불러오는 중…</p>}
      {!loading && units.length === 0 && (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-secondary)]">
          아직 세대가 없습니다. 상단 <b className="text-[var(--accent-strong)]">‘+ 동·호표 생성’</b> 버튼으로 동·호를 자동 생성하세요.
        </p>
      )}

      {!loading && units.length > 0 && (view === "2D" ? (
        <div className="space-y-6">
          {Object.entries(byDong).map(([dong, floors]) => (
            <div key={dong} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
              <h3 className="mb-2 font-bold text-[var(--text-primary)]">{dong}동</h3>
              <div className="space-y-1">
                {Object.entries(floors).sort((a, b) => Number(b[0]) - Number(a[0])).map(([f, us]) => (
                  <div key={f} className="flex items-center gap-1">
                    <span className="w-10 text-xs font-semibold text-[var(--text-tertiary)]">{f}F</span>
                    {us.sort((a, b) => (a.ho || "").localeCompare(b.ho || "")).map((u) => (
                      <button key={u.id} onClick={() => select(u)}
                        className={`flex h-12 w-16 flex-col items-center justify-center rounded border text-[11px] font-medium ${COLOR[u.status]}`}>
                        {u.ho}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Grid3D units={units} onSelect={select} />
      ))}
    </div>
  );
}
