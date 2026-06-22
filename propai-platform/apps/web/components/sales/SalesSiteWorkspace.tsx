"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, ClipboardList, Key, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { salesApi, salesGlobal } from "@/lib/salesApi";
import type { Locale } from "@/i18n/config";
import UnitGrid from "@/components/sales/UnitGrid";
import Unit360Panel from "@/components/sales/Unit360Panel";
import PriceTableEditor from "@/components/sales/PriceTableEditor";
import PricingConfigPanel from "@/components/sales/PricingConfigPanel";
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
import IntegrityGuard from "@/components/sales/IntegrityGuard";
import CrmPanel from "@/components/sales/CrmPanel";
import SitePasswordModal from "@/components/sales-app/SitePasswordModal";

type Tab = "overview" | "units" | "pricing" | "subscription" | "payments" | "loan" | "resale" | "tax" | "org" | "commission" | "desk" | "crm" | "integrity";
const TABS: { key: Tab; label: string; icon?: LucideIcon }[] = [
  { key: "overview", label: "설정·요약", icon: ClipboardList },
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
  { key: "crm", label: "고객 예측", icon: Bot },
  { key: "integrity", label: "무결성 가드", icon: ShieldCheck },
];

type SiteInfo = {
  id: string;
  site_code: string;
  site_name: string;
  status?: string | null;
  development_type?: string | null;
};

export default function SalesSiteWorkspace({ siteCode, locale }: { siteCode: string; locale: Locale }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [rounds, setRounds] = useState<{ id: string; name: string }[]>([]);
  const [rid, setRid] = useState("");
  const [siteName, setSiteName] = useState("");
  const [siteInfo, setSiteInfo] = useState<SiteInfo | null>(null);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [priceRefresh, setPriceRefresh] = useState(0);
  const [pwOpen, setPwOpen] = useState(false);

  useEffect(() => {
    salesApi(siteCode).get<{ id: string; name: string }[]>("/rounds")
      .then((r) => { setRounds(r || []); if (r?.[0]) setRid(r[0].id); })
      .catch(() => setRounds([]));
    salesGlobal.get<SiteInfo[]>("/sites")
      .then((ss) => {
        const me = (ss || []).find((x) => x.site_code === siteCode) || null;
        setSiteInfo(me);
        setSiteName(me?.site_name || "");
      })
      .catch(() => {});
  }, [siteCode]);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Link href={`/${locale}/sales`} className="text-sm text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">← 현장 목록</Link>
        <div>
          <span className="cc-meta">SITE · ADMIN CONSOLE</span>
          <h1 className="mt-0.5 text-lg font-black leading-tight text-[var(--text-primary)]">{siteName || "분양 현장"}</h1>
        </div>
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
            {t.icon ? (
              <span className="inline-flex items-center gap-1.5"><t.icon className="size-4" aria-hidden />{t.label}</span>
            ) : (
              t.label
            )}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-5">
          {/* 현장 기본정보 + 비밀번호 설정 */}
          <div className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
            <div className="cc-grid-bg opacity-40" />
            <i className="cc-bracket cc-bracket--tl" />
            <i className="cc-bracket cc-bracket--tr" />
            <i className="cc-bracket cc-bracket--bl" />
            <i className="cc-bracket cc-bracket--br" />
            <div className="relative z-10 flex flex-wrap items-start justify-between gap-3">
              <div>
                <span className="cc-meta">SITE · OVERVIEW</span>
                <h2 className="mt-1 text-xl font-black text-[var(--text-primary)]">{siteName || "분양 현장"}</h2>
                <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--text-secondary)]">
                  <span>현장코드 <b className="cc-num text-[var(--text-primary)]">{siteInfo?.site_code || siteCode}</b></span>
                  {siteInfo?.development_type && <span>유형 <b className="text-[var(--text-primary)]">{siteInfo.development_type}</b></span>}
                  {siteInfo?.status && <span>상태 <b className="text-[var(--accent-strong)]">{siteInfo.status}</b></span>}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPwOpen(true)}
                disabled={!siteInfo?.id}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--accent-strong)]/50 bg-[var(--accent-strong)]/10 px-4 py-2 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-strong)]/20 disabled:opacity-50"
              >
                <Key className="size-4" aria-hidden /> 현장앱 비밀번호 설정/변경
              </button>
            </div>
            <p className="relative z-10 mt-3 rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--text-hint)]">
              현장앱(현장 직원용)은 2차 비밀번호로 보호됩니다. 위 버튼으로 먼저 비밀번호를 설정한 뒤 직원에게 공유하세요.
            </p>
          </div>

          {/* 관리 메뉴 빠른 이동 — 각 기능 안내 */}
          <div>
            <p className="mb-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">관리 메뉴</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {([
                { key: "units" as Tab, label: "세대 배치도", desc: "동·호 배치·상태" },
                { key: "pricing" as Tab, label: "분양가", desc: "회차별 가격표" },
                { key: "subscription" as Tab, label: "청약·당첨", desc: "접수·추첨·당첨" },
                { key: "payments" as Tab, label: "수납·납부", desc: "계약·중도·잔금" },
                { key: "loan" as Tab, label: "중도금 대출", desc: "대출 알선·실행" },
                { key: "resale" as Tab, label: "전매·실거래", desc: "전매·신고" },
                { key: "tax" as Tab, label: "세금·보증", desc: "취득세·보증" },
                { key: "org" as Tab, label: "조직도", desc: "본부·팀·직원" },
                { key: "commission" as Tab, label: "수수료", desc: "정산·더치페이" },
                { key: "desk" as Tab, label: "방문 안내데스크", desc: "체크인·방문통계" },
                { key: "crm" as Tab, label: "고객 예측", desc: "CRM·전환예측", icon: Bot },
                { key: "integrity" as Tab, label: "무결성 가드", desc: "데이터 검증", icon: ShieldCheck },
              ] as { key: Tab; label: string; desc: string; icon?: LucideIcon }[]).map((m) => (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setTab(m.key)}
                  className="flex flex-col items-start rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 text-left transition hover:border-[var(--accent-strong)] hover:shadow-[var(--shadow-sm)]"
                >
                  <span className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
                    {m.icon && <m.icon className="size-4" aria-hidden />}{m.label}
                  </span>
                  <span className="mt-0.5 text-[11px] text-[var(--text-tertiary)]">{m.desc}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "units" && (<><UnitGrid siteCode={siteCode} /><Unit360Panel siteCode={siteCode} /></>)}
      {tab === "pricing" && (
        <div className="space-y-3">
          {rounds.length > 1 && (
            <select value={rid} onChange={(e) => setRid(e.target.value)}
              className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-sm text-[var(--text-primary)]">
              {rounds.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          )}
          {rid ? (
            <>
              <PricingConfigPanel siteCode={siteCode} roundId={rid} onChanged={() => setPriceRefresh((n) => n + 1)} />
              <PriceTableEditor key={priceRefresh} siteCode={siteCode} roundId={rid} />
            </>
          ) : <p className="text-sm text-[var(--text-secondary)]">차수가 없습니다.</p>}
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
      {tab === "crm" && <CrmPanel siteCode={siteCode} />}
      {tab === "integrity" && <IntegrityGuard siteCode={siteCode} />}

      {siteInfo?.id && (
        <SitePasswordModal siteId={siteInfo.id} open={pwOpen} onClose={() => setPwOpen(false)} />
      )}
    </div>
  );
}
