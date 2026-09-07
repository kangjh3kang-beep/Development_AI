import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FieldBottomNav, FieldDesktopNav, FieldMenuSheet } from "@/components/sales-app/FieldNav";
import {
  BOTTOM_NAV_KEYS,
  MENU_GROUPS,
  SALES_TABS,
  visibleTabs,
} from "@/components/sales-app/roleConfig";

/**
 * 모바일 하단탭바+전체메뉴 시트 계약 회귀(디자인 핸드오프 P0#2).
 *  ① 하단바 주 슬롯은 노출 탭과 교집합 — MEMBER(contracts 미보유)에 '수납' 슬롯 없음(고아 이동 금지)
 *  ② 전체메뉴 시트는 MENU_GROUPS×노출탭 교집합 — 빈 그룹 숨김, 이동 시 onNavigate+닫힘
 *  ③ '전체' 슬롯은 주 슬롯 밖 탭 활성 시 활성 표시
 * 게이팅은 roleConfig.visibleTabs 실물을 사용(모킹 없음 — SSOT 계약 그대로 검증).
 */

// 백엔드 _FEATURE_KEYS 기준 MEMBER features(주 사용자): dashboard·units·customers.
const MEMBER_TABS = visibleTabs(["dashboard", "units", "customers"]);
// 시행사(DEVELOPER) — 전 feature 보유.
const DEV_TABS = visibleTabs([
  "dashboard", "org", "pricing", "units", "contracts", "commission",
  "customers", "ads", "reports", "settings", "site_password",
]);

describe("모바일 도달성 불변식(IA SSOT)", () => {
  it("★BOTTOM_NAV_KEYS ∪ MENU_GROUPS ∪ {home} == SALES_TABS 전체 키(전단사) — 누락=모바일 도달불가 회귀", () => {
    const union = new Set<string>([
      ...BOTTOM_NAV_KEYS,
      ...MENU_GROUPS.flatMap((g) => g.keys),
      "home",
    ]);
    expect(union).toEqual(new Set(SALES_TABS.map((t) => t.key)));
  });
});

describe("FieldBottomNav 계약", () => {
  it("① MEMBER: 홈/고객/배치도 슬롯 + 전체 — '수납' 슬롯 없음(contracts 미보유)", () => {
    render(
      <FieldBottomNav tabs={MEMBER_TABS} activeTab="home" onNavigate={() => {}} onOpenMenu={() => {}} />,
    );
    expect(screen.getByText("홈")).toBeTruthy();
    expect(screen.getByText("고객")).toBeTruthy(); // '고객·상담' 축약
    expect(screen.getByText("세대")).toBeTruthy(); // '세대 배치도' 축약
    expect(screen.queryByText("수납")).toBeNull(); // ★고아 슬롯 금지
    expect(screen.getByText("전체")).toBeTruthy();
  });

  it("시행사: 수납 슬롯 포함 4주+전체, 슬롯 탭 시 onNavigate", () => {
    const nav = vi.fn();
    render(<FieldBottomNav tabs={DEV_TABS} activeTab="home" onNavigate={nav} onOpenMenu={() => {}} />);
    expect(screen.getByText("수납")).toBeTruthy();
    fireEvent.click(screen.getByText("수납"));
    expect(nav).toHaveBeenCalledWith("payments");
  });

  it("③ 주 슬롯 밖 탭(분양가) 활성 시 '전체' 슬롯이 활성 색", () => {
    render(
      <FieldBottomNav tabs={DEV_TABS} activeTab="pricing" onNavigate={() => {}} onOpenMenu={() => {}} />,
    );
    const all = screen.getByText("전체").closest("button");
    expect(all?.className).toContain("--accent-strong");
  });

  it("③-음성: 주 슬롯 탭(home) 활성이면 '전체' 슬롯 비활성(항상-활성 회귀 방지)", () => {
    render(
      <FieldBottomNav tabs={DEV_TABS} activeTab="home" onNavigate={() => {}} onOpenMenu={() => {}} />,
    );
    const all = screen.getByText("전체").closest("button");
    expect(all?.className).not.toContain("--accent-strong");
  });
});

