"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import React from "react";
import { StageIcon } from "@/components/common/StageIcon";
import { STAGE_GROUPS, STAGE_META } from "@/lib/lifecycle-stages";

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

  // 상단탭 = 단계 SSOT(lib/lifecycle-stages)의 그룹 뷰.
  // 각 그룹은 SSOT 단계들(STAGE_META)을 서브링크로 펼치고, 死라우트 보존용 extraRoutes를 더한다.
  const stages: Stage[] = STAGE_GROUPS.map((group) => {
    if (group.id === "overview") {
      return {
        id: group.id,
        label: group.label,
        icon: <StageIcon id={group.icon} size={18} />,
        links: [{ href: base, label: "프로젝트 개요", icon: <StageIcon id={group.icon} size={16} /> }],
      };
    }
    const links: SubLink[] = (group.stages ?? []).map((stageId) => {
      const meta = STAGE_META[stageId];
      return {
        href: `${base}/${meta.route}`,
        label: meta.label,
        icon: <StageIcon id={meta.icon} size={16} />,
      };
    });
    (group.extraRoutes ?? []).forEach((extra) => {
      links.push({
        href: `${base}/${extra.route}`,
        label: extra.label,
        icon: <StageIcon id={extra.icon} size={16} />,
      });
    });
    return {
      id: group.id,
      label: group.label,
      icon: <StageIcon id={group.icon} size={18} />,
      links,
    };
  });

  // pathname 매칭 개선: 정확 매칭 + 서브경로 매칭
  const currentStage = stages.find((s) =>
    (s.links ?? []).some((l) => pathname === l.href || (l.href !== base && pathname.startsWith(l.href)))
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
      {currentStage.links?.length > 1 && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex gap-1 rounded-xl bg-[var(--surface-muted)] p-1 border border-[var(--line-subtle)]"
        >
          {(currentStage.links ?? []).map((link) => {
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
