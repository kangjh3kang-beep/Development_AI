/**
 * `GlobalAddressSearch` — **서버 렌더가 라이브 저장소를 보지 않는다**는 행위 잠금.
 *
 * ■ 고친 결함(2026-08-26 · 라이브 React #418 `args[]=text`)
 *   `useState` **지연 초기값**이 `useProjectContextStore.getState()`(= **라이브 상태**)를 읽었다.
 *   서버에는 `localStorage` 가 없어 `[]`(요약 배지 "대기")를 그리는데, 브라우저는 persist 가
 *   **스토어 생성 시점에 동기 재수화**를 끝낸 뒤 첫 렌더를 하므로 77필지를 그렸다 →
 *   **텍스트 하이드레이션 불일치**. 로컬 dev 재현 diff 가 이 배지를 정확히 지목했다(`+77필지 / -대기`).
 *
 * ■ ★왜 이번엔 유닛으로 잠글 수 있나 — 형제 실패와 **원인 클래스가 다르다**
 *   `ProjectAddressInput.hydration.test.tsx` 는 같은 기법으로 두 번 시도해 두 번 다 변이가
 *   SURVIVED 했다. 그쪽은 **셀렉터**(`useXStore((s) => …)`) 읽기였고, zustand v5 는
 *   `useSyncExternalStore` 의 **서버 스냅샷**으로 `getInitialState` 를 넘기므로 `renderToString`
 *   이 **늘 초기값**을 본다 — 단언이 원리적으로 참이었다.
 *   이 결함은 `getState()` 라 **그 스냅샷을 우회**한다. 그래서 스토어를 채우면 서버 렌더 결과가
 *   실제로 갈린다 → **두 모집단이 갈리는 픽스처**가 성립한다(아래 대조군이 그것을 단언한다).
 *   ★그 전제(zustand 가 서버 스냅샷을 준다) 자체는
 *     `lib/hydration/__tests__/zustand-server-snapshot.contract.test.tsx` 가 따로 잠근다.
 */
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalAddressSearch, buildInitialAddressEntries } from "@/components/common/GlobalAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";

vi.mock("@/components/ui/KakaoAddressSearch", () => ({
  KakaoAddressSearch: () => null,
}));

const PARCELS = Array.from({ length: 77 }, (_, i) => ({
  address: `경기도 오산시 내삼미동 ${i + 1}`,
  pnu: `4137010300${String(i).padStart(5, "0")}`,
  areaSqm: 50 + i,
  zoneCode: "1N",
}));

beforeEach(() => {
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

describe("GlobalAddressSearch — 서버 렌더는 persist 라이브 상태를 보지 않는다", () => {
  it("★대조군 — 이 픽스처는 두 모집단을 실제로 가른다(가르지 않으면 아래 단언이 공허해진다)", () => {
    const withStore = buildInitialAddressEntries({
      parcels: PARCELS, initialAddress: undefined, writeToContext: true, single: false });
    const withoutStore = buildInitialAddressEntries({
      parcels: undefined, initialAddress: undefined, writeToContext: true, single: false });
    expect(withStore).toHaveLength(77);
    expect(withoutStore).toHaveLength(0);
  });

  it("★스토어에 77필지가 있어도 서버 HTML 은 '대기' 다 — '77필지' 가 나오면 하이드레이션이 깨진다", () => {
    useProjectContextStore.setState({ siteAnalysis: { parcels: PARCELS } } as never);
    // 전제: 스토어가 실제로 채워졌는가(안 채워졌으면 이 검사는 공허하다)
    expect(
      (useProjectContextStore.getState().siteAnalysis as { parcels?: unknown[] } | null)?.parcels,
    ).toHaveLength(77);

    const html = renderToString(<GlobalAddressSearch />);

    // 공허 진리 가드 — 요약 배지가 실제로 서버 HTML 에 있어야 이 단언이 의미를 갖는다.
    expect(html, "요약 배지가 서버 HTML 에 없다 — 이 검사는 공허해진다").toContain("대기");
    expect(html, "서버 렌더가 라이브 저장소를 봤다 — React #418(text) 재발").not.toContain("77필지");
  });

  it("스토어가 비어 있으면(=서버 조건) 결과가 같다 — 위 단언이 '스토어 무관'이 아님을 보인다", () => {
    const html = renderToString(<GlobalAddressSearch />);
    expect(html).toContain("대기");
  });
});
