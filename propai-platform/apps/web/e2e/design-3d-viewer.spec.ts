import { expect, test } from "@playwright/test";
import { installReleaseHarness, RELEASE_PROJECT_ID } from "./support/release-harness";

/**
 * SP0 E4: CAD/BIM 3D 뷰어 인터랙션 스모크.
 *
 * 3D 뷰 전환 후 단면·측정·편집(gizmo) 토글이 크래시 없이 렌더·동작하는지 가드한다.
 * WebGL 픽셀은 환경편차가 커 픽셀 완전일치는 의도적으로 하지 않고(구조/스모크), 페이지
 * uncaught 에러 0과 토글 가시성·상호작용만 검증한다. tsc/build로 안 잡히는 R3F 회귀 보호.
 */
test.describe("CAD/BIM 3D 뷰어 스모크", () => {
  test("design-studio 3D 전환 → 단면·측정·편집 툴바 무크래시", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(String(e?.message ?? e)));

    await installReleaseHarness(page);
    // 프로젝트 컨텍스트 시드 — projectId + siteAnalysis(zoneCode)로 hasDesignBasis 충족.
    // persist 키 propai-project-context, version 1(불일치 시 migrate가 siteAnalysis를 정화하므로 일치 필수).
    await page.addInitScript((pid) => {
      localStorage.setItem(
        "propai-project-context",
        JSON.stringify({
          state: {
            projectId: pid,
            siteAnalysis: { landAreaSqm: 800, zoneCode: "2R" },
          },
          version: 1,
        }),
      );
    }, RELEASE_PROJECT_ID);

    await page.goto("/en/design-studio");

    // 2D/3D 세그먼트 칩 — 3D BIM 전환
    const to3D = page.getByTestId("cadbim-to-3d");
    await to3D.waitFor({ state: "visible", timeout: 45_000 });
    await to3D.click();

    // 3D 툴바 — spec 폴백으로 렌더되는 단면/측정/편집 토글 가시성
    const section = page.getByTestId("bim3d-section");
    const measure = page.getByTestId("bim3d-measure");
    const gizmo = page.getByTestId("bim3d-gizmo");
    await expect(section).toBeVisible({ timeout: 30_000 });
    await expect(measure).toBeVisible();
    await expect(gizmo).toBeVisible();

    // 토글 상호작용이 크래시 없이 동작(측정→편집→단면)
    await measure.click();
    await gizmo.click();
    await section.click();
    await page.waitForTimeout(400);

    expect(pageErrors, `uncaught page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  });
});
