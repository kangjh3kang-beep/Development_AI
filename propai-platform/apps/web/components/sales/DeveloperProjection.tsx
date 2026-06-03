"use client";

import { useEffect, useState } from "react";
import { salesGlobal, won } from "@/lib/salesApi";

interface SiteSummary {
  site_id: string; site_name: string; status: string;
  visitors: number; contracts_cnt: number; contract_amt: number;
  sold_ratio: number; commission_paid: number; commission_due: number;
}

export default function DeveloperProjection() {
  const [sites, setSites] = useState<SiteSummary[]>([]);
  useEffect(() => {
    salesGlobal.get<SiteSummary[]>("/projection/summary").then(setSites).catch(() => setSites([]));
  }, []);
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {sites.length === 0 && <p className="text-sm text-[var(--text-secondary)]">집계된 현장이 없습니다.</p>}
      {sites.map((s) => (
        <div key={s.site_id} className="space-y-1 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-sm)]">
          <h3 className="font-bold text-[var(--text-primary)]">{s.site_name}</h3>
          <Row k="방문(누적)" v={`${s.visitors ?? 0}명`} />
          <Row k="계약" v={`${s.contracts_cnt ?? 0}건 / ${won(s.contract_amt)}`} />
          <Row k="분양률" v={`${((s.sold_ratio ?? 0) * 100).toFixed(1)}%`} />
          <Row k="수수료(지급)" v={won(s.commission_paid)} />
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">* 개인정보(고객/방문객 명단) 미표시</p>
        </div>
      ))}
    </div>
  );
}
const Row = ({ k, v }: { k: string; v: string }) => (
  <div className="flex justify-between text-sm">
    <span className="text-[var(--text-tertiary)]">{k}</span>
    <span className="font-semibold text-[var(--text-primary)]">{v}</span>
  </div>
);
