import { expect, test } from "@playwright/test";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";

test("maintenance, tenant, and digital twin routes stay executable", async ({
  page,
}) => {
  await installReleaseHarness(page);

  await page.goto("/en/maintenance");
  await expect(page.getByText("Predictive maintenance")).toBeVisible();
  await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
  await page.getByRole("button", { name: "Run maintenance analysis" }).click();
  await expect(
    page.getByText("Schedule HVAC inspection within 48 hours."),
  ).toBeVisible({ timeout: 15_000 });

  await page.goto("/en/tenant");
  await expect(page.getByText("Tenant experience")).toBeVisible();
  await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
  await page.getByRole("button", { name: "Analyze feedback" }).click();
  await expect(
    page.getByText(
      "A same-day maintenance follow-up has been scheduled for the tenant.",
    ),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Calculate health" }).click();
  await expect(page.getByText(/NPS: 41.2/i)).toBeVisible({ timeout: 15_000 });

  await page.goto("/en/digital-twin");
  await expect(
    page.getByText("Digital twin, risk, and permit readiness"),
  ).toBeVisible();
});

// ── 삭제된 화면을 겨냥하던 테스트 2건을 걷어냈다(2026-08-13) ──
// `d8f9c3da refactor(ux): … 고아 라우트 정리` 가 **10개 라우트를 의도적으로 삭제**했고,
// 그중 셋이 이 스펙의 대상이었다 — 실측 404:
//     /en/agent · /en/dashboard/kdx · /en/feasibility
// 삭제된 화면을 "브라우저에서 실행 가능한가"로 검사하는 것은 의미가 없다. 제품이 되살리기로
// 결정하면 그때 스펙도 함께 되살릴 것.
// ★부수 관찰(제품 쪽 사실): `KdxMonitoringWorkspaceClient` 는 **어떤 page 에서도 마운트되지
//   않는다**(컴포넌트·API 목은 남아 있다). 고아 라우트 정리가 컴포넌트까지는 정리하지 않았다.
test.fixme("KDX 워크스페이스 진입점 — 컴포넌트만 남고 라우트가 없다(제품 결정 필요)", async () => {});

