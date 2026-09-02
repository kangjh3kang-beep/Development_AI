import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";
import { gotoLive } from "./support/goto-live";

const routes = [
  { name: "login", path: "/en/login", withSession: false },
  { name: "dashboard", path: "/en", withSession: true },
  // ★`/en/approvals` 를 뺐다 — `d8f9c3da`(고아 라우트 정리)에서 **삭제된 라우트**다.
  //   404 페이지는 본문이 33자뿐이라 접근성 위반이 있을 수 없어, 이 감사는 대상이 사라진 뒤에도
  //   **조용히 초록**이었다(실측). 아래 `gotoLive` 가 앞으로 같은 일을 막는다.
  {
    name: "project contracts",
    path: `/en/projects/${RELEASE_PROJECT_ID}/contracts`,
    withSession: true,
  },
  { name: "offline fallback", path: "/offline", withSession: true },
];

for (const route of routes) {
  test(`critical accessibility audit stays clean for ${route.name}`, async ({
    page,
  }) => {
    await installReleaseHarness(page, { withSession: route.withSession });
    // ★404 면 여기서 실패한다 — 감사 대상이 실재하는지를 먼저 강제한다(공허한 초록 차단).
    await gotoLive(page, route.path);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const criticalViolations = results.violations.filter(
      (violation) => violation.impact === "critical",
    );

    expect(criticalViolations).toHaveLength(0);
  });
}

/**
 * ★2026-08-13 재작성 — 이 검사는 **없는 UI** 를 기다리고 있었다.
 *
 *   종전: `Login` / `Register admin` **모드 버튼**을 탭으로 훑었다.
 *   현재: 모드 전환이 **버튼이 아니라 라우트**(`/login` ↔ `/register`)로 바뀌어 그 버튼이
 *         렌더되지 않는다. 그래서 `locator.focus` 가 60초 타임아웃으로 죽고 있었다.
 *
 *   ★함정: 그 문자열은 `AuthWorkspaceClient` 의 copy 사전에 **남아만 있었다**
 *     (`modeLabels.login/register`, 소비처 0). grep 으로는 "있다"고 나와 드리프트가 가려졌다 —
 *     **문자열이 존재한다 ≠ 렌더된다.** 같은 커밋에서 그 죽은 copy 를 걷어낸다.
 *
 *   아래 순서는 **실측**이다(2026-08-13 `/en/login`):
 *     Skip to content → email → password → Run login → 비밀번호 찾기 → 소셜 3 → 신규 테넌트 링크
 */
