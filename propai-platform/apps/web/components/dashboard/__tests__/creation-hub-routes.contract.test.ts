/**
 * 생성 허브 카드 ↔ **실재하는 라우트** 정합 락.
 *
 * ★왜(2026-08-27): 「실거래 신고내역」은 기능·패널·백엔드가 모두 있었는데 **카드가 없어서**
 *   대시보드 안 데이터 패널로만 존재했다 — 라이브 실측 y≈2,921px(페이지 높이 4,256px)라
 *   스크롤 없이는 보이지 않아 *"생성허브에 안 나타난다"* 로 읽혔다.
 *   카드로 올리려면 **전용 라우트**가 필요한데 세 곳이 어긋날 수 있다:
 *   `creationProducts.routeId` ↔ `PRIMARY_ROUTE_REGISTRY.id` ↔ **디스크의 page.tsx**.
 *
 * ★형제 `ReportPanelSection.parity.test.tsx` 는 **랜딩** 카드만 레지스트리와 대조한다
 *   (`landing.filter(...)`) — **대시보드 카드는 그 검사 밖**이었고, 어느 락도 **페이지 파일이
 *   실제로 존재하는지**는 보지 않았다.
 *
 * ★독립 리뷰가 초판의 구멍 넷을 잡았다(전부 여기 반영):
 *   ①`routeId` 정규식이 **홑따옴표**를 못 잡아 카드가 8개로 세어졌다(하한 8과 결합해 위음성)
 *   ②**주석·문자열**의 `routeId:` 를 집었다(내가 카드 주석에 경로를 적었다)
 *   ③`[locale]` 밖의 `app/offline/page.tsx` 를 라우트로 세어 `/offline` 카드를 초록으로 통과시켰다
 *     (실제 `hrefFor` 는 `/ko/offline` 을 만들고 그건 404 다)
 *   ④**동적 세그먼트**(`[id]`)를 리터럴로 남겨, 프로젝트 스코프 카드가 생기면 **정상 코드를 막는다**
 *     — 형제 `__tests__/settings-routes-have-doors.test.ts` 가 그 함정을 **경고문으로 이미 적어 뒀다**
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import { PRIMARY_ROUTE_REGISTRY, type RouteRegistryItem } from "@/lib/navigation/route-registry";

const WEB_ROOT = join(__dirname, "..", "..", "..");
/** ★`[locale]` **아래만** 본다 — `app/offline` 처럼 밖에 있는 것은 `/ko/...` 로 못 간다. */
const LOCALE_ROOT = join(WEB_ROOT, "app", "[locale]");
const DASHBOARD_SRC = join(WEB_ROOT, "components/dashboard/DashboardHome.tsx");
const PAGE_FILE = /^page\.(tsx|ts|jsx|js|mjs)$/;

/** 카드의 `routeId` 를 **소스에서 파생**한다(주석·문자열 제거 후 · 따옴표 두 종류). */
const cardRouteIds = [
  ...__stripCommentsForScan(readFileSync(DASHBOARD_SRC, "utf8"), DASHBOARD_SRC).matchAll(
    /routeId:\s*["']([^"']+)["']/g,
  ),
].map((m) => m[1]);

/** `[locale]` 아래 실제 라우트 경로. `(group)`·`@slot`·`_private` 은 URL 에 안 나온다. */
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
      if (e === "node_modules" || e === "__tests__" || e.startsWith("_")) continue;
      const invisible = /^\(.*\)$/.test(e) || e.startsWith("@");
      routePathsOnDisk(p, invisible ? segs : [...segs, e], out);
    } else if (PAGE_FILE.test(e)) {
      out.add("/" + segs.join("/"));
    }
  }
  return out;
}

/** 동적 세그먼트를 와일드카드로 접는다 — `[id]`·`[...slug]` 를 리터럴로 두면 **정상 코드를 막는다**. */
const normalize = (p: string) => p.replace(/\[[^\]]+\]/g, "*");

const DISK_ROUTES = routePathsOnDisk(LOCALE_ROOT);
const DISK_PATTERNS = new Set([...DISK_ROUTES].map(normalize));
const routeOf = (id: string): RouteRegistryItem | undefined =>
  PRIMARY_ROUTE_REGISTRY.find((r) => r.id === id);

