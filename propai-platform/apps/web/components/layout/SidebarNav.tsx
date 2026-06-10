"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

type NavItem = {
  href: string;
  label: string;
  icon: React.ReactNode;
};

type NavSection = {
  title: string;
  items: NavItem[];
  adminOnly?: boolean;     // 관리자(admin/manager)에게만 노출
  assetOpsOnly?: boolean;  // 자산운용/운영권한(admin/manager/owner/총괄관리자/asset_manager)에게만 노출
};

type SidebarNavProps = {
  sections: NavSection[];
};

export function SidebarNav({ sections }: SidebarNavProps) {
  const pathname = usePathname();
  // 역할 확인(클라이언트): 관리자 전용 섹션 노출 제어
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  // 자산 운영(임대·임차인 등) 노출 권한: 운영/관리자 역할만. 역할 미확인 시 보수적으로 숨김.
  const [isAssetOps, setIsAssetOps] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    // ★관리자 여부는 서버의 tier 기반 /auth/is-admin으로만 판별한다.
    //  (role은 가입 시 전원 'admin'이라 role 폴백을 쓰면 관리 메뉴가 전원 노출되는 누출이 된다.)
    Promise.all([
      apiClient.get<{ is_admin?: boolean }>("/auth/is-admin", { useMock: false }).catch(() => ({ is_admin: false })),
      apiClient.get<{ role?: string }>("/auth/me", { useMock: false }).catch(() => ({ role: "" })),
    ]).then(([a, u]) => {
      if (!alive) return;
      const admin = (a as { is_admin?: boolean })?.is_admin === true;
      const role = (u as { role?: string })?.role || "";
      setIsAdmin(admin);
      // 운영권한 = 관리자 ∪ 자산운용 역할(이건 별도 운영역할이라 role 기반 유지).
      setIsAssetOps(admin || ["asset_manager", "operations", "운영관리자", "자산운용"].includes(role));
    }).catch(() => { if (alive) { setIsAdmin(false); setIsAssetOps(false); } });
    return () => { alive = false; };
  }, []);

  // adminOnly/assetOpsOnly 섹션은 해당 권한 확인 전/무권한이면 숨김
  const visibleSections = sections.filter((s) =>
    (!s.adminOnly || isAdmin === true) &&
    (!s.assetOpsOnly || isAssetOps === true),
  );

  return (
    <>
      {visibleSections.map((section, sectionIdx) => (
        <div key={section.title}>
          {sectionIdx > 0 && (
            <div className="h-px bg-[var(--line)] opacity-50 mb-3" aria-hidden="true" />
          )}
          <p className="px-3 pb-1.5 text-[11px] font-bold tracking-normal text-[var(--text-tertiary)]">
            {section.title}
          </p>
          <nav className="grid gap-1">
            {(section.items ?? []).map((item) => {
              const isActive = pathname === item.href;
              
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] font-semibold transition-all duration-300 overflow-hidden ${
                    isActive
                      ? "text-[var(--accent-strong)] bg-[var(--accent-soft)] shadow-[inset_0_0_20px_var(--accent-soft)] border border-[var(--accent-strong)]/20"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-white"
                  }`}
                >
                  {/* Hover/Active Glow Background */}
                  {isActive && (
                    <motion.div
                      layoutId="active-sidebar-bg"
                      className="absolute inset-0 bg-[var(--accent-soft)]"
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                  )}
                  
                  {/* Left Active Indicator */}
                  {isActive && (
                    <div className="absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]" />
                  )}

                  <span className={`relative z-10 shrink-0 transition-colors ${isActive ? "text-[var(--accent-strong)]" : "text-[var(--text-hint)] group-hover:text-white"}`}>
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
