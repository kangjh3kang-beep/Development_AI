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
    // ★★필터를 걸지 않는다 — 걸었다가 **CI 에서 공허해졌다**(적대검증 지적, 실측 확인).
    //   dev 번들은 "Hydration failed …" 라는 산문을 던지지만, **프로덕션 번들에는 그 문자열이
    //   0건**이고 `Minified React error #418` 로 최소화된다(`.next/static` 실측: "Hydration failed" 0,
    //   "Minified React error" 6파일). CI 는 `pnpm build && pnpm start` = **프로덕션**이므로
    //   `/Hydration failed/i` 필터는 **절대 매치되지 않아 무조건 초록**이 된다.
    //   → 이 페이지에서 나는 **모든 uncaught error** 를 대상으로 삼는다(형제 스펙
    //     `digital-twin-scene.spec.ts` 도 같은 방식이고, 그래서 그쪽이 이 버그를 잡았다).
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => {
      const msg = String((e as Error)?.message ?? e);
      pageErrors.push(msg.split("\n")[0]);
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
      pageErrors,
      `이 화면에서 uncaught error 가 났다 — 대개 하이드레이션 불일치이며 prod 에서는 ` +
        `\`Minified React error #418\` 로 최소화돼 나온다:\n${pageErrors.join("\n")}`,
    ).toEqual([]);
  });
});

// ── 부채: 같은 패턴이 남아 있는 소비처(적대검증이 실측으로 준 목록 — 스냅샷) ──
// `persist` 스토어(6개, 어느 것도 `skipHydration` 을 쓰지 않는다)에서 파생한 값을 SSR 경로에서
// 그대로 렌더하는 자리가 더 있다. 이 PR 은 **같은 레이아웃의 3곳**(레일·주소바·다음단계 CTA)만 고쳤다.
//   · `app/[locale]/(dashboard)/projects/[id]/permit/page.tsx:201` — `진행률 {pct}%`(글자 그대로 같은 형태)
//   · `components/common/ContextHeader.tsx` · `components/common/ProjectSwitcher.tsx`
//   · `canvas` · `bim-studio` · `design-studio` · `analytics/investment` · `multi-parcel` 페이지 등
// ★4개 페이지는 **의도가 아니라 `useDictionary` 스피너로 우연히 가려져** 있다 — 사전 로딩을
//   서버로 옮기는 "당연한 최적화"를 하면 한꺼번에 결함으로 바뀐다.
test.fixme(
  "persist 파생값을 SSR 경로에서 렌더하는 잔여 소비처 — 전수 스윕 + 재발 강제(lint/락)",
  async () => {},
);
