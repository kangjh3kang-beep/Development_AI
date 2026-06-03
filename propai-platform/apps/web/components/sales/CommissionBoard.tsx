"use client";

import { useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";

interface Master { basis: string; fixed_amount?: number; rate?: number; locked?: boolean }
interface Dist { id: string; target_node_type?: string; target_node_id?: string; basis: string; value: number }

export default function CommissionBoard({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [master, setMaster] = useState<Master | null>(null);
  const [dist, setDist] = useState<Dist[]>([]);
  const [valid, setValid] = useState<{ total: number; allocated: number; valid: boolean } | null>(null);

  useEffect(() => {
    api.get<Master[]>("/commission-master").then((m) => setMaster(m?.[0] ?? null)).catch(() => setMaster(null));
    api.get<Dist[]>("/commission-distribution").then(setDist).catch(() => setDist([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);

  const check = async () => {
    const r = await api.post<{ total: number; allocated: number; valid: boolean }>(
      "/commission/distribution/validate", { sample_price: 500000000 });
    setValid(r);
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-2 font-bold text-[var(--text-primary)]">1단: 시행사 총액</h3>
        {master ? (
          <div className="space-y-1 text-sm text-[var(--text-secondary)]">
            <div>기준: <span className="text-[var(--text-primary)]">{master.basis}</span></div>
            <div>건당 고정: {master.fixed_amount ? won(master.fixed_amount) : "-"}</div>
            <div>요율: {master.rate ?? "-"}</div>
            <div>잠금: {master.locked ? "예(확정)" : "아니오"}</div>
          </div>
        ) : <p className="text-sm text-[var(--text-tertiary)]">미설정</p>}
      </div>
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-bold text-[var(--text-primary)]">2단: 대행사 배분</h3>
          <button onClick={check} className="rounded bg-[var(--accent-strong)] px-2 py-1 text-xs font-bold text-white">합계 검증</button>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[var(--line)] text-left text-[var(--text-secondary)]">
            <th className="py-1">대상</th><th>기준</th><th className="text-right">값</th></tr></thead>
          <tbody>
            {dist.map((d) => (
              <tr key={d.id} className="border-b border-[var(--line)] text-[var(--text-primary)]">
                <td className="py-1">{d.target_node_type ?? d.target_node_id}</td>
                <td>{d.basis}</td>
                <td className="text-right">{d.basis === "FIXED" ? won(d.value) : `${d.value}`}</td>
              </tr>
            ))}
            {dist.length === 0 && <tr><td colSpan={3} className="py-3 text-[var(--text-tertiary)]">배분 규칙 없음</td></tr>}
          </tbody>
        </table>
        {valid && (
          <p className={`mt-2 text-sm font-semibold ${valid.valid ? "text-emerald-400" : "text-rose-400"}`}>
            총액 {won(valid.total)} / 배분합계 {won(valid.allocated)} → {valid.valid ? "정상(≤총액)" : "초과(오류)"}
          </p>
        )}
      </div>
    </div>
  );
}
