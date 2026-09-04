/**
 * 관리자 설정 화면 — **선언한 문이 실제로 열리는가**(2026-08-19).
 *
 * 【일반화한 결함】
 * 이번에 고친 것은 "사람이 승인해야만 도는 게이트인데 사람에게 문이 없다"였다
 * (자가학습 few-shot: candidate 로만 쌓이고, 활성화 API 를 부르는 화면이 0개였다).
 * 이 형태는 두 방향으로 다시 생길 수 있다:
 *   ① 라우트 레지스트리에 경로를 선언했는데 **그 경로에 페이지 파일이 없다** → 눌러도 404.
 *   ② 페이지가 선언한 `apiDependencies` 를 **아무도 부르지 않는다** → 화면은 있는데 죽어 있다.
 * 여기서 ①을, 같은 폴더의 `components/settings/__tests__/LearningApprovalPanel.wiring.test.tsx`
 * 가 ②를 (렌더·클릭으로) 잠근다.
 *
 * 【목록형이 아니라 파생형】
 * 사람이 센 목록을 쓰지 않는다. `PRIMARY_ROUTE_REGISTRY` 에서 `/settings/*` 항목을
 * **파생**하므로 앞으로 추가되는 관리자 화면이 자동으로 이 검사망에 들어온다.
 *
 * 【범위를 왜 /settings 로 좁혔나 — 정직하게】
 * 이 저장소의 관리자 콘솔이 `/settings/*` 아래에 산다(실측). 다른 영역은 동적 세그먼트
 * (`[id]`) 때문에 레지스트리 경로와 파일 경로가 1:1 이 아니라, 넓히면 **위양성으로 정상
 * 코드를 막는다**(이 저장소가 두 번 겪은 형태). 그래서 매핑이 확실한 범위만 잠근다.
 * ★확인 못한 것: `/settings` 밖의 라우트는 여기서 검사하지 않는다.
 *
 * 【위양성을 구조적으로 없앤 방법 — 문자열 조립이 아니라 탐색(2026-08-19 적대리뷰)】
 * 처음엔 `app/[locale]/(dashboard)<path>/page.tsx` 로 **경로를 조립**해 존재를 봤다.
 * 그러면 `/settings` **안쪽**에 Next 라우트 그룹을 쓰는 순간(`settings/(gated)/x/page.tsx`
 * — URL 은 동일) 정상 코드가 빨강이 되고, `page.js`/`page.jsx` 도 못 본다.
 * 가드의 위양성도 결함이다(CLAUDE.md A.6). 그래서 지금은 **파일 트리를 걸어** 각
 * `page.*` 의 **URL 경로**를 계산한다 — 라우트 그룹 `(...)`·비공개 폴더 `_x`·병렬 슬롯
 * `@x` 를 Next 규칙대로 접고, 확장자도 전부 인정한다.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";
import { NAV_ITEM_LABELS } from "@/lib/navigation/nav-i18n";

// ── 저장소 전수 스캔 테스트의 시간 상한 ──────────────────────────────────────
//  이 파일은 `it` 안에서 저장소의 **모든 소스 파일(약 941개)** 을 다시 읽는다. 그래서 실행
//  시간이 **검증 대상의 성질이 아니라 그때의 CPU 경합**에 좌우된다 — 전체 스위트를 돌리면
//  워커가 붙는 만큼 느려져 기본 10초를 넘고, 단독 실행은 항상 통과한다(실측: 실패는 전부
//  `Test timed out in 10000ms` 이고 비타임아웃 실패는 0건). CI 는 더 느릴 수 있다.
//  ★10초는 **정확성 경계가 아니라 벽시계**다. 늘려도 잡아내는 결함은 그대로다.
//  ★근본 처방은 941파일 읽기를 모듈 스코프로 호이스팅하는 것이고, 별건으로 남겼다.
vi.setConfig({ testTimeout: 60_000 });


/** apps/web 기준 — vitest 는 apps/web 을 cwd 로 돈다. */
const WEB = resolve(process.cwd());
const APP_DIR = "app/[locale]/(dashboard)";

const settingsRoutes = PRIMARY_ROUTE_REGISTRY.filter((r) => r.path?.startsWith("/settings"));

const PAGE_FILE = /^page\.(tsx|ts|jsx|js|mjs)$/;

/**
 * `app/[locale]/(dashboard)` 아래 모든 `page.*` 의 **URL 경로**를 모은다.
 * Next 규칙: `(그룹)` 은 URL 에서 사라지고, `_비공개` 폴더와 `@슬롯` 은 라우트가 아니다.
 */
function discoverPageUrlPaths(root: string): Set<string> {
  const found = new Set<string>();
  const walk = (dir: string, url: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        const name = entry.name;
        if (name.startsWith("_") || name.startsWith("@") || name === "node_modules") continue;
        const isGroup = name.startsWith("(") && name.endsWith(")");
        walk(join(dir, name), isGroup ? url : `${url}/${name}`);
      } else if (PAGE_FILE.test(entry.name)) {
        found.add(url || "/");
      }
    }
  };
  walk(root, "");
  return found;
}