describe("생성 허브 카드 — 실재하는 라우트만 광고한다", () => {
  it("전제: 카드와 디스크 라우트를 실제로 찾았다(공허 진리 방지)", () => {
    // ★하한을 **실측값에 붙인다** — 여유를 크게 두면 절반이 사라져도 통과한다(초판 실수).
    expect(cardRouteIds.length, `카드 routeId 파생 실패: ${cardRouteIds}`).toBeGreaterThanOrEqual(9);
    expect(DISK_ROUTES.size, "디스크 라우트 수집 실패").toBeGreaterThan(40);
    // ★양성 대조군 — 반드시 있어야 하는 것이 같은 방법으로 조회된다.
    expect(DISK_ROUTES.has("/permits")).toBe(true);
    expect(cardRouteIds).toContain("realtx-report");
    // ★음성 대조군 — `[locale]` 밖의 것은 세지 않는다.
    expect(DISK_ROUTES.has("/offline")).toBe(false);
  });

  it("★모든 카드의 routeId 가 라우트 레지스트리에 실재한다", () => {
    const ids = new Set(PRIMARY_ROUTE_REGISTRY.map((r) => r.id));
    const dangling = cardRouteIds.filter((id) => !ids.has(id));
    // ★`hrefFor` 는 미해석 시 조용히 홈(`/${locale}`)으로 폴백한다 — 404 가 아니라 **오배송**이다.
    expect(dangling, `레지스트리에 없는 routeId — 홈으로 조용히 폴백된다: ${dangling}`).toEqual([]);
  });

  it("★모든 카드의 라우트에 **디스크의 page 파일**이 있다", () => {
    const missing = cardRouteIds
      .map(routeOf)
      .filter((r) => r && (!r.path || !DISK_PATTERNS.has(normalize(r.path))))
      .map((r) => `${r!.id}(${r!.path ?? "path 없음"})`);
    expect(missing, `카드가 **존재하지 않는 페이지**를 광고한다: ${missing}`).toEqual([]);
  });

  it("★(역) 카드가 `hidden` 라우트를 광고하지 않는다", () => {
    // ★공허 진리 가드: 레지스트리에 `hidden` 이 **0건**이면 이 단언은 원리적으로 깨질 수 없다.
    //   그래서 판별식을 **두 모집단**으로 먼저 태운다 — 술어가 살아 있음을 증명한 뒤 본단언한다.
    const isAdvertisableHidden = (r: RouteRegistryItem | undefined) => r?.status === "hidden";
    expect(isAdvertisableHidden({ status: "hidden" } as RouteRegistryItem)).toBe(true);
    expect(isAdvertisableHidden({ status: "live" } as RouteRegistryItem)).toBe(false);

    const advertised = cardRouteIds.map(routeOf).filter(isAdvertisableHidden).map((r) => r!.id);
    expect(advertised, `숨김 라우트를 카드로 광고한다: ${advertised}`).toEqual([]);
  });

  it("카드 routeId 에 중복이 없다(같은 곳으로 가는 카드 둘)", () => {
    const dupes = cardRouteIds.filter((id, i) => cardRouteIds.indexOf(id) !== i);
    expect([...new Set(dupes)]).toEqual([]);
  });

  it("★실거래 카드가 **토지에서 원천 불가한 것**을 광고하지 않는다", () => {
    /*
     * 이 패널은 `prop_type: "land"` 고정(`RealtxReportPanel.tsx:67,117`)인데 MOLIT **토지**
     * 응답 원문에는 `rgstDate`·`buyerGbn`·`slerGbn` 이 **없다**(원문 키 실측 land 16 / apt 32 ·
     * 대조군 `cdealType` 양쪽 존재 — `tasks/realtx_sync_task.py:88-108`). 집계는 그 필드가
     * 비면 세지 않으므로 **항상 0** 이다. 라이브 확인(2026-08-27 강남구 6개월):
     *   registered=0 · corporate_buyer=0 · corporate_seller=0
     *   cancelled=1 · direct=52 · brokered=9 · share_deals=45   ← 이 넷은 나온다
     * ★「0%」를 광고하면 사용자가 그것을 **관측**으로 읽는다 — 실제는 **원천 부재**다.
     */
    const src = __stripCommentsForScan(readFileSync(DASHBOARD_SRC, "utf8"), DASHBOARD_SRC);
    const block = src.slice(src.indexOf('routeId: "realtx-report"'));
    const card = block.slice(0, block.indexOf("},"));
    expect(card.length, "카드 블록을 못 잘랐다 — 파서가 죽었다").toBeGreaterThan(50);

    for (const term of ["등기", "법인"]) {
      expect(card.includes(term), `토지에서 항상 0 인 지표(${term})를 카드가 광고한다`).toBe(false);
    }
    // ★두 모집단 — 실제로 나오는 것은 **말해도 된다**(과잉 억제 방지: 전부 지우는 구현도 위 단언을 통과한다).
    expect(card.includes("해제"), "실측으로 나오는 지표까지 지웠다").toBe(true);
  });
});
