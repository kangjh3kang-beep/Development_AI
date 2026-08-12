/**
 * 라이프사이클 레일의 **SSR/클라 하이드레이션 일치** 계약.
 *
 * ★왜 필요한가 — `LifecycleProgressRail` 은 진행도(`{완료}/{전체} · {pct}%`)를
 *   **persist 저장소(zustand + localStorage)** 에서 파생한다. 서버에는 그 저장소가 없으므로
 *   SSR 은 `0`, 클라이언트는 재수화 후 `1` 을 그려 **하이드레이션 불일치**가 났다:
 *
 *     <span className="shrink-0 r...">
 *   +   1        ← 클라이언트
 *   -   0        ← 서버
 *
 *   React 는 그 서브트리를 **버리고 다시 그리며** uncaught error 를 던진다. 실제로
 *   `digital-twin-scene.spec.ts` 가 "무크래시" 단언에서 이걸로 붉었고, 원인이 3D 와 무관해
 *   그 스펙만 봐서는 진단이 되지 않았다 — 그래서 **원인 자리에** 잠금을 따로 둔다.
 *
 * ★재현 조건은 특별한 게 아니다: **저장된 프로젝트 컨텍스트가 있는 재방문 사용자**면 걸린다.
 *   아래 시드는 그 상태를 그대로 만든 것이다.
 */
import { expect, test } from "@playwright/test";

import { installReleaseHarness, RELEASE_PROJECT_ID } from "./support/release-harness";

const SEEDED_CONTEXT = {
  state: {
    projectId: RELEASE_PROJECT_ID,
    siteAnalysis: {
      address: "서울특별시 강남구 테스트로 1",
      landAreaSqm: 800,
      zoneCode: "2R",
    },
  },
  version: 1,
};

test.describe("라이프사이클 레일 — 하이드레이션 일치", () => {
  test("★저장된 프로젝트 컨텍스트가 있어도 하이드레이션 불일치가 없다", async ({ page }) => {
    const hydrationErrors: string[] = [];
    page.on("pageerror", (e) => {
      const msg = String((e as Error)?.message ?? e);
      if (/Hydration failed|hydration/i.test(msg)) hydrationErrors.push(msg.split("\n")[0]);
    });

    await installReleaseHarness(page);
    await page.addInitScript((ctx) => {
      localStorage.setItem("propai-project-context", JSON.stringify(ctx));
    }, SEEDED_CONTEXT);

    await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/site-analysis`);

    // ★전제 — 레일이 실제로 렌더되고, **불일치를 유발하는 상태**(완료 1건 이상)여야 한다.
    //   이걸 먼저 단언하지 않으면 "레일이 안 떠서 오류도 없음"인 공허한 통과가 된다.
    const rail = page.getByLabel("프로젝트 라이프사이클 진행 현황");
    await expect(rail, "레일이 렌더되지 않았다 — 이 검사는 공허해진다").toBeVisible({ timeout: 45_000 });
    const badge = rail.locator("header span").last();
    await expect(badge, "진행도 배지를 찾지 못했다").toBeVisible();
    await expect
      .poll(async () => Number(/^(\d+)\//.exec((await badge.innerText()).trim())?.[1] ?? 0), {
        timeout: 20_000,
        message: "완료 0건이면 서버·클라가 같은 값이라 불일치가 나올 수 없다 — 시드가 먹지 않았다",
      })
      .toBeGreaterThan(0);

    expect(
      hydrationErrors,
      `하이드레이션 불일치가 발생했다 — 서버와 클라가 다른 값을 그린다:\n${hydrationErrors.join("\n")}`,
    ).toEqual([]);
  });
});
