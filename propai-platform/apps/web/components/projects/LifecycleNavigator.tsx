"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";

interface Stage {
  id: string;
  label: string;
  icon: string;
  links: Array<{ href: string; label: string; icon: string }>;
}

export function LifecycleNavigator({
  locale,
  projectId,
}: {
  locale: string;
  projectId: string;
}) {
  const pathname = usePathname();

  const stages: Stage[] = [
    {
      id: "index",
      label: "개요",
      icon: "📊",
      links: [{ href: `/${locale}/projects/${projectId}`, label: "프로젝트 개요", icon: "📊" }],
    },
    {
      id: "analysis",
      label: "입지 분석",
      icon: "🗺️",
      links: [{ href: `/${locale}/projects/${projectId}/site-analysis`, label: "부지 분석", icon: "🗺️" }],
    },
    {
      id: "legal",
      label: "법규 검토",
      icon: "⚖️",
      links: [{ href: `/${locale}/projects/${projectId}/legal`, label: "법규 검토", icon: "⚖️" }],
    },
    {
      id: "architecture",
      label: "건축 설계",
      icon: "🎨",
      links: [
        { href: `/${locale}/projects/${projectId}/design`, label: "설계 AI", icon: "🎨" },
        { href: `/${locale}/projects/${projectId}/cad`, label: "도면 분석", icon: "📐" },
        { href: `/${locale}/projects/${projectId}/bim`, label: "BIM 모델", icon: "🏛️" },
      ],
    },
    {
      id: "feasibility",
      label: "사업성 검토",
      icon: "📈",
      links: [
        { href: `/${locale}/projects/${projectId}/feasibility`, label: "수지분석", icon: "📈" },
        { href: `/${locale}/projects/${projectId}/finance`, label: "재무 모델링", icon: "💰" },
        { href: `/${locale}/projects/${projectId}/esg`, label: "ESG / LCA", icon: "🌿" },
      ],
    },
    {
      id: "permit",
      label: "인허가/계약",
      icon: "📝",
      links: [
        { href: `/${locale}/projects/${projectId}/permit`, label: "인허가 관리", icon: "📝" },
        { href: `/${locale}/projects/${projectId}/blockchain`, label: "블록체인", icon: "⛓️" },
        { href: `/${locale}/projects/${projectId}/contracts`, label: "전자 계약", icon: "📜" },
      ],
    },
    {
      id: "execution",
      label: "시공 관리",
      icon: "🏗️",
      links: [
        { href: `/${locale}/projects/${projectId}/construction`, label: "시공 원가", icon: "🏗️" },
        { href: `/${locale}/projects/${projectId}/drone`, label: "드론 측량", icon: "🚁" },
      ],
    },
    {
      id: "management",
      label: "운영 관리",
      icon: "⚙️",
      links: [
        { href: `/${locale}/projects/${projectId}/operations`, label: "자산 운영", icon: "⚙️" },
        { href: `/${locale}/projects/${projectId}/report`, label: "최종 보고서", icon: "📄" },
      ],
    },
  ];

  const currentStage = stages.find((s) =>
    s.links.some((l) => pathname === l.href)
  ) || stages[0];

  return (
    <div className="flex flex-col gap-4 relative z-40">
      {/* Primary Stages Horizontal Bar */}
      <nav className="sticky top-[80px] flex w-full gap-1 overflow-x-auto rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-1.5 shadow-[var(--shadow-lg)] backdrop-blur-3xl scrollbar-hide">
        {stages.map((stage) => {
          const isActive = currentStage.id === stage.id;
          return (
            <Link
              key={stage.id}
              href={stage.links[0].href}
              className={`flex min-w-max items-center gap-2 rounded-xl px-5 py-2.5 text-[13px] font-black transition-all duration-300 ${
                isActive
                  ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)] scale-[1.02]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-strong)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="text-base">{stage.icon}</span>
              <span>{stage.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Sub-links (only if multiple) */}
      <div className="min-h-[40px]">
        {currentStage.links.length > 1 && (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex w-full gap-2 overflow-x-auto rounded-[var(--radius-lg)] bg-[var(--surface-muted)] p-1 scrollbar-hide border border-[var(--line-subtle)]"
          >
            {currentStage.links.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex min-w-max items-center gap-2 rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
                    isActive
                      ? "bg-[var(--surface)] text-[var(--accent-strong)] shadow-sm border border-[var(--line-strong)]"
                      : "text-[var(--text-hint)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-secondary)]"
                  }`}
                >
                  <span className="text-sm">{link.icon}</span>
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </motion.div>
        )}
      </div>
    </div>
  );
}
