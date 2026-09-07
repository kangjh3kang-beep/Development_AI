import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FieldBottomNav, FieldDesktopNav, FieldMenuSheet } from "@/components/sales-app/FieldNav";
import {
  BOTTOM_NAV_KEYS,
  MENU_GROUPS,
  MENU_GROUP_MAX,
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
 * ★데스크톱 그룹 레일 계약(2026-09-07 · 적대 리뷰 반영본).
 *
 * 초판 락은 상한을 `shown < DEV_TABS.length` 로 걸었다가 **뚫렸다** — 그룹 밖 탭이 `home`
 * 하나뿐이라 여유가 **탭 1개**였고, 「모든 그룹을 한 줄에 펼치는」 변이가 `19 < 20` 으로
 * 통과했다(적대 리뷰가 `::VERDICT=SURVIVED` 로 실증). 그 변이가 **바로 사용자가 신고한
 * 나열식 회귀**다. 그래서 상한을 **활성 그룹 크기로 파생**시켜 못 박는다.
 *
 * 표면에서 탭 키를 읽을 때는 라벨이 아니라 `data-tab-key` 를 본다 — 하단바는 라벨을 축약해
 * 그리므로(첫 어절만) 라벨 역매핑은 **모바일 절반을 잴 수 없었다**(초판의 자기지시적 결함).
 */

/** 한 표면이 지금 화면에 그린 탭 키 — DOM 에서 읽는다(소스 파생 아님). */
function renderedKeys(root: ParentNode): string[] {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-tab-key]")).map(
    (el) => el.dataset.tabKey!,
  );
}

/** 데스크톱 레일에서 **도달 가능한** 탭 키 전수 — 그룹 칩을 모두 눌러 모은다. */
function desktopReachableKeys(tabs: typeof DEV_TABS): Set<string> {
  const seen = new Set<string>();
  const { container, unmount } = render(
    <FieldDesktopNav tabs={tabs} activeTab="home" onNavigate={() => {}} />,
  );
  renderedKeys(container).forEach((k) => seen.add(k));
  for (const chip of Array.from(container.querySelectorAll<HTMLButtonElement>('[data-group]'))) {
    fireEvent.click(chip);
    renderedKeys(container).forEach((k) => seen.add(k));
  }
  unmount();
  return seen;
}

/** 모바일에서 도달 가능한 탭 키 전수 — 하단 주 슬롯 ∪ 전체메뉴 시트. **둘 다 DOM 에서 읽는다.** */
function mobileReachableKeys(tabs: typeof DEV_TABS): Set<string> {
  const seen = new Set<string>();
  const bottom = render(
    <FieldBottomNav tabs={tabs} activeTab="home" onNavigate={() => {}} onOpenMenu={() => {}} />,
  );
  renderedKeys(bottom.container).forEach((k) => seen.add(k));
  bottom.unmount();
  const sheet = render(
    <FieldMenuSheet open tabs={tabs} activeTab="home" onNavigate={() => {}} onClose={() => {}} />,
  );
  renderedKeys(sheet.container).forEach((k) => seen.add(k));
  sheet.unmount();
  return seen;
}

describe("IA SSOT 상한(m4) — 「상단이 길어지지 않는다」가 참이려면 그룹당 상한이 있어야 한다", () => {
  it("★모든 그룹이 MENU_GROUP_MAX 이하다 — 넘으면 그룹을 쪼갠다", () => {
    expect(MENU_GROUPS.length).toBeGreaterThan(0); // 공허 방지
    for (const g of MENU_GROUPS) {
      expect(g.keys.length).toBeLessThanOrEqual(MENU_GROUP_MAX);
    }
    // 두 모집단 — 상한이 **실제로 빡빡한지** 확인(아무 값이나 넣은 상수가 아니다).
    expect(Math.max(...MENU_GROUPS.map((g) => g.keys.length))).toBe(MENU_GROUP_MAX);
  });

  it("★그룹 제목이 유일하다 — 제목이 그룹의 **신원**이기 때문이다(적대 리뷰 m5 권고)", () => {
    // `FieldDesktopNav` 는 `key={g.title}` 와 `find(g => g.title === openTitle)` 로 그룹을
    // 식별한다. 제목이 겹치면 React key 충돌 + 엉뚱한 그룹이 열린다.
    // 안정 id 도입은 SSOT 계약 변경이라 범위 밖으로 뒀고, **유일성만** 못 박는다.
    const titles = MENU_GROUPS.map((g) => g.title);
    expect(titles.length).toBeGreaterThan(1); // 공허 방지
    expect(new Set(titles).size).toBe(titles.length);
  });
});

