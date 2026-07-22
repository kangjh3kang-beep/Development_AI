import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FieldBottomNav, FieldMenuSheet } from "@/components/sales-app/FieldNav";
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
