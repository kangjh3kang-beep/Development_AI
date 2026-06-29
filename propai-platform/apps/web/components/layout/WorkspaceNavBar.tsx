"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
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
      className="hidden rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] p-2 shadow-[var(--shadow-sm)] lg:block"
    >
      <div className="grid gap-2 xl:grid-cols-5">
        {visibleSections.slice(0, 5).map((section) => {
          const links = flattenLinks(section.items).slice(0, 3);
          const active = activeSections.has(section.id);
          return (
            <section
              key={section.id}
              className={`min-w-0 rounded-xl border p-3 ${
                active
                  ? "border-[var(--accent-strong)]/35 bg-[var(--accent-soft)]"
                  : "border-transparent bg-[var(--surface-soft)]"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-xs font-black text-[var(--text-primary)]">
                  {section.title}
                </p>
                {active && (
                  <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)]" />
                )}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {links.map((link) => {
                  const linkActive = isHrefActive(link.href, pathname);
                  return (
                    <Link
                      key={link.id}
                      href={link.href!}
                      prefetch={link.prefetch}
                      className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold transition ${
                        linkActive
                          ? "bg-[var(--accent-strong)] text-white"
                          : "bg-[var(--surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      {link.label}
                    </Link>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </nav>
  );
}
