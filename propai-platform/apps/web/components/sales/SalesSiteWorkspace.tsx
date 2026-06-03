"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { salesApi, salesGlobal } from "@/lib/salesApi";
import type { Locale } from "@/i18n/config";
import UnitGrid from "@/components/sales/UnitGrid";
import Unit360Panel from "@/components/sales/Unit360Panel";
import PriceTableEditor from "@/components/sales/PriceTableEditor";
import OrgTree from "@/components/sales/OrgTree";
import CommissionBoard from "@/components/sales/CommissionBoard";
import DeskCheckin from "@/components/desk/DeskCheckin";
import VisitorStats from "@/components/desk/VisitorStats";
import SubscriptionPanel from "@/components/sales/SubscriptionPanel";
import PaymentsPanel from "@/components/sales/PaymentsPanel";
import LoanPanel from "@/components/sales/LoanPanel";
import ResalePanel from "@/components/sales/ResalePanel";
import TaxPanel from "@/components/sales/TaxPanel";
import { UnitOutlineBuilder } from "@/components/sales/UnitOutlineBuilder";

type Tab = "units" | "pricing" | "subscription" | "payments" | "loan" | "resale" | "tax" | "org" | "commission" | "desk";
const TABS: { key: Tab; label: string }[] = [
  { key: "units", label: "세대 배치도" },
  { key: "pricing", label: "분양가" },
  { key: "subscription", label: "청약·당첨" },
  { key: "payments", label: "수납·납부" },
  { key: "loan", label: "중도금 대출" },
  { key: "resale", label: "전매·실거래신고" },
  { key: "tax", label: "세금·보증" },
  { key: "org", label: "조직도" },
  { key: "commission", label: "수수료" },
  { key: "desk", label: "방문 안내데스크" },
];

export default function SalesSiteWorkspace({ siteCode, locale }: { siteCode: string; locale: Locale }) {
  const [tab, setTab] = useState<Tab>("units");
  const [rounds, setRounds] = useState<{ id: string; name: string }[]>([]);
  const [rid, setRid] = useState("");
  const [siteName, setSiteName] = useState("");
  const [builderOpen, setBuilderOpen] = useState(false);

  useEffect(() => {
    salesApi(siteCode).get<{ id: string; name: string }[]>("/rounds")
      .then((r) => { setRounds(r || []); if (r?.[0]) setRid(r[0].id); })
      .catch(() => setRounds([]));
    salesGlobal.get<{ site_code: string; site_name: string }[]>("/sites")
      .then((ss) => setSiteName((ss || []).find((x) => x.site_code === siteCode)?.site_name || ""))
      .catch(() => {});
  }, [siteCode]);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Link href={`/${locale}/sales`} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">← 현장 목록</Link>
        <h1 className="text-lg font-black text-[var(--text-primary)]">{siteName || "분양 현장"}</h1>
        {tab === "units" && (
          <button onClick={() => setBuilderOpen(true)}
            className="ml-auto rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-white">
            + 동·호표 생성
          </button>
        )}
      </div>

      <UnitOutlineBuilder
        siteCode={siteCode}
        open={builderOpen}
        onClose={() => setBuilderOpen(false)}
        onDone={() => { setBuilderOpen(false); window.location.reload(); }}
      />

      <div className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-3">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`rounded-lg px-3.5 py-1.5 text-sm font-bold transition ${
              tab === t.key
                ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-sm)]"
                : "border border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--text-primary)]"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "units" && (<><UnitGrid siteCode={siteCode} /><Unit360Panel siteCode={siteCode} /></>)}
      {tab === "pricing" && (
        <div className="space-y-3">
          {rounds.length > 1 && (
            <select value={rid} onChange={(e) => setRid(e.target.value)}
              className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-sm text-[var(--text-primary)]">
              {rounds.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
          {rid ? <PriceTableEditor siteCode={siteCode} roundId={rid} /> : <p className="text-sm text-[var(--text-secondary)]">차수가 없습니다.</p>}
        </div>
      )}
      {tab === "subscription" && <SubscriptionPanel siteCode={siteCode} />}
      {tab === "payments" && <PaymentsPanel siteCode={siteCode} />}
      {tab === "loan" && <LoanPanel siteCode={siteCode} />}
      {tab === "resale" && <ResalePanel siteCode={siteCode} />}
      {tab === "tax" && <TaxPanel siteCode={siteCode} />}
      {tab === "org" && <OrgTree siteCode={siteCode} />}
      {tab === "commission" && <CommissionBoard siteCode={siteCode} />}
      {tab === "desk" && (<div className="grid gap-6 lg:grid-cols-2"><DeskCheckin siteCode={siteCode} /><VisitorStats siteCode={siteCode} /></div>)}
    </div>
  );
}