describe("FieldDesktopNav 계약(L1) — 활성 그룹만 펼친다", () => {
  it("★★패널에는 **활성 그룹의 탭만** 있다 — 개수가 그룹 크기와 정확히 같다(전 탭 나열 회귀 차단)", () => {
    const { container } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab="home" onNavigate={() => {}} />,
    );
    const panel = container.querySelector('[role="tabpanel"]')!;
    expect(panel).toBeTruthy(); // 공허 방지 — 패널이 없으면 아래가 전부 무의미하다

    const shown = renderedKeys(panel);
    const openGroupTitle = container
      .querySelector<HTMLElement>('[data-group][data-open="true"]')!
      .dataset.group!;
    const expected = MENU_GROUPS.find((g) => g.title === openGroupTitle)!.keys.filter((k) =>
      DEV_TABS.some((t) => t.key === k),
    );

    // ★상한을 **활성 그룹 크기로 파생**시킨다. 초판은 전체 탭 수와 비교해 여유가 1개였다.
    expect(shown.sort()).toEqual(expected.sort());
    // 그리고 그 그룹 밖 탭은 패널에 **하나도** 없다.
    const outside = DEV_TABS.filter((t) => !expected.includes(t.key)).map((t) => t.key);
    expect(outside.length).toBeGreaterThan(0); // 대조군 — 비교 대상이 실재한다
    expect(shown.filter((k) => outside.includes(k))).toEqual([]);
  });

  it("① 그룹 칩을 누르면 그 그룹의 탭이 뜬다(Money → 수납·납부)", () => {
    const nav = vi.fn();
    render(<FieldDesktopNav tabs={DEV_TABS} activeTab="home" onNavigate={nav} />);
    fireEvent.click(screen.getByRole("tab", { name: /Money/ }));
    fireEvent.click(screen.getByRole("button", { name: /수납·납부/ }));
    expect(nav).toHaveBeenCalledWith("payments");
  });

  it("② 권한 밖 탭은 **어느 그룹에서도** 도달할 수 없다 — MEMBER 에 '수납·납부' 없음", () => {
    const keys = desktopReachableKeys(MEMBER_TABS);
    expect(keys.has("payments")).toBe(false);
    expect(keys.has("units")).toBe(true); // 대조군 — 권한 안 탭은 반드시 도달
  });

  it("③ 빈 그룹은 칩 자체가 없다 — MEMBER 는 Money 그룹 미노출", () => {
    render(<FieldDesktopNav tabs={MEMBER_TABS} activeTab="home" onNavigate={() => {}} />);
    expect(screen.queryByRole("tab", { name: /Money/ })).toBeNull();
    expect(screen.getByRole("tab", { name: /Sales/ })).toBeTruthy(); // 대조군
  });

  it("④ 고정 슬롯은 파생이다 — 어느 그룹에도 없는 '홈'이 상시 노출", () => {
    const { container } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab="units" onNavigate={() => {}} />,
    );
    expect(container.querySelector('[data-tab-key="home"]')).toBeTruthy();
  });

  it("★F3 데스크톱 전용 표면이다 — 루트가 sm+ 에서만 보인다(반응형 계약)", () => {
    // 적대 리뷰 실증: `sm:block` → `sm:hidden` 변이가 SURVIVED 했다 —
    // 이 PR 의 산출물이 **전 뷰포트에서 사라져도** 초록이었다. 이제 두 방향을 다 단언한다.
    const { container } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab="home" onNavigate={() => {}} />,
    );
    const cls = (container.firstElementChild as HTMLElement).className;
    expect(cls).toContain("hidden");   // 기본은 숨김
    expect(cls).toContain("sm:block"); // sm+ 에서만 보인다
    expect(cls).not.toContain("sm:hidden");
  });

  it("★R1 패널은 `sa-tabbar` 를 쓴다 — 셸의 W2 음성 단언이 이 이름을 표지로 삼는다", () => {
    // ★적대 리뷰가 이 자리를 반증했다: `sa-tabbar` → `sa-tab-bar` 로 바꿔도 초록이었다.
    //   그러면 셸의 `expect(code).not.toContain("sa-tabbar")` 가 **닻을 잃고**,
    //   셸이 새 이름으로 탭바를 다시 인라인해도 W2 가 탐지하지 못한다.
    //   ⇒ 표지가 사는 자리를 여기서 못 박는다(두 파일이 같은 문자열에 묶인다).
    const { container } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab="home" onNavigate={() => {}} />,
    );
    const panel = container.querySelector('[role="tabpanel"]');
    expect(panel).toBeTruthy(); // 공허 방지
    expect((panel as HTMLElement).className).toContain("sa-tabbar");
  });
});

