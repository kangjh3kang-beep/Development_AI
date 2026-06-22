"use client";

import { AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";

interface PriceRow {
  unit_id: string; dong: string; ho: string; total_price: number;
  price_mode: "WEIGHTED" | "FIXED"; override_price?: number | null;
}

export default function PriceTableEditor({ siteCode, roundId }: { siteCode: string; roundId: string }) {
  const api = salesApi(siteCode);
  const [rows, setRows] = useState<PriceRow[]>([]);
  const [busy, setBusy] = useState(false);
  // ★[iter-4 MED·warning 종단배선] /pricing/generate 응답의 원가구성 경고(흡수금지·왜곡·음수clamp)를
  //   배너로 노출(과거엔 폐기 — '가중치 일괄 재생성' 경로의 dead 채널 해소). PriceGroupingPanel 과 동일.
  const [warnings, setWarnings] = useState<{ message: string; unit_count?: number }[]>([]);

  const load = useCallback(() => {
    api.get<PriceRow[]>(`/pricing/table?round_id=${roundId}`).then(setRows).catch(() => setRows([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roundId, siteCode]);
  useEffect(() => { load(); }, [load]);

  const regenerate = async () => {
    setBusy(true); setWarnings([]);
    try {
      const r = await api.post<{ priced?: number; warnings?: { message: string; unit_count?: number }[] }>(
        "/pricing/generate", { round_id: roundId });
      setWarnings(r?.warnings || []);
      load();
    } finally { setBusy(false); }
  };
  const toggleMode = async (r: PriceRow, mode: "WEIGHTED" | "FIXED", override?: number) => {
    await api.patch(`/units/${r.unit_id}/price`,
      mode === "FIXED"
        ? { round_id: roundId, mode, override_price: override, reason: "확정가 직접입력" }
        : { round_id: roundId, mode });
    load();
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-black text-[var(--text-primary)]">분양가표 (차수)</h2>
        <button onClick={regenerate} disabled={busy}
          className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "생성 중…" : "가중치 일괄 재생성"}
        </button>
      </div>
      {/* ★[iter-4 warning 배너] 재생성 시 원가구성 경고(흡수금지·왜곡·음수clamp) 정직 노출 —
          Σ구성≠분양가·VAT 과세표준 과소합산 신호. PriceGroupingPanel 과 동일 디자인. */}
      {warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-2.5 py-1.5">
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
      <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--line)] bg-[var(--surface-strong)] text-left text-[var(--text-secondary)]">
              <th className="px-3 py-2">동/호</th><th className="px-3 py-2">모드</th>
              <th className="px-3 py-2 text-right">분양가</th><th className="px-3 py-2">확정금액 입력</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.unit_id} className="border-b border-[var(--line)]">
                <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">{r.dong}-{r.ho}</td>
                <td className="px-3 py-2">
                  <select value={r.price_mode}
                    onChange={(e) => toggleMode(r, e.target.value as "WEIGHTED" | "FIXED", r.override_price ?? undefined)}
                    className="rounded border border-[var(--line)] bg-[var(--surface-strong)] px-1.5 py-0.5 text-xs text-[var(--text-primary)]">
                    <option value="WEIGHTED">가중치</option>
                    <option value="FIXED">확정금액</option>
                  </select>
                </td>
                <td className="px-3 py-2 text-right font-semibold text-[var(--text-primary)]">{won(r.total_price)}</td>
                <td className="px-3 py-2">
                  {r.price_mode === "FIXED" ? (
                    <input type="number" defaultValue={r.override_price ?? undefined}
                      onBlur={(e) => toggleMode(r, "FIXED", Number(e.target.value))}
                      className="w-32 rounded border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-0.5 text-right text-[var(--text-primary)]"
                      placeholder="원" />
                  ) : <span className="text-xs text-[var(--text-tertiary)]">가중치 자동</span>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-sm text-[var(--text-secondary)]">
                분양가가 없습니다. 기준가/구성 입력 후 ‘가중치 일괄 재생성’을 실행하세요.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--text-tertiary)]">가중치(층/라인/향/그룹) 또는 확정금액을 행별로 병행 적용. 확정금액이 가중치에 우선.</p>
    </div>
  );
}
