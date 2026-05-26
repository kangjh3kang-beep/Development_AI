"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";

type NavItem = {
  href: string;
  label: string;
  icon: React.ReactNode;
};

type NavSection = {
  title: string;
  items: NavItem[];
};

type SidebarNavProps = {
  sections: NavSection[];
};

export function SidebarNav({ sections }: SidebarNavProps) {
  const pathname = usePathname();

  return (
    <>
      {sections.map((section, sectionIdx) => (
        <div key={section.title}>
          {sectionIdx > 0 && (
            <div className="h-px bg-[var(--line)] opacity-50 mb-5" aria-hidden="true" />
          )}
          <p className="px-3 pb-2.5 text-[11px] font-bold tracking-[0.12em] text-[var(--text-tertiary)] uppercase">
            {section.title}
          </p>
          <nav className="grid gap-1.5">
            {section.items.map((item) => {
              const isActive = pathname === item.href;
              
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-semibold transition-all duration-300 overflow-hidden ${
                    isActive 
                      ? "text-teal-400 bg-teal-500/10 shadow-[inset_0_0_20px_rgba(20,184,166,0.1)] border border-teal-500/20" 
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-white"
                  }`}
                >
                  {/* Hover/Active Glow Background */}
                  {isActive && (
                    <motion.div 
                      layoutId="active-sidebar-bg"
                      className="absolute inset-0 bg-teal-500/5" 
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                  )}
                  
                  {/* Left Active Indicator */}
                  {isActive && (
                    <div className="absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-teal-400 shadow-[0_0_10px_rgba(45,212,191,0.8)]" />
                  )}

                  <span className={`relative z-10 shrink-0 transition-colors ${isActive ? "text-teal-400" : "text-[var(--text-hint)] group-hover:text-white"}`}>
                    {item.icon}
                  </span>
                  <span className="relative z-10">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      ))}
    </>
  );
}
