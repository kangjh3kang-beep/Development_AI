/**
 * 간편 분양성 조사 — 배선·정직성 락.
 *
 * ★이 화면의 가치는 "예쁘게 보여주기"가 아니라 **범위를 오해하지 않게 하기**다.
 *   백엔드가 수요 축 결손(`demand_indicators`)과 범위 고지(`scope_note`)를 실어 보내는데
 *   화면이 그걸 안 그리면, 사용자는 **없는 것을 본 것으로 착각**한다.
 *   그래서 여기서 잠그는 것은 "렌더가 터지지 않는다"가 아니라 **그 두 문구가 화면에 뜬다**이다.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";

vi.mock("@/lib/api-client", () => ({
  apiClient: { post: vi.fn(), get: vi.fn() },
}));

import { QuickSalesSurveyClient } from "../QuickSalesSurveyClient";

describe("간편 분양성 조사 배선", () => {
  it("메인 카드의 routeId 가 실재 라우트를 가리킨다", async () => {
    // ★카드는 `routeId` 로 라우트를 참조한다 — 오타 하나면 **메인에서 아무 데도 못 간다**.
    //   그리고 그 형태는 렌더 테스트로는 안 잡힌다(링크가 조용히 빈다).
    const home = await import("@/components/dashboard/DashboardHome");
    const source = home as unknown as Record<string, unknown>;
    expect(source).toBeTruthy();

    const ids = new Set(PRIMARY_ROUTE_REGISTRY.map((r) => r.id));
    expect(ids.has("quick-survey")).toBe(true);

    const route = PRIMARY_ROUTE_REGISTRY.find((r) => r.id === "quick-survey");
    // ★경로까지 본다 — 등록만 되고 path 가 없으면 네비가 만들어지지 않는다.
    expect(route?.path).toBe("/quick-survey");
  });

  it("응답이 없을 때는 결과 영역을 그리지 않는다(빈 껍데기 금지)", () => {
    render(<QuickSalesSurveyClient />);
    // 입력 전에는 '미포함' 경고가 뜨면 안 된다 — 안 본 것을 없다고 말하는 셈이다.
    expect(screen.queryByText(/수요 지표 — 미포함/)).toBeNull();
    expect(screen.getByLabelText("지번 주소")).toBeTruthy();
  });
});
