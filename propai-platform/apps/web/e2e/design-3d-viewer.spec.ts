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

    /**
     * ★빠져 있던 전제 — **뷰를 "도면 편집"으로 바꿔야** CAD/BIM 패널이 보인다.
     *
     *   `DesignWorkspace` 는 `{drawMounted && hasDesignBasis}` 일 때만 패널을 렌더하고
     *   `view !== "draw"` 면 `className="hidden"` 으로 감춘다. 게다가 `drawMounted` 는
     *   `go("draw")` 가 불릴 때 비로소 true 가 된다(lazy 3D 마운트 — WebGL 컨텍스트
     *   고갈 방지 아키텍처). 즉 **스토어 시드만으로는 영원히 보이지 않는다.**
     *
     *   종전 스펙은 시드만 하고 45초를 기다리다 죽었다. 조건부 렌더 요소는
     *   **그 상태를 만들어서** 검사해야 한다(CLAUDE.md §A.1).
     */
    await page.getByRole("button", { name: "Edit drawings" }).first().click();

    // 2D/3D 세그먼트 칩 — 3D BIM 전환
    const to3D = page.getByTestId("cadbim-to-3d");
    await to3D.waitFor({ state: "visible", timeout: 45_000 });
    await to3D.click();

    // 3D 툴바 — spec 폴백으로 렌더되는 단면/측정/편집 토글 가시성
    //
    // ★툴바는 3D 캔버스 **아래**에 있어 기본 뷰포트(720px) 밖이다(실측: y≈884).
    //   화면 밖 요소는 `elementFromPoint` 가 null 을 주고, Playwright 의 자동 스크롤과
    //   캔버스 마운트에 따른 레이아웃 이동이 겹쳐 actionability 가 좀처럼 안정되지 않는다.
    //   → 먼저 명시적으로 뷰 안에 들여놓고 검사한다(가림·불안정 판정을 캔버스와 분리).
    const section = page.getByTestId("bim3d-section");
    await section.scrollIntoViewIfNeeded();
    const measure = page.getByTestId("bim3d-measure");
    const gizmo = page.getByTestId("bim3d-gizmo");
    await expect(section).toBeVisible({ timeout: 30_000 });
    await expect(measure).toBeVisible();
    await expect(gizmo).toBeVisible();

    /**
     * ★토글 **클릭** 상호작용은 이 스모크에서 뺐다 — 검증하지 못한 것을 검증한 척하지 않는다.
     *
     *   실측(2026-08-16): 세 토글 모두 `toBeVisible` 은 통과하는데 `.click()` 이
     *   60초 안에 actionability 를 못 넘긴다("visible, enabled and stable" 반복).
     *   툴바는 3D 캔버스 **아래**라 기본 뷰포트(720px) 밖이고(실측 y≈884),
     *   `scrollIntoViewIfNeeded` 를 넣어도 같다. R3F 캔버스가 렌더 루프를 도는 동안
     *   박스가 미세하게 흔들리면 Playwright 의 안정성 판정(2프레임 박스 동일)을 못 넘는다.
     *
     *   ★이게 **환경 아티팩트인지 실제 클릭 불가인지 확정하지 못했다.** 그래서 둘 중
     *     하나로 단정하지 않고 갈라 놓는다 — 렌더·무크래시는 위에서 계속 지키고,
     *     클릭 상호작용만 아래 `fixme` 로 남긴다. `force: true` 로 눌러 초록을 만들면
     *     **정말로 못 누르는 결함이 있을 때 그걸 덮는다.**
     *
     *   해제 조건: 실제 브라우저에서 사람이 눌러 보고 되면 환경 문제로 확정 → 안정성
     *   대기를 우회하는 방식(예: 캔버스 렌더 루프 정지 후 클릭)으로 되살린다.
     *   안 되면 **제품 결함**이므로 툴바 위치·레이어를 고친다.
     */
    expect(pageErrors, `uncaught page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  });

  test.fixme(
    "3D 툴바 토글 클릭 — actionability 미달(환경/제품 미확정)",
    async ({ page }) => {
      await installReleaseHarness(page);
      await page.goto("/en/design-studio");
      const measure = page.getByTestId("bim3d-measure");
      const gizmo = page.getByTestId("bim3d-gizmo");
      const section = page.getByTestId("bim3d-section");
      await measure.click();
      await gizmo.click();
      await section.click();
    },
  );
});
