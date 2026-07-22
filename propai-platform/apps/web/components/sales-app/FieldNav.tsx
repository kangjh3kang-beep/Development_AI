"use client";

/**
 * 분양 현장앱 — 모바일 하단 탭바 + 전체메뉴 시트(디자인 핸드오프 P0 #2).
 *
 * 21탭 가로스크롤의 모바일 인지부하를 디자인 의도(하단 5탭 + 전체메뉴 4그룹)대로 해소한다.
 * - 하단 탭바: 홈/고객/배치도/수납 주 슬롯(BOTTOM_NAV_KEYS) + '전체' 상시 슬롯.
 *   주 슬롯은 내 권한 노출 탭(visibleTabs)과 교집합만 렌더(고아 탭 이동 금지 — FieldHome 과 동일 규칙).
 * - 전체메뉴 시트: MENU_GROUPS(4그룹 IA SSOT)를 노출 탭과 교집합해 그리드로. 빈 그룹은 숨김.
 * - 데스크톱(sm+)은 기존 상단 탭바 유지 — 이 컴포넌트는 모바일 전용(sm:hidden).
 * 라벨·아이콘·게이팅 전부 roleConfig SSOT 소비(재정의 0).
 */

import { useEffect } from "react";
import { LayoutGrid, X } from "lucide-react";
import { BOTTOM_NAV_KEYS, MENU_GROUPS, type SalesTabDef } from "@/components/sales-app/roleConfig";

export function FieldBottomNav({
  tabs,
  activeTab,
  onNavigate,
  onOpenMenu,
}: {
  /** 내 권한으로 노출되는 탭(visibleTabs 결과) — 라벨·아이콘·게이팅의 단일 출처. */
  tabs: SalesTabDef[];
  activeTab: string;
  onNavigate: (tab: string) => void;
  onOpenMenu: () => void;
}) {
  const byKey = new Map(tabs.map((t) => [t.key, t]));
  const slots = BOTTOM_NAV_KEYS.map((k) => byKey.get(k)).filter((t): t is SalesTabDef => Boolean(t));
  // 주 슬롯에 없는 탭이 활성일 때(전체메뉴로 이동한 경우) '전체' 슬롯을 활성으로 표시.
  const menuActive = !slots.some((t) => t.key === activeTab);

  return (
    <nav
      aria-label="현장 하단 메뉴"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-[var(--line)] bg-[color:color-mix(in_srgb,var(--background)_92%,transparent)] pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
    >
      <div className="mx-auto grid max-w-md gap-1 px-2 py-1.5" style={{ gridTemplateColumns: `repeat(${slots.length + 1}, 1fr)` }}>
        {slots.map((t) => {
          const active = t.key === activeTab;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => onNavigate(t.key)}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-lg text-[10px] font-bold transition ${
                active ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {t.icon && <t.icon className="size-5" aria-hidden />}
              {/* 하단바는 폭이 좁아 짧은 라벨 사용(고객·상담→고객 등) — 첫 어절만. */}
              {t.label.split("·")[0].split(" ")[0]}
            </button>
          );
        })}
        <button
          type="button"
          onClick={onOpenMenu}
          aria-haspopup="dialog"
          className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-lg text-[10px] font-bold transition ${
            menuActive ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
          }`}
        >
          <LayoutGrid className="size-5" aria-hidden />
          전체
        </button>
      </div>
    </nav>
  );
}

export function FieldMenuSheet({
  open,
  tabs,
  activeTab,
  onNavigate,
  onClose,
}: {
  open: boolean;
  tabs: SalesTabDef[];
  activeTab: string;
  onNavigate: (tab: string) => void;
  onClose: () => void;
}) {
  // 열림 동안 배경 스크롤 잠금(모바일 시트 표준 UX).
  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // ESC 닫기(WAI-ARIA 다이얼로그 패턴) + sm(640px) 이상 확장 시 자동 닫기 —
  // 시트가 sm:hidden 으로 CSS 만 숨으면 body 잠금이 해제 불가로 남던 R1 지적 반영
  // (태블릿 회전·반응형 토글·폴더블 확장 시 스크롤 먹통 방지).
  useEffect(() => {
    if (!open || typeof window === "undefined") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    // matchMedia 는 일부 테스트 환경(jsdom)에 없을 수 있어 존재 시에만 바인드.
    const mq = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 640px)") : null;
    const onMq = () => {
      if (mq?.matches) onClose();
    };
    if (mq?.matches) onClose(); // 열림 시점에 이미 sm+ 면 즉시 닫기.
    mq?.addEventListener("change", onMq);
    return () => {
      window.removeEventListener("keydown", onKey);
      mq?.removeEventListener("change", onMq);
    };
  }, [open, onClose]);

  if (!open) return null;
  const byKey = new Map(tabs.map((t) => [t.key, t]));
  const groups = MENU_GROUPS.map((g) => ({
    title: g.title,
    items: g.keys.map((k) => byKey.get(k)).filter((t): t is SalesTabDef => Boolean(t)),
  })).filter((g) => g.items.length > 0);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="전체 메뉴"
      className="fixed inset-0 z-40 flex flex-col justify-end sm:hidden"
    >
      {/* 배경 딤 — 탭하면 닫힘 */}
      <button
        type="button"
        aria-label="메뉴 닫기"
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <div className="relative max-h-[80vh] overflow-y-auto rounded-t-2xl border-t border-[var(--line)] bg-[var(--background)] p-4 pb-[calc(env(safe-area-inset-bottom)+16px)] shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <span className="cc-label">MENU</span>
            <h2 className="text-[15px] font-black text-[var(--text-primary)]">전체 메뉴</h2>
            <p className="text-[10.5px] text-[var(--text-tertiary)]">{tabs.length}개 메뉴 · 내 권한 기준</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="grid size-9 place-items-center rounded-full border border-[var(--line)] text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)]"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          {groups.map((g) => (
            <section key={g.title}>
              <h3 className="cc-label mb-2">{g.title}</h3>
              <div className="grid grid-cols-4 gap-2">
                {g.items.map((t) => {
                  const active = t.key === activeTab;
                  return (
                    <button
                      key={t.key}
                      type="button"
                      onClick={() => {
                        onNavigate(t.key);
                        onClose();
                      }}
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-[68px] flex-col items-center justify-center gap-1.5 rounded-xl border px-1 py-2 text-center transition ${
                        active
                          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                          : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-primary)] hover:border-[var(--accent-strong)]"
                      }`}
                    >
                      {t.icon && <t.icon className={`size-5 ${active ? "" : "text-[var(--accent-strong)]"}`} aria-hidden />}
                      <span className="break-keep text-[10.5px] font-bold leading-tight">{t.label}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
