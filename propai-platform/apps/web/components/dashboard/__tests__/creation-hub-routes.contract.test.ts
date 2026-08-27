/**
 * 생성 허브 카드 ↔ **실재하는 라우트** 정합 락.
 *
 * ★왜(2026-08-27): 「실거래 신고내역」은 기능·패널·백엔드가 모두 있었는데 **카드가 없어서**
 *   대시보드 안 데이터 패널로만 존재했다 — 라이브 실측 y≈2,921px(페이지 높이 4,256px)라
 *   스크롤 없이는 보이지 않아 *"생성허브에 안 나타난다"* 로 읽혔다.
 *   카드로 올리려면 **전용 라우트**가 필요한데, 그 사이에 세 곳이 어긋날 수 있다:
 *   `creationProducts.routeId` ↔ `PRIMARY_ROUTE_REGISTRY.id` ↔ **디스크의 page.tsx**.
 *
 * ★형제 `ReportPanelSection.parity.test.tsx` 는 **랜딩** 카드가 실재 라우트를 가리키는지만 본다
 *   (`landing.filter(...)`). **대시보드 카드는 그 검사 밖**이었고, 어느 락도 **파일이 실제로
 *   존재하는지**는 보지 않았다 — 레지스트리에 id 만 넣고 페이지를 안 만들어도 초록이었다.
 *
 * ★목록을 손으로 나열하지 않는다. 세 축 모두 **파생**한다 — 새 카드는 자동으로 감시망에 든다.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";

const WEB_ROOT = join(__dirname, "..", "..", "..");
const APP = join(WEB_ROOT, "app");

/** 대시보드 카드의 `routeId` 를 **소스에서 파생**한다(형제 파리티 락과 같은 방식). */
const cardRouteIds = [
  ...readFileSync(join(WEB_ROOT, "components/dashboard/DashboardHome.tsx"), "utf8").matchAll(
    /routeId:\s*"([^"]+)"/g,
  ),
].map((m) => m[1]);

/**
 * `app/` 트리에서 **실제 라우트 경로**를 파생한다.
 * `[locale]` 과 `(group)` 세그먼트는 URL 에 나타나지 않으므로 제거한다.
 */
function routePathsOnDisk(dir: string, segs: string[] = [], out = new Set<string>()): Set<string> {
  let entries: string[] = [];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) {
      if (e === "node_modules" || e === "__tests__") continue;
      // `[locale]` · `(dashboard)` 같은 세그먼트는 URL 에 안 나온다.
      const hidden = /^\(.*\)$/.test(e) || e === "[locale]";
      routePathsOnDisk(p, hidden ? segs : [...segs, e], out);
    } else if (e === "page.tsx" || e === "page.ts") {
      out.add("/" + segs.join("/"));
    }
  }
  return out;
}

const DISK_ROUTES = routePathsOnDisk(APP);

describe("생성 허브 카드 — 실재하는 라우트만 광고한다", () => {
  it("전제: 카드와 디스크 라우트를 실제로 찾았다(공허 진리 방지)", () => {
    expect(cardRouteIds.length, "카드 routeId 를 못 뽑았다 — 정규식이 죽었다").toBeGreaterThanOrEqual(8);
    expect(DISK_ROUTES.size, "디스크에서 라우트를 못 찾았다 — 수집기가 죽었다").toBeGreaterThan(20);
    // ★양성 대조군: 반드시 있어야 하는 것이 같은 방법으로 조회된다.
    expect(DISK_ROUTES.has("/permits")).toBe(true);
  });

  it("★모든 카드의 routeId 가 라우트 레지스트리에 실재한다", () => {
    const ids = new Set(PRIMARY_ROUTE_REGISTRY.map((r) => r.id));
    const dangling = cardRouteIds.filter((id) => !ids.has(id));
    expect(dangling, `레지스트리에 없는 routeId — 링크가 어디로도 못 간다: ${dangling}`).toEqual([]);
  });

  it("★모든 카드의 라우트에 **디스크의 page 파일**이 있다", () => {
    // 「레지스트리에 id 가 있다」와 「그 페이지가 실재한다」는 **다른 명제**다.
    const missing = cardRouteIds
      .map((id) => PRIMARY_ROUTE_REGISTRY.find((r) => r.id === id))
      .filter((r) => r && (!r.path || !DISK_ROUTES.has(r.path)))
      .map((r) => `${r!.id}(${r!.path ?? "path 없음"})`);
    expect(
      missing,
      `카드가 **존재하지 않는 페이지**를 광고한다 — 클릭하면 404 다: ${missing}`,
    ).toEqual([]);
  });

  it("★(역) 카드가 `hidden` 라우트를 광고하지 않는다", () => {
    // 의도적으로 숨긴 것을 메인에서 광고하면 그 결정이 조용히 뒤집힌 것이다.
    const advertised = cardRouteIds
      .map((id) => PRIMARY_ROUTE_REGISTRY.find((r) => r.id === id))
      .filter((r) => r?.status === "hidden")
      .map((r) => r!.id);
    expect(advertised, `숨김 라우트를 카드로 광고한다: ${advertised}`).toEqual([]);
  });

  it("카드 routeId 에 중복이 없다(같은 곳으로 가는 카드 둘)", () => {
    const dupes = cardRouteIds.filter((id, i) => cardRouteIds.indexOf(id) !== i);
    expect([...new Set(dupes)]).toEqual([]);
  });
});
