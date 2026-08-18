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
 * 이 저장소의 관리자 콘솔이 `/settings/*` 아래에 산다(실측). 다른 영역은 라우트 그룹·
 * 동적 세그먼트 때문에 경로→파일 매핑이 1:1 이 아니라, 넓히면 **위양성으로 정상 코드를
 * 막는다**(이 저장소가 두 번 겪은 형태). 그래서 매핑이 확실한 범위만 잠근다.
 * ★확인 못한 것: `/settings` 밖의 라우트는 여기서 검사하지 않는다.
 */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import { PRIMARY_ROUTE_REGISTRY } from "@/lib/navigation/route-registry";
import { NAV_ITEM_LABELS } from "@/lib/navigation/nav-i18n";

/** apps/web 기준 — vitest 는 apps/web 을 cwd 로 돈다. */
const WEB = resolve(process.cwd());
const APP_DIR = "app/[locale]/(dashboard)";

const settingsRoutes = PRIMARY_ROUTE_REGISTRY.filter((r) => r.path?.startsWith("/settings"));

describe("관리자 설정 라우트는 실제 페이지를 갖는다", () => {
  it("전제 — 검사 대상이 실제로 있다(공허 진리 방지)", () => {
    expect(settingsRoutes.length).toBeGreaterThanOrEqual(5);
  });

  it.each(settingsRoutes.map((r) => [r.id, r.path] as const))(
    "%s(%s) — page.tsx 가 존재한다",
    (_id, path) => {
      const file = resolve(WEB, `${APP_DIR}${path}/page.tsx`);
      expect(existsSync(file), `${path} 를 레지스트리가 선언했는데 페이지 파일이 없다: ${file}`).toBe(
        true,
      );
    },
  );
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
      expect(stripped.includes(dep), `${dep} 를 부르는 코드가 패널에 없다`).toBe(true);
    }
  });

  it("대조군 — 주석 스트립이 실제로 동작한다(검사기 생존 증명)", () => {
    const probe = `/* /growth/learning/candidates */\nconst x = 1;\n// /growth/learning/promote\n`;
    const stripped = __stripCommentsForScan(probe, "probe.ts");
    expect(stripped.includes("/growth/learning/candidates")).toBe(false);
    expect(stripped.includes("/growth/learning/promote")).toBe(false);
    expect(stripped.includes("const x = 1")).toBe(true);
  });
});
