"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import React from "react";

/* ── SVG Icons (Lucide-style, 18x18) ── */

type IconProps = React.SVGAttributes<SVGElement>;

const Icons = {
  Overview: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>,
  SiteAnalysis: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/></svg>,
  Legal: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"/></svg>,
  Design: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>,
  Feasibility: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M22 12h-2.5a2 2 0 0 0 0 4H21a2 2 0 0 1 0 4h-2.5M7 5v14M2 5h10M2 19h10"/><path d="M18 5v14"/></svg>,
  Permit: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/></svg>,
  Construction: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M16 10h.01"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/></svg>,
  Operations: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>,
  // Sub-icons
  Cad: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>,
  Bim: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22.54 12.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.84l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.85Z"/></svg>,
  Finance: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
  Esg: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M11 20A7 7 0 0 1 9.8 6.9C15.5 4.9 17 3.5 17 3.5s1.5 2.5 2.5 6.5"/><path d="M11.7 10.5c.9.3 1.5 1.3 1.5 2.5 0 1.7-1.3 3-3 3s-3-1.3-3-3c0-1.2.7-2.2 1.6-2.7"/></svg>,
  Chain: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>,
  Contract: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/></svg>,
  Drone: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/></svg>,
  Report: (p: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>,
};

/* ── Types ── */

interface SubLink {
  href: string;
  label: string;
  icon: React.ReactNode;
}

interface Stage {
  id: string;
  label: string;
  icon: React.ReactNode;
  links: SubLink[];
}

/* ── Component ── */

export function LifecycleNavigator({
  locale,
  projectId,
}: {
  locale: string;
  projectId: string;
}) {
  const pathname = usePathname();
  const base = `/${locale}/projects/${projectId}`;

  const stages: Stage[] = [
    {
      id: "index", label: "개요", icon: <Icons.Overview />,
      links: [{ href: base, label: "프로젝트 개요", icon: <Icons.Overview /> }],
    },
    {
      id: "analysis", label: "입지 분석", icon: <Icons.SiteAnalysis />,
      links: [{ href: `${base}/site-analysis`, label: "부지 분석", icon: <Icons.SiteAnalysis /> }],
    },
    {
      id: "legal", label: "법규 검토", icon: <Icons.Legal />,
      links: [{ href: `${base}/legal`, label: "법규 검토", icon: <Icons.Legal /> }],
    },
    {
      id: "architecture", label: "건축 설계", icon: <Icons.Design />,
      links: [
        { href: `${base}/design`, label: "설계 AI", icon: <Icons.Design /> },
        { href: `${base}/cad`, label: "도면 편집", icon: <Icons.Cad /> },
        { href: `${base}/bim`, label: "BIM 모델", icon: <Icons.Bim /> },
      ],
    },
    {
      id: "feasibility", label: "사업성 검토", icon: <Icons.Feasibility />,
      links: [
        { href: `${base}/feasibility`, label: "수지분석", icon: <Icons.Feasibility /> },
        { href: `${base}/finance`, label: "재무 모델링", icon: <Icons.Finance /> },
        { href: `${base}/esg`, label: "ESG / LCA", icon: <Icons.Esg /> },
      ],
    },
    {
      id: "permit", label: "인허가/계약", icon: <Icons.Permit />,
      links: [
        { href: `${base}/permit`, label: "인허가 관리", icon: <Icons.Permit /> },
        { href: `${base}/blockchain`, label: "블록체인", icon: <Icons.Chain /> },
        { href: `${base}/contracts`, label: "전자 계약", icon: <Icons.Contract /> },
      ],
    },
    {
      id: "execution", label: "시공 관리", icon: <Icons.Construction />,
      links: [
        { href: `${base}/construction`, label: "시공 원가", icon: <Icons.Construction /> },
        { href: `${base}/drone`, label: "드론 측량", icon: <Icons.Drone /> },
      ],
    },
    {
      id: "management", label: "운영", icon: <Icons.Operations />,
      links: [
        { href: `${base}/operations`, label: "자산 운영", icon: <Icons.Operations /> },
        { href: `${base}/report`, label: "최종 보고서", icon: <Icons.Report /> },
      ],
    },
  ];

  // pathname 매칭 개선: 정확 매칭 + 서브경로 매칭
  const currentStage = stages.find((s) =>
    s.links.some((l) => pathname === l.href || (l.href !== base && pathname.startsWith(l.href)))
  ) || stages[0];

  return (
    <div className="flex flex-col gap-3 relative z-40">
      {/* 1차 탭 바 */}
      <nav className="sticky top-[80px] flex w-full gap-0.5 overflow-x-auto rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)]/80 p-1 shadow-lg backdrop-blur-2xl scrollbar-hide">
        {stages.map((stage) => {
          const isActive = currentStage.id === stage.id;
          return (
            <Link
              key={stage.id}
              href={stage.links[0].href}
              className={`flex min-w-max items-center gap-2 rounded-xl px-4 py-2 text-[13px] font-bold transition-all ${
                isActive
                  ? "bg-[var(--accent-strong)] text-white shadow-md"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
              }`}
            >
              {stage.icon}
              <span>{stage.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* 2차 서브탭 (멀티 링크 있을 때만) */}
      {currentStage.links.length > 1 && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex gap-1 rounded-xl bg-[var(--surface-muted)] p-1 border border-[var(--line-subtle)]"
        >
          {currentStage.links.map((link) => {
            const isActive = pathname === link.href || (link.href !== base && pathname.startsWith(link.href));
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                  isActive
                    ? "bg-[var(--surface)] text-[var(--accent-strong)] shadow-sm border border-[var(--line)]"
                    : "text-[var(--text-hint)] hover:text-[var(--text-secondary)]"
                }`}
              >
                {link.icon}
                <span>{link.label}</span>
              </Link>
            );
          })}
        </motion.div>
      )}
    </div>
  );
}
