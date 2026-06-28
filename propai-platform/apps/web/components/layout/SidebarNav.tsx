"use client";

/**
 * 접이식 그룹형 좌측 네비게이션 — IA 원칙(docs/design/navigation-ia-system.md) 렌더러.
 *
 * 단일 트리(nav-config)를 재귀 렌더한다: L1 섹션(접기/펼치기) → L2 항목/그룹 → L3 하위메뉴.
 * 활성 경로의 섹션·그룹은 자동 펼침(activeGroupIds/activeSectionIds), 펼침 상태는 localStorage 기억.
 * 역할 게이팅(adminOnly/assetOpsOnly)·홈 리셋(goHome)은 기존 동작 보존.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchAuthMeRole, fetchIsAdmin } from "@/lib/use-is-admin";
import { useUiReset } from "@/store/useUiReset";
import {
  type NavNode,
  type NavSection,
  activeGroupIds,
  activeSectionIds,
  isHrefActive,
} from "./nav-config";

const STORAGE_KEY = "propai-nav-expanded";
const HOME_RE = /^\/[a-z]{2}(-[A-Z]{2})?$/;

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
      aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function SidebarNav({ sections }: { sections: NavSection[] }) {
  const pathname = usePathname();
  const goHome = useUiReset((s) => s.goHome);

  // 역할 게이팅(서버 tier 기반) — admin/assetOps 섹션 노출 제어. 미확인 시 보수적 숨김.
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [isAssetOps, setIsAssetOps] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    Promise.all([
      // ★is-admin·role 모두 세션캐시(fetchIsAdmin/fetchAuthMeRole) 공유 — 다른 소비처와 1회 호출만
      //   공유(반복 왕복 제거). 페이지 전환마다 재호출하던 /auth/me·/auth/is-admin 왕복을 세션당 1회로.
      fetchIsAdmin().catch(() => false),
      fetchAuthMeRole().catch(() => ""),
    ]).then(([admin, role]) => {
      if (!alive) return;
      setIsAdmin(admin);
      setIsAssetOps(admin || ["asset_manager", "operations", "운영관리자", "자산운용"].includes(role));
    }).catch(() => { if (alive) { setIsAdmin(false); setIsAssetOps(false); } });
    return () => { alive = false; };
  }, []);

  // 펼침 상태(명시 토글만 저장) — 미설정 항목은 default(섹션 펼침 / 그룹은 활성 시 펼침).
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setExpanded(JSON.parse(raw));
    } catch {
      /* localStorage 불가 환경 — 무시(기본 동작) */
    }
  }, []);

  const toggle = useCallback((id: string, fallbackOpen: boolean) => {
    setExpanded((prev) => {
      const cur = prev[id] ?? fallbackOpen;
      const next = { ...prev, [id]: !cur };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* 무시 */
      }
      return next;
    });
  }, []);

  const activeSections = useMemo(() => new Set(activeSectionIds(sections, pathname)), [sections, pathname]);
  const activeGroups = useMemo(() => new Set(activeGroupIds(sections, pathname)), [sections, pathname]);

  const visibleSections = sections.filter(
    (s) => (!s.adminOnly || isAdmin === true) && (!s.assetOpsOnly || isAssetOps === true),
  );

  const leafClass = (active: boolean) =>
    `group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] font-semibold transition-colors duration-200 ${
      active
        ? "text-[var(--accent-strong)] bg-[var(--accent-soft)] border border-[var(--accent-strong)]/20"
        : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
    }`;

  function renderLeaf(node: NavNode, depth: number) {
    const active = isHrefActive(node.href, pathname);
    return (
      <Link
        key={node.id}
        href={node.href!}
        prefetch={node.prefetch}
        onClick={() => {
          if (active && HOME_RE.test(node.href!)) goHome();
        }}
        className={leafClass(active)}
      >
        {active && (
          <span className="absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-[var(--accent-strong)]" aria-hidden="true" />
        )}
        {node.icon && (
          <span className={`shrink-0 ${active ? "text-[var(--accent-strong)]" : "text-[var(--text-hint)] group-hover:text-[var(--text-primary)]"}`}>
            {node.icon}
          </span>
        )}
        <span className="truncate">{node.label}</span>
      </Link>
    );
  }

  function renderGroup(node: NavNode, depth: number) {
    const trailActive = activeGroups.has(node.id) || isHrefActive(node.href, pathname);
    const open = expanded[node.id] ?? activeGroups.has(node.id);
    return (
      <div key={node.id}>
        <div className={`flex items-center ${leafClass(false)} ${trailActive ? "text-[var(--text-primary)]" : ""} !py-0`}>
          {node.href ? (
            <Link href={node.href} prefetch={node.prefetch} className="flex flex-1 items-center gap-2.5 py-2 min-w-0">
              {node.icon && (
                <span className={`shrink-0 ${trailActive ? "text-[var(--accent-strong)]" : "text-[var(--text-hint)]"}`}>{node.icon}</span>
              )}
              <span className="truncate">{node.label}</span>
            </Link>
          ) : (
            <button
              type="button"
              onClick={() => toggle(node.id, activeGroups.has(node.id))}
              className="flex flex-1 items-center gap-2.5 py-2 min-w-0 text-left"
            >
              {node.icon && <span className="shrink-0 text-[var(--text-hint)]">{node.icon}</span>}
              <span className="truncate">{node.label}</span>
            </button>
          )}
          <button
            type="button"
            aria-label={open ? "접기" : "펼치기"}
            aria-expanded={open}
            onClick={() => toggle(node.id, activeGroups.has(node.id))}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--text-hint)] hover:text-[var(--text-primary)]"
          >
            <ChevronDown open={open} />
          </button>
        </div>
        {open && (
          <div className="ml-[18px] mt-0.5 flex flex-col gap-0.5 border-l border-[var(--line)] pl-2">
            {(node.children ?? []).map((c) => renderNode(c, depth + 1))}
          </div>
        )}
      </div>
    );
  }

  function renderNode(node: NavNode, depth: number) {
    return node.children?.length ? renderGroup(node, depth) : renderLeaf(node, depth);
  }

  return (
    <>
      {visibleSections.map((section, idx) => {
        const open = expanded[section.id] ?? true; // 섹션 기본 펼침(접기 가능)
        const sectionActive = activeSections.has(section.id);
        return (
          <div key={section.id}>
            {idx > 0 && <div className="h-px bg-[var(--line)] opacity-50 mb-2" aria-hidden="true" />}
            <button
              type="button"
              aria-expanded={open}
              onClick={() => toggle(section.id, true)}
              className={`flex w-full items-center gap-1.5 px-2 pb-1.5 text-[11px] font-bold tracking-normal transition-colors ${
                sectionActive ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
              }`}
            >
              <ChevronDown open={open} />
              {section.title}
            </button>
            {open && (
              <nav className="grid gap-0.5">
                {section.items.map((node) => renderNode(node, 0))}
              </nav>
            )}
          </div>
        );
      })}
    </>
  );
}
