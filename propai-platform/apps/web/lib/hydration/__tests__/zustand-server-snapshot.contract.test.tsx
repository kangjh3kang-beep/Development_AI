/**
 * **전제 잠금** — zustand v5 는 `useSyncExternalStore` 의 **서버 스냅샷**으로 `getInitialState` 를 준다.
 *
 * ★왜 이걸 잠그나(2026-08-26 · 비싼 교훈)
 *   이 전제를 몰라서 `#850` 이 **결함이 아닌 것**을 고쳤다. 셀렉터(`useXStore((s) => …)`)로 읽는
 *   persist 소비는 하이드레이션 렌더에서 **초기값**을 보므로 서버와 같은 것을 그린다 —
 *   즉 **원리적으로 불일치를 만들지 못한다.** 그런데 저장소의 안내(부채 목록·독스트링)는
 *   *"persist 파생값을 SSR 경로에서 렌더하는 자리"* 를 통째로 위험으로 적어 두어,
 *   다음 사람을 **없는 결함**으로 보낸다. 실제로 한 세션과 PR 하나를 그렇게 썼다.
 *
 *   진짜 위험은 그 스냅샷을 **우회**하는 읽기다 — `getState()` · 스토어 메서드 호출 · `localStorage` 직접.
 *   그 분류는 `lib/hydration/render-path-store-reads.ts` 가 파서로 수행하고,
 *   실제 결함 사례는 `components/common/__tests__/GlobalAddressSearch.hydration.test.tsx` 가 잠근다.
 *
 * ★이 파일이 빨개지면 zustand 업그레이드가 그 계약을 바꾼 것이다 — 위 두 검사의 **의미가 통째로 바뀐다.**
 */
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { create } from "zustand";

const useProbeStore = create<{ n: number }>(() => ({ n: 0 }));

function ViaSelector() {
  const n = useProbeStore((s) => s.n);
  return <span data-testid="selector">{`셀렉터:${n}`}</span>;
}
function ViaGetState() {
  const n = useProbeStore.getState().n;
  return <span data-testid="getstate">{`직접:${n}`}</span>;
}

describe("zustand 서버 스냅샷 계약", () => {
  it("★셀렉터 읽기는 서버 렌더에서 **초기값**을 본다(= 하이드레이션 안전)", () => {
    useProbeStore.setState({ n: 42 });
    expect(useProbeStore.getState().n, "픽스처가 안 먹었다 — 아래 단언이 공허해진다").toBe(42);

    const html = renderToString(<ViaSelector />);
    expect(html).toContain("셀렉터:0");
    expect(html).not.toContain("셀렉터:42");
  });

  it("★대조군 — `getState()` 직접 읽기는 **라이브 값**을 본다(= 서버/클라가 갈린다)", () => {
    useProbeStore.setState({ n: 42 });
    const html = renderToString(<ViaGetState />);
    // 이 줄이 두 모집단을 가른다. 둘 다 0 이면 위 검사는 "무엇을 재도 0"인 공허한 참이 된다.
    expect(html).toContain("직접:42");
  });
});
