"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { fetchAuthMeRole, fetchIsAdmin } from "@/lib/use-is-admin";
import {
  type NavNode,
  type NavSection,
  activeSectionIds,
  isHrefActive,
} from "./nav-config";

function flattenLinks(items: NavNode[]): NavNode[] {
  const out: NavNode[] = [];
  const walk = (node: NavNode) => {
    if (node.href) out.push(node);
    for (const child of node.children ?? []) walk(child);
  };
  for (const item of items) walk(item);
  return out;
}

export function WorkspaceNavBar({ sections }: { sections: NavSection[] }) {
  const pathname = usePathname();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [isAssetOps, setIsAssetOps] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetchIsAdmin().catch(() => false),
      fetchAuthMeRole().catch(() => ""),
    ])
      .then(([admin, role]) => {
        if (!alive) return;
        setIsAdmin(admin);
        setIsAssetOps(
          admin || ["asset_manager", "operations", "운영관리자", "자산운용"].includes(role),
        );
      })
      .catch(() => {
        if (!alive) return;
        setIsAdmin(false);
        setIsAssetOps(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const activeSections = useMemo(
    () => new Set(activeSectionIds(sections, pathname)),
    [sections, pathname],
  );

  const visibleSections = sections.filter(
    (section) =>
      (!section.adminOnly || isAdmin === true) &&
      (!section.assetOpsOnly || isAssetOps === true),
  );

  return (
    <nav
      aria-label="Workspace navigation"
      className="hidden rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] px-3 py-2 shadow-[var(--shadow-sm)] lg:block"
    >
      <div className="flex items-center gap-1">
        {visibleSections.slice(0, 5).map((section) => {
          const links = flattenLinks(section.items).slice(0, 3);
          const active = activeSections.has(section.id);
          return (
            <details
              key={section.id}
              className="group relative"
            >
              <summary
                className={`flex h-10 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm font-bold transition [&::-webkit-details-marker]:hidden ${
                  active
                    ? "bg-[var(--text-primary)] text-white"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span>{section.title}</span>
                <ChevronDown
                  aria-hidden="true"
                  className="h-4 w-4 transition-transform group-open:rotate-180"
                />
                {active && (
                  <span className="sr-only">현재 섹션</span>
                )}
              </summary>
              <div className="absolute left-0 top-12 z-50 hidden min-w-64 rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)] p-2 shadow-[var(--shadow-md)] group-open:block">
                {links.map((link) => {
                  const linkActive = isHrefActive(link.href, pathname);
                  return (
                    <Link
                      key={link.id}
                      href={link.href!}
                      prefetch={link.prefetch}
                      className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-bold transition ${
                        linkActive
                          ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      <span>{link.label}</span>
                      {linkActive && <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)]" />}
                    </Link>
                  );
                })}
              </div>
            </details>
          );
        })}
        <Link
          href={pathname?.replace(/\/$/, "") || "/"}
          aria-label="현재 워크스페이스 새로고침"
          className="ml-auto inline-flex h-10 items-center rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-sm font-bold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        >
          워크스페이스
        </Link>
      </div>
    </nav>
  );
}
