import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DashboardPage from "../page";

// 대시보드 홈은 현재 사전(getDictionary) 없이 한국어 정적 카피를 직접 렌더하며,
// 진행단계/KPI/프로젝트 데이터는 클라이언트 로더(useEffect+apiClient)가 비동기로 채운다.
// 따라서 이 테스트는 서버 컴포넌트가 동기적으로 확정 렌더하는 핵심 진입 동선
// (히어로 카피 + 실제 내비게이션 목적지)을 검증한다.
describe("Dashboard home navigation", () => {
  it("renders the hero entry links and real overview navigation destinations", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    // 히어로 헤드라인/서브카피 — 사용자가 처음 보는 핵심 가치제안.
    expect(
      screen.getByRole("heading", {
        name: "개발사업의 필수 플랫폼! 주소만 입력하면, 시장조사·사업성·수지 분석을 한 번에.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("부동산 개발 분석")).toBeInTheDocument();

    // 핵심 행동(accent) — 프로젝트 생성 진입 동선이 /en/projects/new 로 연결된다.
    // "프로젝트 생성" 라벨은 히어로 + 빈상태 로더에 중복 등장하므로 href로 식별한다.
    const allLinks = screen.getAllByRole("link");
    const newProjectLinks = allLinks.filter(
      (link) => link.getAttribute("href") === "/en/projects/new",
    );
    expect(newProjectLinks.length).toBeGreaterThan(0);

    // 이용 가이드 진입 동선.
    expect(allLinks.some((link) => link.getAttribute("href") === "/en/guide")).toBe(true);
  });

  it("renders the active pipeline section and real card destinations", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    // 활성 진행 단계 섹션 헤더(실시간 모니터링 진입점).
    expect(screen.getByText("활성 진행 단계")).toBeInTheDocument();

    // 섹션 우상단 "전체 보기" → 프로젝트 목록(/en/projects).
    expect(screen.getByRole("link", { name: "전체 보기" })).toHaveAttribute(
      "href",
      "/en/projects",
    );

    // 사이드바 규제 동향 → 규제 분석(/en/regulations) 진입.
    expect(screen.getByRole("link", { name: "규제 분석 열기 →" })).toHaveAttribute(
      "href",
      "/en/regulations",
    );
  });
});
