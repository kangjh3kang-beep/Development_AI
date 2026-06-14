import { expect, test } from "@playwright/test";
import { installReleaseHarness, RELEASE_PROJECT_ID } from "./support/release-harness";

/**
 * SP1 스모크: 가상준공 3D 씬의 '준공 전/후' 토글이 크래시 없이 동작하는지.
 *
 * POST /digital-twin/scene를 building.glb_url 포함 payload로 목킹 → 씬 생성 → before/after
 * 세그먼트(dt-beforeafter) 노출·전환 무크래시 + pageerror 0 가드. WebGL 픽셀일치는 비검증
 * (구조/스모크, design-3d-viewer.spec.ts 규약). 항공/glb URL 404는 텍스처/메시 로드만 실패하고
 * 씬·토글 렌더에는 영향 없음(hasBuildingGlb는 glb_url 존재로만 판정).
 */
const SCENE = {
  ok: true,
  address: "서울특별시 강남구 테스트로 1",
  lat0: 37.5,
  lon0: 127.0,
  parcel: { ring_enu: [[0, 0], [20, 0], [20, 15], [0, 15]], center_enu: [10, 7.5] },
  aerial: {
    image_proxy_url: "/api/v1/digital-twin/aerial-image?lat=37.5&lon=127.0&zoom=18&size=512",
    center: [127.0, 37.5],
    zoom: 18,
    cover_m: 200,
  },
  building: { glb_url: "/e2e-dummy.glb", place_at_enu: [10, 0, 7.5] },
  badges: {
    terrain_source: "SRTM",
    terrain_resolution_m: 30,
    confidence: 0.6,
    neighbors_estimated: true,
    note: "AI 절차생성·인허가 아님",
  },
  sources: ["VWorld"],
};

test.describe("가상준공 3D — 준공 전/후 토글 스모크", () => {
  test("씬 생성 → before/after 세그먼트 무크래시", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(String(e?.message ?? e)));

    await installReleaseHarness(page);
    // scene 목킹(base 경로 무관 매칭) — building.glb_url 포함이라 준공 전/후 토글 노출 조건 충족
    await page.route("**/digital-twin/scene", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(SCENE) }),
    );
    // 프로젝트 컨텍스트 시드 — projectId===id(isBound) + siteAnalysis.address → result 단계 자동진입
    // (그래야 DigitalTwinScene 렌더). persist version 1 일치 필수(불일치 시 migrate가 정화).
    await page.addInitScript((pid) => {
      localStorage.setItem(
        "propai-project-context",
        JSON.stringify({
          state: {
            projectId: pid,
            siteAnalysis: { address: "서울특별시 강남구 테스트로 1", landAreaSqm: 800, zoneCode: "2R" },
          },
          version: 1,
        }),
      );
    }, RELEASE_PROJECT_ID);

    await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/site-analysis`);

    const addr = page.getByPlaceholder("예) 서울특별시 강남구 …");
    await addr.waitFor({ state: "visible", timeout: 45_000 });
    await addr.fill("서울특별시 강남구 테스트로 1");
    await page.getByRole("button", { name: "가상준공 생성" }).click();

    // 준공 전/후 세그먼트(payload.building.glb_url → hasBuildingGlb) 노출·전환
    const seg = page.getByTestId("dt-beforeafter");
    await expect(seg).toBeVisible({ timeout: 20_000 });
    await page.getByTestId("dt-before").click();
    await page.getByTestId("dt-after").click();
    await page.waitForTimeout(300);

    expect(pageErrors, `uncaught page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  });
});
