"use client";

/**
 * 분양 현장앱 내비게이션 — **두 표면이 같은 IA 를 접는 방식만 다르다**(DESIGN.md B3.3).
 *
 * 21탭 인지부하를 디자인 의도(하단 5탭 + 4그룹)대로 해소한다. IA SSOT 는 roleConfig 하나이고
 * 이 파일은 소비만 한다(라벨·아이콘·게이팅 재정의 0).
 * - `FieldBottomNav`(모바일 `sm:hidden`): 주 슬롯(BOTTOM_NAV_KEYS) + '전체' 상시 슬롯.
 *   주 슬롯은 내 권한 노출 탭(visibleTabs)과 교집합만 렌더(고아 탭 이동 금지 — FieldHome 과 동일 규칙).
 * - `FieldMenuSheet`(모바일): MENU_GROUPS 를 노출 탭과 교집합해 그리드로. 빈 그룹은 숨김.
 * - `FieldDesktopNav`(데스크톱 `hidden sm:block`): **같은** MENU_GROUPS 를 그룹 레일로.
 *   활성 그룹만 펼치므로 탭이 늘어도 상단이 길어지지 않는다.
 *
 * ★변이 생존에 대하여: 이 파일의 생존은 대부분 `className` **표기**다. 다만 그중
 *   **계약을 지는 className 은 셋**이다 — `sm:block`(데스크톱 전용 축) ·
 *   `role="tabpanel"`(패널 식별) · **`sa-tabbar`**(셸의 W2 음성 단언이 「나열 회귀」를
 *   탐지하는 **표지**. 여기서 이름을 바꾸면 그 표지가 닻을 잃는다). **셋 다 락이 있다.**
 *   ★경계를 이름으로 적는 이유: *"className 은 표기다"* 라고만 썼다가 `sm:block` 이
 *     그 변명에 덮여 **전 뷰포트에서 사라져도 초록**인 채 지나갔다(적대 리뷰 실증).
 *   ★★그리고 **이 문장 자체가 한 번 반증됐다** — 처음엔 「둘뿐」이라 적었는데 리뷰어가
 *     `sa-tabbar` 를 바꿔 `::VERDICT=SURVIVED` 를 받았다. **경계가 있었기 때문에 반증할 수
 *     있었다** — 그것이 경계를 적는 이유다. 지금은 셋 다 잠겨 있다.
 *
 * ★2026-09-07 — 종전엔 데스크톱만 **전 탭을 가로로 나열**했다(SiteWorkspaceClient 인라인).
 *   P0 가 선언한 인지부하 해소가 모바일 모집단에만 착지해 있었고 사용자가 데스크톱에서 신고했다.
 *   **처방을 한쪽에만 적용하면 나머지 절반이 그대로 샌다** — DESIGN.md B3.3 이 이것을 못 박는다.
 */

