import { expect, test } from "@playwright/test";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";

test("auth to dashboard release cutover chain stays live-first", async ({
  page,
}) => {
  await installReleaseHarness(page, { withSession: false });

  await page.goto("/en/login");
  await page.getByLabel("Email").fill("ops@propai.dev");
  await page.getByLabel("Password").fill("super-secret-password");
  await page.getByRole("button", { name: "Run login" }).click();

  /**
   * ★로그인 성공 시 **성공 문구는 뜨지 않는다** — 즉시 이동한다.
   *
   *   `AuthWorkspaceClient` 는 `source === "login" | "register"` 이면
   *   `router.push(resolveNextPath(next, locale))` 후 **곧바로 `return`** 한다
   *   (2026-07-23 "앱 컨텍스트 복귀" — 분양 현장앱 등에서 재로그인 시 원래 화면으로 돌아가려고
   *   도입됐다). `successLabels.login` 은 그 경로에서 도달 불가이고, 세션 갱신·복원·로그아웃
   *   같은 다른 `source` 에서만 쓰인다.
   *
   *   종전 스펙은 그 문구와 "Open dashboard" 버튼 클릭을 기다렸다 — 둘 다 지금 동작에
   *   존재하지 않는다. **리다이렉트 자체**를 계약으로 삼는다(그게 실제로 보장돼야 할 것이다).
   */
  await expect(page).toHaveURL(/\/en$/);

  /**
   * ★삭제된 UI 를 겨냥하던 단언 3건을 걷어냈다(2026-08-16 실측).
   *
   *   `"Connections"` · `"PropAI API 30.0.0 (production)"` · `"Approval Ops"` ·
   *   `role="navigation"[name="Operations navigation"]` — **네 문자열 모두 제품 소스에서
   *   0건**이다(테스트 제외 `git grep`). 대시보드가 산출물 중심으로 재설계되며 사라졌다.
   *
   *   없는 것을 기다리는 단언은 고쳐도 초록이 되지 않고, 남겨 두면 **무엇이 깨졌는지**를
   *   가린다. 살아 있는 계약(로그인 → 리다이렉트 → 프로젝트 진입점)만 남긴다.
   *
   *   ★대시보드 본문 문구로 잠그지 않은 이유: `/en` 인데 히어로가 한국어다
   *   (컴포넌트층 i18n 캠페인 대상 — 134파일·341개). 한국어로 잠그면 그 결함을 굳힌다.
   */
  // 로그인 후 **인증된 워크스페이스 셸**에 도달했는가 — 이 스펙의 고유 계약이다.
  //   (`Open project` 링크는 대시보드 홈이 아니라 `/en/projects` 에 있고, 그쪽은
  //    `project-release.spec.ts:8` 이 이미 잠근다 — 중복 단언을 만들지 않는다.)
  //   ★영문 라벨로 잠근 것은 의도적이다: `/en` 내비가 한국어로 새던 결함을 봉합했고
  //    (`lib/navigation/nav-i18n.ts`), 이 단언이 그 봉합을 **실제 화면에서** 지킨다.
  const nav = page.getByRole("navigation", { name: "Workspace navigation" });
  await expect(nav.getByRole("button", { name: "Projects" })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Design Center" })).toBeVisible();
});
