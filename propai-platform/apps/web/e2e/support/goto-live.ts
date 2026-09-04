import { expect, type Page } from "@playwright/test";

/**
 * 살아 있는 라우트로만 이동한다 — **404 면 즉시 실패**시킨다.
 *
 * ★왜 필요한가(실측된 공허한 초록): `accessibility.spec.ts` 는 `/en/approvals` 를 감사 대상에
 *   넣고 "critical 위반 0" 을 단언했는데, 그 라우트는 `d8f9c3da`(고아 라우트 정리)에서 **삭제**됐다.
 *   Next.js 의 404 페이지는 본문이 33자뿐이라 **접근성 위반이 있을 수 없다** — 즉 그 검사는
 *   대상이 사라진 뒤에도 조용히 초록이었다. 검사가 무엇을 봤는지가 아니라 **무엇을 못 봤는지**가
 *   문제였다.
 *
 * ★그래서 목록을 고치는 대신 **전제를 강제**한다. 앞으로 어떤 라우트가 사라져도 그 자리에서
 *   빨개진다 — 사람이 목록을 갱신해 주기를 기다리지 않는다(규율 A-4: 목록형 금지).
 *
 * ※ 404 판정은 Next.js 기본 not-found 문구로 한다. 커스텀 404 를 도입하면 여기도 함께 고칠 것.
 */
export async function gotoLive(page: Page, path: string): Promise<void> {
  await page.goto(path, { waitUntil: "domcontentloaded" });
  const body = await page.locator("body").innerText({ timeout: 10_000 });
  expect(
    /This page could not be found/.test(body),
    `${path} 가 404 다 — 라우트가 사라졌는데 이 스펙은 그걸 모른 채 검사를 이어간다.\n` +
      `삭제가 의도라면 이 경로를 스펙에서 빼고, 아니라면 라우트를 되살릴 것.`,
  ).toBe(false);
}