/**
 * ★2026-08-23 — **이 감사는 모달을 한 번도 열지 않는다.**
 *
 * 위 라우트 4개를 axe 로 훑지만, 정작 접근성에서 가장 위험한 표면인 **모달**
 * (포커스 트랩·`aria-modal`·ESC·복귀)은 **e2e 전체에서 0건** 태워지고 있다
 * (`grep 'aria-modal|role="dialog"|data-modal-focus' e2e/*.spec.ts` = 0).
 *
 * ## ★★2026-08-24 정정 — **이 문서의 "못 한다"는 전제가 뒤집혔다**
 *
 * 아래 3회 탐색은 **전부 비로그인 조건**이었다. 그 뒤 **라이브 테스트 계정**이 생겼고,
 * 다른 세션이 `4t8t.net` 로그인 + Playwright(읽기전용)로 `/ko/projects/{id}` 같은
 * **실제 프로젝트 화면을 실브라우저로 태웠다.** 즉 *"목록이 0개라 모달에 못 닿는다"* 는
 * **인증이 없을 때만 참**이다.
 *
 * → 아래 "선행 조건"은 **하네스 확장만이 유일한 길인 것처럼** 읽히는데 그렇지 않다.
 *   **로그인 세션 + 실데이터**로도 닿는다. 이 `fixme` 는 그 경로로 **승격 가능하다.**
 *
 * ★교훈: **"불가"는 그때의 조건에서만 참이다.** 나는 결론과 조건을 함께 적었지만
 *   **다음 사람은 결론만 읽는다** — 기각·보류에는 **무엇이 바뀌면 뒤집히는지**를 적어야 한다.
 *   (그래서 이 절을 조건 서술 **위**에 둔다. 아래에 달면 같은 실수가 반복된다.)
 *
 * ## 왜 아직 못 했나 — 추측이 아니라 실측이다 (★2026-08-23 · 비로그인 조건)
 *
 * 실브라우저에서 배선된 모달에 **닿는 경로를 찾지 못했다**(2026-08-23, 3회 탐색):
 *   · `/en/projects`                      → 프로젝트 카드 **0개**(하네스가 목록을 주지 않는다)
 *                                            → `ConfirmDeleteModal` 을 열 수 없다
 *   · `/en/projects/{id}/contracts`        → 모달 진입점 없음(액션 버튼뿐)
 *   · `AI 어시스턴트 열기`                 → `role="dialog"` 0 · `aria-modal` 0 → 모달이 아니다
 *
 * ## 열리면 무엇을 잠글지 (선행 작업이 끝나면 이 자리)
 *
 * ① 열었을 때 포커스가 대화상자 **안**으로 들어오는가
 * ② 마지막 요소에서 `Tab` 이 첫 요소로 **도는가**(그리고 `Shift+Tab` 역방향)
 * ③ 닫으면 **열기 전 요소**로 돌아오는가
 *
 * ★②는 **jsdom 으로는 대신할 수 없는 축**이다. `useModalFocus.test.tsx` 는
 *   *"`position: fixed` 요소는 사양상 `offsetParent` 가 null 이라 jsdom 만의 문제가 아니다"*
 *   라고 **주장**하는데, 그 명제를 **실브라우저로 검증한 테스트가 저장소에 없다.**
 *   (배포 검증에서도 같은 공백이 확인됐다 — 통합자가 *"키보드 Tab 순환이 실제로 도는지는
 *   라이브에서 태우지 못했다"* 고 정직하게 남겼다.)
 *
 * ## ★★2026-08-24 — **실제로 시도했고, 9회 끝에 미검증으로 종결됐다**
 *
 * 위 정정(*"로그인이면 닿는다"*)을 받아 통합자 세션이 **관리자 계정 + Playwright** 로
 * 실브라우저에서 **9회** 시도했다. **모달을 안정적으로 열지 못했다.**
 * 사용자 지시로 배포 주기에 집중하기 위해 **추적을 중단**했다 — 미검증 확정이다.
 *
 * ★**진전이 있었으니 다음 사람은 여기서 출발하라(전부 실측)**:
 *   · 경로: `/ko/projects` 의 **프로젝트 카드 삭제 버튼** → `ConfirmDeleteModal`.
 *     실제로 **8개를 찾았다**(`<button>` · `innerText="✕"`).
 *   · **셀렉터 함정**: 그 버튼의 보이는 텍스트는 `✕` 뿐이고 이름은 `title` 속성에만 있다
 *     (`ProjectsOverviewClient.tsx:279`, `aria-label` 은 **없다**). `innerText` 로
 *     `삭제|delete` 를 찾으면 **0개**다. `getByTitle(/삭제/)` 또는 `getByRole` 을 써라.
 *   · **타이밍 함정**: 목록은 `useEffect(syncFromBackend)` 로 **마운트 후 비동기 로드**된다
 *     (`ProjectsOverviewClient.tsx:62~70`). 헤더의 `.cc-live` 가 `SYNCING` → **`LIVE`** 가
 *     될 때까지 기다려야 카드가 있다.
 *   · **포털 함정**: 이 모달은 `createPortal(..., document.body)` 다
 *     (`ConfirmDeleteModal.tsx:90·159`). 스코프된 로케이터로는 `[data-modal-focus]` 를
 *     **못 본다** — 페이지 레벨로 잡아라.
 *   · **파괴적 조작 금지**: 확인 버튼은 진짜 삭제다(다만 프로젝트명 입력이 강제라
 *     실수로는 안 지워진다). 열고 `Tab` 만 재고 `ESC` 로 닫아라.
 *
 * ★**세 함정 모두 "소스를 한 단계 더 읽으면 알 수 있는 것"이었다.** 이 문서를 쓴 나는
 *   매 라운드 한 겹씩만 벗겨 넘겼고, 그때마다 남의 시도 한 번이 소모됐다.
 *   **남에게 검증을 부탁할 때는 그 절차를 끝까지 시뮬레이션한 뒤 넘겨라.**
 *
 * ## 선행 조건 (★위 정정 참조 — 둘 중 **하나만** 있으면 된다)
 *
 * **(A) 로그인 세션 + 실데이터** — 지금 가능하다. 가장 빠른 길이다.
 * **(B) 하네스 확장** — 아래. 인증 없이 돌리려면 여전히 필요하다.
 *
 * `release-harness` 가 **프로젝트 목록**을 주면 `/en/projects` 에서 삭제 버튼 →
 * `ConfirmDeleteModal` 로 닿는다. 하네스는 공용 파일이라 다른 스펙에 영향이 가므로
 * **별건으로 분리**한다. 그때 `[data-modal-focus]`(훅이 실제로 가둔 컨테이너 표식)를
 * 앵커로 쓰면 트랩 범위를 정확히 잴 수 있다.
 */
test.fixme(
  "modal focus trap holds in a real browser (needs a harness route that opens one)",
  async () => {
    // 진입 경로가 생기면 위 ①②③ 을 여기서 태운다.
  },
);

test("keyboard navigation reaches the live login controls in order", async ({
  page,
}) => {
  await installReleaseHarness(page, { withSession: false });
  await page.goto("/en/login");

  const emailInput = page.getByLabel("Email");
  await expect(emailInput, "로그인 폼이 렌더되지 않았다 — 아래 탭 순서 검사가 공허해진다").toBeVisible();

  // 문서 첫 탭은 스킵 링크다(접근성 계약). 그다음이 로그인 컨트롤 체인.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /skip to content/i })).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(emailInput).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password")).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Run login" })).toBeFocused();

  // ★모드 전환은 이제 링크다 — 키보드로 **도달 가능**해야 한다(종전 버튼 계약의 대체물).
  //   몇 번째인지까지 고정하면 소셜 버튼이 하나 늘 때마다 깨진다 — 도달성만 잠근다.
  const registerLink = page.getByRole("link", { name: /create a new tenant/i });
  await expect(registerLink, "관리자 등록으로 가는 링크가 없다 — 모드 전환 경로가 사라졌다").toBeVisible();
  let reached = false;
  for (let i = 0; i < 8 && !reached; i += 1) {
    await page.keyboard.press("Tab");
    reached = await registerLink.evaluate((el) => el === document.activeElement);
  }
  expect(reached, "8번 탭 안에 등록 링크에 닿지 못했다 — 키보드로 모드 전환이 불가능하다").toBe(true);
});
