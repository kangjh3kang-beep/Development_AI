"use client";

import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { salesApi } from "@/lib/salesApi";

export default function VisitorStats({ siteCode }: { siteCode: string }) {
  const [data, setData] = useState<{ hour: string; visitors: number }[]>([]);
  useEffect(() => {
    salesApi(siteCode).get<{ hour: string; visitors: number }[]>("/mh/stats?hours=24")
      .then((d) => setData((d || []).map((x) => ({ hour: new Date(x.hour).getHours() + "시", visitors: x.visitors }))))
      .catch(() => setData([]));
  }, [siteCode]);
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <h3 className="mb-3 font-bold text-[var(--text-primary)]">시간대별 방문자 (24h)</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data}>
          <XAxis dataKey="hour" stroke="var(--text-tertiary)" fontSize={12} />
          <YAxis allowDecimals={false} stroke="var(--text-tertiary)" fontSize={12} />
          <Tooltip contentStyle={{ background: "var(--surface-strong)", border: "1px solid var(--line)", color: "var(--text-primary)" }} />
          <Bar dataKey="visitors" fill="#6366f1" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
