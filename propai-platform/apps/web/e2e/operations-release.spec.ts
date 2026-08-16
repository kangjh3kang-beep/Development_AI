import { expect, test } from "@playwright/test";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";

test("maintenance, tenant, and digital twin routes stay executable", async ({
  page,
}) => {
  await installReleaseHarness(page);

  /**
   * ★이 화면의 "분석"은 **서버를 부르지 않는다** — 폼 입력값으로 브라우저에서 산술한다
   *   (`OperationsIntelligenceWorkspaceClient`, 클릭 후 API 요청 0건·2026-08-13 실측).
   *
   *   종전 스펙은 해네스 픽스처 문자열(`"Schedule HVAC inspection within 48 hours."` ·
   *   `"NPS: 41.2"`)이 화면에 뜨기를 기다렸다. **앱이 그 API 를 부르지 않으므로 원리적으로
   *   뜰 수 없다** — 픽스처를 보강해도 통과하지 않는다(그 착각으로 한 번 우회됐다).
   *
   *   → **제품이 실제로 내는 것**을 잠근다: 로컬 산출 결과에 그것이 추정임을 밝히는
   *     정직 고지(#634)가 붙어 있는가. 고지가 사라지면 여기서 빨강이 된다.
   */
  await page.goto("/en/maintenance");
  await expect(page.getByText("Predictive maintenance")).toBeVisible();
  await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
  await page.getByRole("button", { name: "Run maintenance analysis" }).click();
  await expect(page.getByTestId("local-estimate-notice")).toBeVisible({
    timeout: 15_000,
  });

  await page.goto("/en/digital-twin");
  await expect(
    page.getByText("Digital twin, risk, and permit readiness"),
  ).toBeVisible();
});

/**
 * ★`/en/tenant` 커버리지는 **제품 결함에 막혀 있다** — 스펙이 낡은 게 아니다.
 *
 *   종전 스펙은 이 경로에서 `"Tenant experience"` · `"Analyze feedback"` 등 영문 UI 를
 *   기대했다. 그런데 페이지가 `OperationsIntelligenceWorkspaceClient` 에서
 *   `TenantWorkspaceClient` 로 교체됐고, 그 컴포넌트는 **로케일 지원이 없다** —
 *   `/en` 으로 들어가도 화면이 전부 한국어다(실측: `시설명(예: 커뮤니티 라운지)` ·
 *   `메모(선택)` · `취소할 예약 ID`).
 *
 *   ★한국어 기대로 바꾸면 통과하지만 **그 결함을 굳히는 것**이므로 하지 않는다.
 *     이건 컴포넌트층 i18n 캠페인의 일부다 — 실측 규모 **134파일·341개**
 *     (`placeholder`/`aria-label` 한국어 하드코딩, 2026-08-16).
 *     내비게이션 SSOT(레지스트리 44 + 섹션 8 + 단계 11)는 이미 봉합됐고
 *     `__tests__/nav-i18n.coverage.test.ts` 가 잠그고 있다.
 *
 *   해제 조건: `TenantWorkspaceClient` 가 로케일을 타면 `.fixme` 를 떼고 살린다.
 */
test.fixme(
  "tenant workspace stays executable in English — TenantWorkspaceClient 로케일 미지원으로 보류",
  async ({ page }) => {
    await installReleaseHarness(page);
    await page.goto("/en/tenant");
    await expect(page.getByText("Tenant experience")).toBeVisible();
    await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
    await page.getByRole("button", { name: "Analyze feedback" }).click();
    await expect(page.getByTestId("local-estimate-notice")).toBeVisible({
      timeout: 15_000,
    });
  },
);

// ── 삭제된 화면을 겨냥하던 테스트 2건을 걷어냈다(2026-08-13) ──
// `d8f9c3da refactor(ux): … 고아 라우트 정리` 가 **10개 라우트를 의도적으로 삭제**했고,
// 그중 셋이 이 스펙의 대상이었다 — 실측 404:
//     /en/agent · /en/dashboard/kdx · /en/feasibility
// 삭제된 화면을 "브라우저에서 실행 가능한가"로 검사하는 것은 의미가 없다. 제품이 되살리기로
// 결정하면 그때 스펙도 함께 되살릴 것.
// ★부수 관찰(제품 쪽 사실): `KdxMonitoringWorkspaceClient` 는 **어떤 page 에서도 마운트되지
//   않는다**(컴포넌트·API 목은 남아 있다). 고아 라우트 정리가 컴포넌트까지는 정리하지 않았다.
test.fixme("KDX 워크스페이스 진입점 — 컴포넌트만 남고 라우트가 없다(제품 결정 필요)", async () => {});

