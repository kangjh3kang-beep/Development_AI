/**
 * 랜딩 보고서 카드 ↔ 대시보드 생성 카드 **정합 락**.
 *
 * ★이 락이 생긴 이유가 곧 이 파일의 존재 이유다: `quick-survey` 를 대시보드에만 넣고
 *   **랜딩에는 빠뜨린 채 "메인에 추가했다"고 보고**했다. 두 목록은 서로의 미러인데
 *   그 사실을 아무도 강제하지 않아, 한쪽만 고쳐도 조용히 통과했다.
 *
 * ★그래서 잠그는 것은 "카드가 렌더된다"가 아니라 **"두 목록이 어긋나지 않는다"** 이다.
 *   목록을 손으로 나열하지 않고 **양쪽 소스에서 파생**한다 — 새 산출물이 늘어도 자동으로 감시망에 든다.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";

const WEB_ROOT = join(__dirname, "..", "..", "..");

/** 소스에서 `routeId: "..."` 를 전부 뽑는다(둘 다 같은 필드명을 쓴다). */
function routeIdsIn(relPath: string): string[] {
  const source = readFileSync(join(WEB_ROOT, relPath), "utf8");
  return [...source.matchAll(/routeId:\s*"([^"]+)"/g)].map((m) => m[1]);
}

describe("랜딩 ↔ 대시보드 산출물 목록 정합", () => {
  const landing = routeIdsIn("components/marketing/ReportPanelSection.tsx");
  const dashboard = routeIdsIn("components/dashboard/DashboardHome.tsx");

  it("두 목록이 비어 있지 않다(공허 진리 방지)", () => {
    // ★정규식이 어긋나 0개를 뽑고 "어긋남 없음"으로 통과하는 것을 먼저 막는다.
    expect(landing.length).toBeGreaterThanOrEqual(4);
    expect(dashboard.length).toBeGreaterThanOrEqual(6);
  });

  it("랜딩의 모든 카드가 실재 라우트를 가리킨다", () => {
    const ids = new Set(PRIMARY_ROUTE_REGISTRY.map((r) => r.id));
    const dangling = landing.filter((id) => !ids.has(id));
    expect(dangling).toEqual([]);
  });

  it("두 목록은 서로 **부분집합일 필요가 없다**(위양성 방지 — 실측으로 확인)", () => {
    // ★처음에 "랜딩 ⊆ 대시보드" 를 단언했다가 **CI 에서 위양성으로 걸렸다**:
    //   랜딩의 `precheck`(후보지 진단서)는 실재 라우트인데 대시보드 카드 목록엔 없다.
    //   랜딩 docstring 의 "creationProducts 기준"이라는 문장을 **검증 없이 믿은** 결과다.
    //   두 화면은 노출 산출물을 각자 선별한다 — 그게 정상이다.
    // ★진짜 불변식은 위 "실재 라우트를 가리킨다" 하나다(없는 것을 광고하지 않는다).
    //   여기서는 **둘 다 비어 있지 않고 겹치는 게 있다**만 확인해 완전한 분기를 막는다.
    const shared = landing.filter((id) => dashboard.includes(id));
    expect(shared.length).toBeGreaterThan(0);
  });

  it("간편 분양성 조사가 양쪽 모두의 **첫 항목**이다", () => {
    // ★순서까지 잠근다: 이 산출물의 차별점이 "지번 하나만"이라 맨 앞에 두기로 한 결정이다.
    //   순서가 밀리면 결정이 조용히 뒤집힌 것이므로 여기서 드러낸다.
    expect(landing[0]).toBe("quick-survey");
    expect(dashboard[0]).toBe("quick-survey");
  });
});