describe("★M2·M3 — 상태가 어긋나도 화면이 무너지지 않는다", () => {
  it("M2 펼친 그룹이 사라지면 **활성 탭이 속한 그룹**으로 되돌아온다(첫 그룹이 아니라)", () => {
    // ★활성 탭을 **첫 그룹 밖**(Operations 의 worklog)에 둔다. 초판 락은 활성 탭이 Sales(=groups[0])
    //   에 있어서, 폴백이 `activeGroupTitle` 이든 `groups[0]` 이든 결과가 같았다 —
    //   그래서 `activeGroupTitle` 폴백을 지우는 변이가 **SURVIVED** 했다(실측).
    const ACTIVE = "worklog"; // Operations 그룹
    expect(MENU_GROUPS[0].keys).not.toContain(ACTIVE); // 대조군 — 첫 그룹이 아님을 못 박는다

    const { container, rerender } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab={ACTIVE} onNavigate={() => {}} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Money/ }));
    expect(renderedKeys(container.querySelector('[role="tabpanel"]')!)).toContain("payments"); // 전제

    // Money 그룹의 탭이 권한에서 빠진다(활성 탭은 그대로).
    const shrunk = DEV_TABS.filter((t) => !["payments", "loan", "resale", "tax"].includes(t.key));
    rerender(<FieldDesktopNav tabs={shrunk} activeTab={ACTIVE} onNavigate={() => {}} />);

    const panel = container.querySelector('[role="tabpanel"]');
    expect(panel).toBeTruthy(); // 초판은 여기서 통째로 증발했다
    // ★첫 그룹이 아니라 **활성 탭이 속한 그룹**이 펼쳐진다.
    expect(renderedKeys(panel!)).toContain(ACTIVE);
    expect(renderedKeys(panel!)).not.toContain(MENU_GROUPS[0].keys[0]);
  });

  it("M3 다른 그룹을 펼쳐도 **현재 위치가 보조기술에 남는다**(활성 그룹 칩이 aria-current)", () => {
    const { container } = render(
      <FieldDesktopNav tabs={DEV_TABS} activeTab="units" onNavigate={() => {}} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Money/ }));
    const current = container.querySelector('[data-group][aria-current="true"]');
    expect(current).toBeTruthy();
    expect((current as HTMLElement).dataset.group).toBe("Sales"); // units 가 속한 그룹
    expect(current!.textContent).toContain("현재 메뉴 포함"); // sr-only 문구
  });
});

describe("★L2 — 데스크톱과 모바일이 같은 IA 를 쓴다(처방을 한쪽에만 적용 금지)", () => {
  it("시행사(DEV): 두 표면의 **도달 가능한 탭 키 집합이 같다**", () => {
    const d = desktopReachableKeys(DEV_TABS);
    const m = mobileReachableKeys(DEV_TABS);
    expect(d.size).toBeGreaterThan(0); // 공허 방지
    expect(d).toEqual(m);
    expect(d).toEqual(new Set(DEV_TABS.map((t) => t.key))); // 노출 탭 전수 도달
  });

  it("MEMBER(권한 제한): 두 표면이 **같이 줄어든다** — 한쪽만 새지 않는다", () => {
    const d = desktopReachableKeys(MEMBER_TABS);
    const m = mobileReachableKeys(MEMBER_TABS);
    expect(d).toEqual(m);
    // ★절대 기준을 둔다 — 초판은 `d===m` 과 크기 비교뿐이라 **양쪽이 같은 키를 함께 흘리면**
    //   조용히 통과했다(적대 리뷰 m1).
    expect(d).toEqual(new Set(MEMBER_TABS.map((t) => t.key)));
    expect(d.size).toBeLessThan(DEV_TABS.length);
  });
});