import { useEffect, useRef, useState } from "react";
import { LayoutGrid, X } from "lucide-react";
import { BOTTOM_NAV_KEYS, MENU_GROUPS, type SalesTabDef } from "@/components/sales-app/roleConfig";
import { DISMISS_Z, useDismissible } from "@/lib/satong-dismiss";
import { useModalFocus } from "@/hooks/useModalFocus";

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
              data-tab-key={t.key}
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
  const bodyRef = useRef<HTMLDivElement>(null);
  // 열림 동안 배경 스크롤 잠금(모바일 시트 표준 UX).
  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // ESC 닫기 — **자체 window 리스너에서 조정기로 이관**(2026-08-18).
  // 이 시트 위로 모달(현장 진입 등)이 열릴 수 있고, 종전에는 ESC 한 번에 둘 다 닫혔다.
  // 시트는 모달보다 아래 칸(`navSheet`)이라 모달이 먼저 닫히고, 다음 ESC 가 시트를 닫는다.
  useDismissible(DISMISS_Z.navSheet, open, onClose);

  // ★포커스 생명주기 — 트랩 범위는 **시트 본체**다(백드롭 딤 버튼은 밖).
  //   미룬 사유 둘을 재봤다:
  //   ① *"딤이 포커스 가능해 본체 트랩이면 닫을 수단이 없다"* → **본체 안에 닫기(X) 버튼이
  //      있다**. 게다가 딤을 트랩 안에 넣으면 Tab 순환에 화면 전체를 덮는 버튼이 끼어든다.
  //   ② *"항목을 누르면 라우팅으로 언마운트돼 복귀 대상이 사라진다"* → 훅이 이미
  //      `document.contains(restoreTo)` 로 막는다(사라진 요소로 되돌리지 않는다).
  useModalFocus(bodyRef, open);

  // sm(640px) 이상 확장 시 자동 닫기 — 시트가 sm:hidden 으로 CSS 만 숨으면 body 잠금이
  // 해제 불가로 남던 R1 지적 반영(태블릿 회전·반응형 토글·폴더블 확장 시 스크롤 먹통 방지).
  useEffect(() => {
    if (!open || typeof window === "undefined") return;
    // matchMedia 는 일부 테스트 환경(jsdom)에 없을 수 있어 존재 시에만 바인드.
    const mq = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 640px)") : null;
    const onMq = () => {
      if (mq?.matches) onClose();
    };
    if (mq?.matches) onClose(); // 열림 시점에 이미 sm+ 면 즉시 닫기.
    mq?.addEventListener("change", onMq);
    return () => {
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
      <div
        ref={bodyRef}
        className="relative max-h-[80vh] overflow-y-auto rounded-t-2xl border-t border-[var(--line)] bg-[var(--background)] p-4 pb-[calc(env(safe-area-inset-bottom)+16px)] shadow-2xl"
      >
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
                      data-tab-key={t.key}
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


/**
 * 데스크톱(sm+) 그룹 레일 — 모바일 시트와 **같은 MENU_GROUPS** 를 소비한다.
 *
 * 1줄: 고정 슬롯(어느 그룹에도 없는 탭) + 그룹 칩.  2줄: **활성 그룹만** 펼친 탭.
 * 종전 인라인 탭바는 `tabs.map` 으로 21개를 전부 그렸다 — 탭이 늘면 상단이 함께 길어졌다.
 * 지금은 상단 높이가 **가장 큰 그룹 크기**로 정해진다(그래서 `MENU_GROUP_MAX` 가 있다).
 *
 * ★고정 슬롯을 목록으로 적지 않는다 — 어느 그룹에도 속하지 않은 탭을 **파생**시킨다.
 *   목록으로 두면 새 탭이 그룹에도 목록에도 없을 때 **데스크톱에서만 조용히 사라진다**.
 *   (모바일 쪽 전단사 가드 `BOTTOM_NAV_KEYS ∪ MENU_GROUPS ∪ {home} == SALES_TABS` 와 같은 규율.)
 *
 * ## a11y — 두 층을 **다른 의미론**으로 나눈다 (적대 리뷰 2026-09-07 반영)
 *
 * 종전엔 2줄이 `role="tablist"` 인데 사용자가 다른 그룹을 펼치면 **`aria-selected="true"` 가
 * 하나도 없는 상태**가 만들어졌다(실증됨). 그래서:
 *   · 1줄 그룹 칩 = `role="tablist"`(어느 그룹을 볼지 고른다) · `aria-controls` 로 2줄을 가리킨다
 *   · 2줄 = `role="tabpanel"` 안의 **평범한 버튼** + 활성은 `aria-current="page"`
 *     (하단 탭바·고정 슬롯과 **같은 표기**로 통일 — 종전엔 `aria-current` 와 `aria-selected` 두 벌이었다)
 *   · 활성 탭을 품은 그룹 칩은 `aria-current` + 스크린리더 문구로 **어디에 있는지 말한다**
 *     (종전 표식은 `aria-hidden` 점 하나뿐이라 보조기술에 아무것도 전달되지 않았다)
 */
export function FieldDesktopNav({
  tabs,
  activeTab,
  onNavigate,
}: {
  /** 내 권한으로 노출되는 탭(visibleTabs 결과) — 라벨·아이콘·게이팅의 단일 출처. */
  tabs: SalesTabDef[];
  activeTab: string;
  onNavigate: (tab: string) => void;
}) {
  const byKey = new Map(tabs.map((t) => [t.key, t]));
  const groups = MENU_GROUPS.map((g) => ({
    title: g.title,
    items: g.keys.map((k) => byKey.get(k)).filter((t): t is SalesTabDef => Boolean(t)),
  })).filter((g) => g.items.length > 0); // 빈 그룹은 숨긴다(빈 껍데기 금지).

  const groupedKeys = new Set(MENU_GROUPS.flatMap((g) => g.keys));
  const pinned = tabs.filter((t) => !groupedKeys.has(t.key));

  // 사용자 선택을 **그것을 고른 시점의 탭과 함께** 저장한다. 탭이 바뀌면 저절로 무효가 되므로
  // effect 로 비우지 않아도 된다(effect 안 setState 는 연쇄 렌더 · lint 래칫이 잡는다).
  const [picked, setPicked] = useState<{ tab: string; title: string } | null>(null);
  const pickedTitle = picked?.tab === activeTab ? picked.title : null;
  const activeGroupTitle = groups.find((g) => g.items.some((t) => t.key === activeTab))?.title ?? null;

  // ★폴백은 **그룹 객체 단계**에서 한다. 종전엔 title 문자열로만 폴백해서, 고른 그룹이
  //   권한 변경으로 사라지면 `find` 가 null 이 되어 **2줄이 통째로 증발**했다(적대 리뷰 실증).
  const open =
    groups.find((g) => g.title === pickedTitle) ??
    groups.find((g) => g.title === activeGroupTitle) ??
    groups[0] ??
    null;

  const panelId = "field-desktop-nav-panel";

  return (
    <div className="sticky top-0 z-20 -mx-1 hidden border-b border-[var(--line)] bg-[color:color-mix(in_srgb,var(--background)_85%,transparent)] px-1 pt-1.5 backdrop-blur sm:block">
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5 px-1">
        <span className="cc-label">MENU</span>

        {pinned.map((t) => (
          <button
            key={t.key}
            type="button"
            data-tab-key={t.key}
            onClick={() => onNavigate(t.key)}
            aria-current={activeTab === t.key ? "page" : undefined}
            data-active={activeTab === t.key}
            className={`inline-flex min-h-[44px] items-center gap-1 rounded-lg px-3 text-xs font-black transition ${
              activeTab === t.key
                ? "bg-[var(--accent-strong)] text-white"
                : "border border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]"
            }`}
          >
            {t.icon && <t.icon className="size-4" aria-hidden />}
            {t.label}
          </button>
        ))}

        {pinned.length > 0 && groups.length > 0 && (
          <span aria-hidden className="mx-0.5 h-4 w-px bg-[var(--line)]" />
        )}

        <div role="tablist" aria-label="메뉴 그룹" className="flex flex-wrap items-center gap-1.5">
          {groups.map((g) => {
            const isOpen = open?.title === g.title;
            const holdsActive = g.items.some((t) => t.key === activeTab);
            return (
              <button
                key={g.title}
                type="button"
                role="tab"
                aria-selected={isOpen}
                aria-controls={panelId}
                aria-current={holdsActive ? "true" : undefined}
                data-group={g.title}
                data-open={isOpen}
                data-holds-active={holdsActive}
                onClick={() => setPicked({ tab: activeTab, title: g.title })}
                className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-3 text-xs font-black transition ${
                  isOpen
                    ? "border border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                    : "border border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                }`}
              >
                {g.title}
                <span className="text-xs font-bold opacity-70">{g.items.length}</span>
                {/* ★보조기술에도 「현재 여기」를 말한다 — 종전엔 aria-hidden 점 하나뿐이었다. */}
                {holdsActive && <span className="sr-only">현재 메뉴 포함</span>}
                {holdsActive && !isOpen && (
                  <span aria-hidden className="size-1.5 rounded-full bg-[var(--accent-strong)]" />
                )}
              </button>
            );
          })}
        </div>

        <span className="ml-auto text-xs font-bold text-[var(--text-tertiary)]">
          {tabs.length}개 메뉴 · 내 권한 기준
        </span>
      </div>

      {open && (
        <div id={panelId} role="tabpanel" aria-label={`${open.title} 메뉴`} className="sa-tabbar">
          {open.items.map((t) => (
            <button
              key={t.key}
              type="button"
              data-tab-key={t.key}
              aria-current={activeTab === t.key ? "page" : undefined}
              data-active={activeTab === t.key}
              onClick={() => onNavigate(t.key)}
              className="sa-tab"
            >
              {t.icon && (
                <span className="sa-tab__icon" aria-hidden>
                  <t.icon className="size-4" />
                </span>
              )}
              {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
