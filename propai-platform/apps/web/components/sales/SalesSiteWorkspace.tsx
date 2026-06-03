"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { salesApi } from "@/lib/salesApi";
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

type Tab = "units" | "pricing" | "subscription" | "payments" | "loan" | "resale" | "tax" | "org" | "commission" | "desk";
const TABS: { key: Tab; label: string }[] = [
  { key: "units", label: "동호 배치도" },
  { key: "pricing", label: "분양가" },
  { key: "subscription", label: "청약" },
  { key: "payments", label: "수납" },
  { key: "loan", label: "중도금대출" },
  { key: "resale", label: "전매/실거래" },
  { key: "tax", label: "세무/보증" },
  { key: "org", label: "조직도" },
  { key: "commission", label: "수수료" },
  { key: "desk", label: "데스크" },
];

export default function SalesSiteWorkspace({ siteCode, locale }: { siteCode: string; locale: Locale }) {
  const [tab, setTab] = useState<Tab>("units");
  const [rounds, setRounds] = useState<{ id: string; name: string }[]>([]);
  const [rid, setRid] = useState("");
  const [genBusy, setGenBusy] = useState(false);

  useEffect(() => {
    salesApi(siteCode).get<{ id: string; name: string }[]>("/rounds")
      .then((r) => { setRounds(r || []); if (r?.[0]) setRid(r[0].id); })
      .catch(() => setRounds([]));
  }, [siteCode]);

  const generateUnits = async () => {
    const floors = Number(prompt("동호 생성(건축개요) — 층수?", "10") || 0);
    const upf = Number(prompt("층당 세대수?", "4") || 0);
    if (!floors || !upf) return;
    setGenBusy(true);
    try {
      await salesApi(siteCode).post("/units/generate", {
        source_type: "OUTLINE",
        params: { blocks: [{ name: "101", floors, units_per_floor: upf, types: [{ name: "84A" }] }] },
      });
      window.location.reload();
    } catch { alert("동호 생성 실패 (권한 확인)"); }
    finally { setGenBusy(false); }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Link href={`/${locale}/sales`} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">← 현장 목록</Link>
        <h1 className="text-lg font-black text-[var(--text-primary)]">현장: {siteCode}</h1>
        {tab === "units" && (
          <button onClick={generateUnits} disabled={genBusy}
            className="ml-auto rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-black text-white disabled:opacity-50">
            {genBusy ? "생성 중…" : "+ 동호 생성"}
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-2">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`rounded-lg px-3 py-1.5 text-sm font-bold ${tab === t.key ? "bg-[var(--accent-strong)] text-white" : "text-[var(--text-secondary)] hover:bg-[var(--surface-strong)]"}`}>
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