const PAGE_URLS = discoverPageUrlPaths(resolve(WEB, APP_DIR));

describe("관리자 설정 라우트는 실제 페이지를 갖는다", () => {
  it("전제 — 검사 대상과 탐색 결과가 실제로 있다(공허 진리 방지)", () => {
    expect(settingsRoutes.length).toBeGreaterThanOrEqual(5);
    // 탐색기가 죽으면 PAGE_URLS 가 비고 아래 단언이 전부 빨강이 된다 — 여기서 먼저 말한다.
    expect(PAGE_URLS.size, "페이지 탐색 결과가 비었다 — 탐색기가 죽었다").toBeGreaterThan(20);
    expect(existsSync(resolve(WEB, APP_DIR))).toBe(true);
  });

  it.each(settingsRoutes.map((r) => [r.id, r.path] as const))(
    "%s(%s) — 그 URL 로 열리는 page 파일이 실재한다",
    (_id, path) => {
      expect(
        PAGE_URLS.has(path as string),
        `${path} 를 레지스트리가 선언했는데 그 URL 의 page 파일이 없다`,
      ).toBe(true);
    },
  );

  it("대조군 — 없는 경로는 탐색 결과에도 없다(검사기 생존)", () => {
    expect(PAGE_URLS.has("/settings/__없는화면__")).toBe(false);
  });
});

describe("AI 학습 사례 승인 — 승인 게이트의 문이 선언대로 있다", () => {
  const route = PRIMARY_ROUTE_REGISTRY.find((r) => r.id === "learning-approval");

  it("레지스트리에 총괄관리자 전용으로 등록돼 있다", () => {
    expect(route, "learning-approval 항목이 레지스트리에 없다").toBeTruthy();
    expect(route?.path).toBe("/settings/learning");
    expect(route?.sectionId).toBe("admin");
    expect(route?.adminOnly).toBe(true);
    expect(route?.status).toBe("live");
  });

  it("한국어 원문 라벨이 있다(레지스트리 label 이 ko 폴백이다)", () => {
    expect(route?.label).toBeTruthy();
    expect(route?.label).toMatch(/[가-힣]/);
  });

  it("영어·중국어 라벨이 있다(내비게이션 i18n 누락 재발 방지)", () => {
    expect(NAV_ITEM_LABELS["learning-approval"]?.en).toBeTruthy();
    expect(NAV_ITEM_LABELS["learning-approval"]?.["zh-CN"]).toBeTruthy();
  });

  it("선언한 API 세 개가 승인 패널의 **실행되는 코드**에 있다", () => {
    // ★소스를 볼 때는 주석·JSDoc 을 먼저 지운다 — 이 저장소는 "주석 처리 + 임포트 유지"
    //   변이로 소스 검사가 두 번 뚫렸다(CLAUDE.md §A.3). 이 파일 상단 설명문에도 같은
    //   경로 문자열이 적혀 있어, 스트립이 없으면 이 검사는 **자기 주석에 속는다**.
    const file = resolve(WEB, "components/settings/LearningApprovalPanel.tsx");
    expect(existsSync(file)).toBe(true);
    const stripped = __stripCommentsForScan(readFileSync(file, "utf-8"), file);

    const deps = route?.apiDependencies ?? [];
    expect(deps.length, "apiDependencies 가 비었다 — 검사가 공허해진다").toBe(3);
    for (const dep of deps) {
      // ★부분문자열이 아니라 **경로 끝을 앵커**한다(적대리뷰 M1b). `includes` 로 보면
      //   `/candidates` → `/candidatesX` 접미 오타가 통과한다 — 프로덕션에서는 404 다.
      //   경로 뒤에 올 수 있는 것은 `?`·따옴표·백틱 등 비식별자 문자뿐이다.
      const anchored = new RegExp(
        `${dep.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![A-Za-z0-9_-])`,
      );
      expect(anchored.test(stripped), `${dep} 를 부르는 코드가 패널에 없다`).toBe(true);
    }
  });

  it("대조군 — 접미가 붙은 경로는 앵커 검사를 통과하지 못한다(검사기 생존)", () => {
    const anchored = new RegExp("/growth/learning/candidates(?![A-Za-z0-9_-])");
    expect(anchored.test('apiClient.get("/growth/learning/candidates?x=1")')).toBe(true);
    expect(anchored.test('apiClient.get("/growth/learning/candidatesX?x=1")')).toBe(false);
  });

  it("대조군 — 주석 스트립이 실제로 동작한다(검사기 생존 증명)", () => {
    const probe = `/* /growth/learning/candidates */\nconst x = 1;\n// /growth/learning/promote\n`;
    const stripped = __stripCommentsForScan(probe, "probe.ts");
    expect(stripped.includes("/growth/learning/candidates")).toBe(false);
    expect(stripped.includes("/growth/learning/promote")).toBe(false);
    expect(stripped.includes("const x = 1")).toBe(true);
  });
});