describe("FieldMenuSheet 계약", () => {
  it("② MEMBER: Money 그룹 전체 숨김(수납/대출/전매/세금 모두 미노출)", () => {
    render(
      <FieldMenuSheet open tabs={MEMBER_TABS} activeTab="home" onNavigate={() => {}} onClose={() => {}} />,
    );
    expect(screen.queryByText("Money")).toBeNull(); // 빈 그룹 숨김
    expect(screen.getByText("Sales")).toBeTruthy(); // units·customers 있음
    expect(screen.queryByText("수납·납부")).toBeNull();
    expect(screen.getByText("업무일지")).toBeTruthy(); // alwaysOn → Operations 노출
  });

  it("이동 클릭 시 onNavigate(key) 후 onClose", () => {
    const nav = vi.fn();
    const close = vi.fn();
    render(<FieldMenuSheet open tabs={DEV_TABS} activeTab="home" onNavigate={nav} onClose={close} />);
    fireEvent.click(screen.getByText("분양가"));
    expect(nav).toHaveBeenCalledWith("pricing");
    expect(close).toHaveBeenCalled();
  });

  it("open=false 면 렌더하지 않음", () => {
    const { container } = render(
      <FieldMenuSheet open={false} tabs={DEV_TABS} activeTab="home" onNavigate={() => {}} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });
});

/**
 * ★L1·L2 — 데스크톱 그룹 레일(2026-09-07 신설).
 *
 * 이 자리를 태우는 락이 **0건**이었다. 그래서 P0 가 선언한 인지부하 해소가 모바일에만
 * 착지한 것을 아무 검사도 잡지 못했다. 두 모집단으로 건다:
 *   L1  그룹 소비 — 그룹 탭은 그 그룹에서 도달 ↔ 권한 밖 탭은 **어디에도 없다**
 *   L2  두 표면 IA 일치 — 같은 visibleTabs 로 렌더하면 **도달 가능한 키 집합이 같다**
 */

/** 데스크톱 레일에서 도달 가능한 탭 키 전수 — 그룹 칩을 모두 눌러 모은다(활성 그룹만 펼치므로). */
function desktopReachableKeys(tabs: typeof DEV_TABS): Set<string> {
  const seen = new Set<string>();
  const nav = vi.fn();
  const { container, unmount } = render(
    <FieldDesktopNav tabs={tabs} activeTab="home" onNavigate={nav} />,
  );
  // 고정 슬롯(어느 그룹에도 없는 탭) + 그룹 칩을 차례로 눌러 2줄에 뜬 탭을 수집.
  container.querySelectorAll<HTMLButtonElement>("[data-active]").forEach((b) => {
    const t = tabs.find((x) => x.label === b.textContent?.trim());
    if (t) seen.add(t.key);
  });
  const chips = Array.from(container.querySelectorAll<HTMLButtonElement>("[aria-expanded]"));
  for (const chip of chips) {
    fireEvent.click(chip);
    container.querySelectorAll<HTMLButtonElement>('[role="tab"]').forEach((b) => {
      const t = tabs.find((x) => x.label === b.textContent?.trim());
      if (t) seen.add(t.key);
    });
  }
  unmount();
  return seen;
}

/** 모바일에서 도달 가능한 탭 키 전수 — 하단 주 슬롯 ∪ 전체메뉴 시트. */
function mobileReachableKeys(tabs: typeof DEV_TABS): Set<string> {
  const seen = new Set<string>();
  const bottom = render(
    <FieldBottomNav tabs={tabs} activeTab="home" onNavigate={() => {}} onOpenMenu={() => {}} />,
  );
  for (const k of BOTTOM_NAV_KEYS) if (tabs.some((t) => t.key === k)) seen.add(k);
  bottom.unmount();
  const sheet = render(
    <FieldMenuSheet open tabs={tabs} activeTab="home" onNavigate={() => {}} onClose={() => {}} />,
  );
  sheet.container.querySelectorAll<HTMLButtonElement>("button").forEach((b) => {
    const t = tabs.find((x) => x.label === b.textContent?.trim());
    if (t) seen.add(t.key);
  });
  sheet.unmount();
  return seen;
}

describe("FieldDesktopNav 계약(L1) — 그룹을 소비한다", () => {
  it("★전 탭을 한 줄에 나열하지 않는다 — 최초 렌더의 role=tab 은 **활성 그룹 하나**뿐", () => {
    const { container } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab="home" onNavigate={() => {}} />,
    );
    const shown = container.querySelectorAll('[role="tab"]').length;
    // 공허한 그린 방지 — 대상이 0개여서 "나열 안 함"이 참이 되면 안 된다.
    expect(shown).toBeGreaterThan(0);
    expect(shown).toBeLessThan(DEV_TABS.length);
  });

  it("① 그룹 칩을 누르면 그 그룹의 탭이 뜬다(Money → 수납·납부)", () => {
    const nav = vi.fn();
    render(<FieldDesktopNav tabs={DEV_TABS} activeTab="home" onNavigate={nav} />);
    fireEvent.click(screen.getByRole("button", { name: /Money/ }));
    fireEvent.click(screen.getByRole("tab", { name: /수납·납부/ }));
    expect(nav).toHaveBeenCalledWith("payments");
  });

  it("② 권한 밖 탭은 **어느 그룹에서도** 도달할 수 없다 — MEMBER 에 '수납·납부' 없음", () => {
    const keys = desktopReachableKeys(MEMBER_TABS);
    expect(keys.has("payments")).toBe(false);
    // 두 모집단 — 권한 안 탭은 반드시 도달한다(검사기 생존).
    expect(keys.has("units")).toBe(true);
  });

  it("③ 빈 그룹은 칩 자체가 없다 — MEMBER 는 Money 그룹 미노출", () => {
    render(<FieldDesktopNav tabs={MEMBER_TABS} activeTab="home" onNavigate={() => {}} />);
    expect(screen.queryByRole("button", { name: /Money/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Sales/ })).toBeTruthy(); // 대조군
  });

  it("④ 고정 슬롯은 파생이다 — 어느 그룹에도 없는 '홈'이 그룹 칩과 함께 상시 노출", () => {
    render(<FieldDesktopNav tabs={DEV_TABS} activeTab="units" onNavigate={() => {}} />);
    expect(screen.getByRole("button", { name: /홈/ })).toBeTruthy();
  });
});

describe("★L2 — 데스크톱과 모바일이 같은 IA 를 쓴다(처방을 한쪽에만 적용 금지)", () => {
  it("시행사(DEV): 두 표면의 **도달 가능한 탭 키 집합이 같다**", () => {
    const d = desktopReachableKeys(DEV_TABS);
    const m = mobileReachableKeys(DEV_TABS);
    expect(d.size).toBeGreaterThan(0); // 공허한 그린 방지
    expect(d).toEqual(m);
    expect(d).toEqual(new Set(DEV_TABS.map((t) => t.key))); // 노출 탭 전수 도달
  });

  it("MEMBER(권한 제한): 두 표면이 **같이 줄어든다** — 한쪽만 새지 않는다", () => {
    const d = desktopReachableKeys(MEMBER_TABS);
    const m = mobileReachableKeys(MEMBER_TABS);
    expect(d).toEqual(m);
    // 두 모집단 — DEV 보다 확실히 작아야 한다(줄어들지 않으면 게이팅이 죽은 것).
    expect(d.size).toBeLessThan(DEV_TABS.length);
  });
});
