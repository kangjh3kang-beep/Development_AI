/**
 * **전제 잠금** — persist 스토어라도 `getInitialState()` 는 **재수화 이전** 값을 준다.
 *
 * ★왜 이걸 잠그나(2026-08-26 · 비싼 교훈)
 *   이 전제를 몰라서 `#850` 이 **결함이 아닌 것**을 고쳤다. 셀렉터(`useXStore((s) => …)`)로 읽는
 *   persist 소비는 하이드레이션 렌더에서 **초기값**을 보므로 서버와 같은 것을 그린다 —
 *   즉 **원리적으로 불일치를 만들지 못한다.** 그런데 저장소의 안내(부채 목록·독스트링)는
 *   *"persist 파생값을 SSR 경로에서 렌더하는 자리"* 를 통째로 위험으로 적어 두어,
 *   다음 사람을 **없는 결함**으로 보낸다. 실제로 한 세션과 PR 하나를 그렇게 썼다.
 *
 * ★★그리고 근거를 **한 겹 더** 파야 한다(독립 리뷰 지적).
 *   `useSyncExternalStore(subscribe, getState, getInitialState)` 라는 사실만으로는 **부족하다** —
 *   바닐라 `createStore` 의 `initialState` 는 **initializer 반환값**이고, `persist` 는 그 안에서
 *   **동기 재수화를 끝낸다.** 안전한 진짜 이유는 `zustand/middleware` 가
 *   `api.getInitialState = () => configResult` 로 **다시 덮어쓰기** 때문이다.
 *   그래서 이 파일은 **persist 스토어**를 픽스처로 쓴다 — 그 한 줄이 사라지면 빨개진다.
 *   (변이 실측: 그 대입을 지우면 `getInitialState().n` 이 0 → 77 로 바뀌고 아래 두 단언이 깨진다.)
 *
 * 진짜 위험은 그 스냅샷을 **우회**하는 읽기다 — `getState()` · 스토어 메서드 호출 · `localStorage` 직접.
 * 그 분류는 `lib/hydration/render-path-store-reads.ts` 가 파서로 수행하고,
 * 실제 결함 사례는 `components/common/__tests__/GlobalAddressSearch.hydration.test.tsx` 가 잠근다.
 */
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";
import { persist, type PersistStorage, type StorageValue } from "zustand/middleware";

type Probe = { n: number; read: () => number };

/** 이미 값이 저장돼 있는 **동기** 저장소 — 브라우저 `localStorage` 와 같은 조건. */
/** ★`read` 는 저장되지 않는다(함수) — 재수화는 `n` 만 덮어쓴다. 실제 스토어와 같은 조건. */
const SEEDED = { state: { n: 77 }, version: 0 } as unknown as StorageValue<Probe>;
const syncStorage: PersistStorage<Probe> = {
  getItem: () => SEEDED,
  setItem: () => {},
  removeItem: () => {},
};

const usePersistedStore = create<Probe>()(
  persist(
    (_set, get) => ({ n: 0, read: () => get().n }),
    { name: "hydration-probe", storage: syncStorage },
  ),
);

function ViaSelector() {
  const n = usePersistedStore((s) => s.n);
  return <span>{`셀렉터:${n}`}</span>;
}
function ViaGetState() {
  const n = usePersistedStore.getState().n;
  return <span>{`직접:${n}`}</span>;
}

/**
 * ★**스토어 메서드** 경유 — `getState()` 를 안 써도 메서드 내부의 `get()` 이 라이브를 읽는다.
 *   2026-08-27 `FeasibilityEditorV2` 의 실제 결함 형태다(`feasibilityCompleteness()`).
 *   이 대조군이 없으면 "getState 만 조심하면 된다"는 **좁은 오독**이 굳는다.
 */
function ViaMethod() {
  const read = usePersistedStore((s) => s.read);
  return <span>{`메서드:${read()}`}</span>;
}
/**
 * ★처방 형태 — 입력을 **객체 셀렉터 + `useShallow`** 로 읽고 계산은 **순수 함수**로.
 * ★초판은 `(s) => ({ n: s.n }).n` 이었는데 그건 객체를 즉시 푸는 **스칼라 셀렉터**라
 *   바로 위 `ViaSelector` 와 판별력이 같았다 — **실제 처방을 한 번도 렌더하지 않았다**
 *   (독립 리뷰 MINOR-1: 등재와 산출물이 갈렸다). 실제 형태 그대로 태운다.
 */
const double = (i: { n: number }) => i.n * 2;
const pickN = (s: Probe) => ({ n: s.n });
function ViaSelectorThenPure() {
  const i = usePersistedStore(useShallow(pickN));
  return <span>{`처방:${double(i)}`}</span>;
}

describe("zustand persist 서버 스냅샷 계약", () => {
  it("전제 — persist 는 스토어 생성 시점에 **동기 재수화**를 끝낸다(픽스처가 성립하는가)", () => {
    // 이게 0 이면 아래 대조군이 두 모집단을 가르지 못해 전부 공허해진다.
    expect(usePersistedStore.getState().n).toBe(77);
  });

  it("★`getInitialState()` 는 **재수화 이전** 값이다 — 이 한 줄이 안전의 진짜 근거다", () => {
    expect(usePersistedStore.getInitialState().n).toBe(0);
  });

  it("★셀렉터 읽기는 서버 렌더에서 초기값을 본다(= 하이드레이션 안전)", () => {
    const html = renderToString(<ViaSelector />);
    expect(html).toContain("셀렉터:0");
    expect(html).not.toContain("셀렉터:77");
  });

  it("★대조군 — `getState()` 직접 읽기는 **라이브(재수화된) 값**을 본다(= 서버/클라가 갈린다)", () => {
    // 이 줄이 두 모집단을 가른다. 둘 다 0 이면 위 검사는 "무엇을 재도 0"인 공허한 참이 된다.
    expect(renderToString(<ViaGetState />)).toContain("직접:77");
  });

  it("★★스토어 **메서드** 호출도 라이브를 본다 — `getState()` 만 조심하면 된다는 오독을 막는다", () => {
    // 2026-08-27 실제 결함(`feasibilityCompleteness()`)의 형태. 셀렉터로 꺼냈어도 **부르면** 라이브다.
    expect(renderToString(<ViaMethod />)).toContain("메서드:77");
  });

  it("★처방 — 입력은 셀렉터로, 계산은 순수 함수로 하면 서버 스냅샷을 벗어나지 않는다", () => {
    const html = renderToString(<ViaSelectorThenPure />);
    expect(html).toContain("처방:0");
    expect(html).not.toContain("처방:154"); // 라이브(77×2)를 봤다면 이 값이 나온다
  });
});
