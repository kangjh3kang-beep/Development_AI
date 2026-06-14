import { expect, test } from "@playwright/test";
import { installReleaseHarness, RELEASE_PROJECT_ID } from "./support/release-harness";

/**
 * SP2-5 스모크: 좌측 "설계 참고 > 프로젝트 회의방" 랜딩 — 프로젝트 리스트가 뜨고 각 항목이
 * 해당 회의방(/projects/{id}/collaboration)으로 연결되는지(무크래시) 확인.
 *
 * useProjectStore.syncFromBackend는 GET /projects의 res.items를 읽으므로, 하니스 기본
 * 응답(res.projects) 대신 items 형태를 이 스펙에서 override(이후 등록 → 우선). tsc/build로
 * 안 잡히는 라우트·store 회귀 보호.
 */
test.describe("프로젝트 회의방 랜딩 스모크", () => {
  test("회의방 진입 → 프로젝트 리스트 → 회의방 링크 노출 무크래시", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(String(e?.message ?? e)));

    await installReleaseHarness(page);
    // store는 res.items를 읽음 → items 형태로 명시 override(GET /projects만).
    await page.route(
      (url) => url.pathname.endsWith("/projects"),
      (route) => {
        if (route.request().method() !== "GET") return route.fallback();
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [
              {
                id: RELEASE_PROJECT_ID,
                name: "테스트 회의방 프로젝트",
                address: "서울특별시 강남구 테헤란로 1",
                status: "design",
              },
            ],
          }),
        });
      },
    );

    await page.goto(`/en/meeting-rooms`);

    const root = page.getByTestId("meeting-rooms");
    await root.waitFor({ state: "visible", timeout: 45_000 });

    const link = page.getByTestId("meeting-room-link").first();
    await expect(link).toBeVisible({ timeout: 15_000 });
    await expect(link).toHaveAttribute(
      "href",
      `/en/projects/${RELEASE_PROJECT_ID}/collaboration`,
    );

    expect(pageErrors, `uncaught page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  });
});
