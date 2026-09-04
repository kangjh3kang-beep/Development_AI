import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";

/**
 * 하이드레이션 수정의 **범위**를 잠근다 — 행위 잠금은 여기 있지 않다.
 *
 * ■ 고친 결함
 *   프로젝트 선택 드롭다운이 `pickerProjects.length > 0` 으로 조건부 렌더되는데,
 *   그 값은 `useProjectStore.projects`(zustand persist = localStorage)에서 파생된다.
 *   서버에는 localStorage 가 없어 SSR 은 그 노드를 안 그리고, 브라우저는 store 생성 시점의
 *   **동기 재수화** 때문에 첫 렌더에 그린다 → **React #418**.
 *   로컬 프로덕션 빌드 변이로 확정: `/ko/regulations` 의 #418 **1→0**,
 *   양성 대조군(다른 라우트) **1 유지**.
 *
 * ■ ★유닛으로는 이 결함을 잠글 수 없다 — 두 번 시도해 두 번 다 공허했다(실측 2026-08-26)
 *   1) `renderToString(빈 스토어) === renderToString(채운 스토어)` → **변이 SURVIVED.**
 *      센티널로 찍어 보니 `renderToString` 안에서 `pickerProjects.length === 0` 이었다 —
 *      zustand `persist` 가 `getServerSnapshot` 으로 **초기 상태**를 주므로 서버 렌더는
 *      **게이트 유무와 무관하게 늘 빈 값**을 본다. 단언이 **원리적으로 참**이었다.
 *   2) `hydrateRoot` + `console.error` 감시 → **변이 SURVIVED.**
 *      jsdom + `act()` 는 React 동시성 하이드레이션을 전부 flush 해
 *      **수정본과 변이본의 DOM 이 완전히 동일**했고(`SSR:false | act 내부:false | act 이후:true`
 *      가 양쪽 같음), prod 빌드가 아니라 불일치가 `console.error` 로도 안 나왔다.
 *
 *   → **행위 잠금은 실브라우저·프로덕션 빌드에서만 선다.**
 *     `e2e/hydration-lifecycle-rail.spec.ts` 에 형제 테스트로 넣었다
 *     (그 파일이 2026-08-13 같은 결함으로 만들어진 자리이고, 그 스펙의 `test.fixme` 가
 *      남긴 **잔여 소비처 스윕**의 한 건이 바로 이 건이다).
 *   ★단 그 e2e 는 `e2e-nightly.yml` 에서 돈다 — **필수 CI 게이트가 아니다.**
 *     즉 이 수정은 **머지 시점에는 회귀망이 없다.** 알고 남긴다.
 *
 * ■ 그래서 여기서는 **범위만** 잠근다: 게이트가 컴포넌트를 통째로 죽이지 않았는가.
 *   (전체를 게이트하면 첫 페인트에 주소 입력이 사라져 결함보다 나쁘다.)
 */

vi.mock("@/components/common/GlobalAddressSearch", () => ({
  GlobalAddressSearch: () => <div data-testid="address-search" />,
}));

describe("ProjectAddressInput — 하이드레이션 게이트의 범위", () => {
  it("★게이트가 컴포넌트 전체를 죽이지 않는다 — 라벨과 검색창은 서버에서도 그린다", () => {
    const html = renderToString(
      <ProjectAddressInput value="" onChange={() => {}} label="대지 주소" />,
    );
    expect(html).toContain("대지 주소");
    expect(html).toContain("address-search");
  });

  it("서버 렌더에 드롭다운이 없다(정상 — persist 는 서버에서 빈 값이다)", () => {
    // ★이 단언은 **결함을 잡지 못한다**(위 ■ 참조). 서버 계약이 유지되는지만 기록한다:
    //   서버 HTML 에 `<select>` 가 생기면 그건 다른 종류의 변경이므로 알려 준다.
    const html = renderToString(<ProjectAddressInput value="" onChange={() => {}} />);
    expect(html).not.toContain("<select");
  });

  it.todo(
    "★행위 잠금은 e2e 에 있고 필수 CI 가 아니다 — 나이틀리가 아니라 PR 게이트에서 도는 " +
      "하이드레이션 검사(프로덕션 빌드 스모크)를 별건으로 만들어야 한다",
  );
});
