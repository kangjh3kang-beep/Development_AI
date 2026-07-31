/**
 * SatongMultiMap — 배치 오버레이 **위임 배선** 테스트(W3 / R2 잔여 갭).
 *
 * ★왜 필요한가(R2 실증): 그리기·정리 로직을 `lib/satong-layout-overlay`로 추출해 **로직**은
 *   가짜 L로 잠갔지만, "컴포넌트가 그 로직을 실제로 호출하는가"라는 **배선**은 여전히 무커버리지였다.
 *   리뷰어가 위임 블록 전체와 cleanup return을 각각 지웠는데 **관련 90건이 전부 통과**했다 —
 *   이 저장소가 반복 지적하는 "배선 미변이로 뚫림" 패턴 그 자체다.
 *
 *   그래서 여기서는 오버레이 모듈을 스파이로 대체해 ①올바른 인자로 호출되는가
 *   ②overlay가 바뀌면 이전 레이어를 previousLayer로 넘겨 재호출하는가 ③언마운트 시 정리하는가
 *   를 고정한다. Leaflet 실렌더는 검증 대상이 아니다(그건 라이브 검증 몫).
 */
import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SatongMultiMap from "@/components/map/SatongMultiMap";
import type { SiteLayoutOverlay } from "@/lib/site-layout";

type RenderArgs = {
  L: unknown;
  map: unknown;
  previousLayer: unknown;
  overlay: unknown;
  toRings: (geometry: unknown) => [number, number][][];
};

const render_ = vi.hoisted(() => vi.fn(() => ({ id: "group-1" })));
const clear_ = vi.hoisted(() => vi.fn());

// ★무인자 `vi.fn()`은 `mock.calls`가 빈 튜플 타입이라 `[0]` 인덱싱이 타입 에러가 된다
//   (CI tsc가 적발). 인자를 선언하면 이번엔 unused-vars 경고가 붙는다(이 저장소 eslint는
//   `_` 접두를 면제하지 않는다). 배열 단위로 한 번만 좁혀 둘 다 피한다.
// ★mock.calls는 "인자 배열의 배열"이다 — 첫 인자를 꺼내려면 `[0]`이 필요하다(빠뜨려서 3건 실패).
const renderArgs = () => (render_.mock.calls as unknown as [RenderArgs][]).at(-1)![0];
const clearArgs = () => (clear_.mock.calls as unknown as [unknown, unknown][]).at(-1)!;

vi.mock("@/lib/satong-layout-overlay", () => ({
  renderLayoutOverlay: render_,
  clearLayoutOverlay: clear_,
  BUILDABLE_STYLE: {},
  BUILDING_STYLE: {},
  buildingTooltip: () => "",
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

const OVERLAY = (tag: string): SiteLayoutOverlay => ({
  buildable: { type: "Polygon", coordinates: [[[127, 37]]], tag } as never,
  buildings: null,
  northLightBand: null,
});

describe("SatongMultiMap 배치 오버레이 위임 배선(W3)", () => {
  beforeEach(() => {
    render_.mockClear();
    clear_.mockClear();
    render_.mockReturnValue({ id: "group-1" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("★① overlay를 받으면 renderLayoutOverlay에 올바른 인자로 위임한다", () => {
    const overlay = OVERLAY("a");
    render(<SatongMultiMap layoutOverlay={overlay} />);

    expect(render_).toHaveBeenCalled();
    const arg = renderArgs();
    expect(arg.overlay).toBe(overlay);
    // 링 변환기를 주입한다(컴포넌트가 좌표를 직접 만들지 않는다는 계약).
    expect(typeof arg.toRings).toBe("function");
    // 첫 렌더엔 이전 레이어가 없다.
    expect(arg.previousLayer).toBeNull();
  });

  it("★② overlay가 바뀌면 **새로 그리기 전에** 이전 레이어를 정리한다(잔존 방지 배선)", () => {
    // ★잔존 방지의 실제 메커니즘은 `previousLayer`가 아니라 **effect cleanup**이다:
    //   React는 deps 변경 시 cleanup → 새 effect 순서로 실행하므로, 재실행 시점의
    //   layoutLayerRef는 이미 null이다(cleanup이 비운다). 따라서 검증해야 하는 계약은
    //   "clearLayoutOverlay(이전 그룹)가 다음 renderLayoutOverlay보다 **먼저** 호출된다"다.
    const { rerender } = render(<SatongMultiMap layoutOverlay={OVERLAY("a")} />);
    const firstRenderOrder = render_.mock.invocationCallOrder.at(-1)!;
    clear_.mockClear();

    const next = OVERLAY("b");
    rerender(<SatongMultiMap layoutOverlay={next} />);

    // 새 오버레이로 다시 위임됐다.
    const lastRenderOrder = render_.mock.invocationCallOrder.at(-1)!;
    expect(lastRenderOrder).toBeGreaterThan(firstRenderOrder);
    expect(renderArgs().overlay).toBe(next);

    // ★이전 그룹이 정리됐고, 그 정리가 새 그리기보다 앞이다.
    expect(clear_).toHaveBeenCalled();
    expect(clearArgs()[1]).toEqual({ id: "group-1" });
    expect(clear_.mock.invocationCallOrder.at(-1)!).toBeLessThan(lastRenderOrder);
  });

  it("★③ 언마운트 시 clearLayoutOverlay로 정리한다(orphan 레이어 방지)", () => {
    const { unmount } = render(<SatongMultiMap layoutOverlay={OVERLAY("a")} />);
    clear_.mockClear();

    unmount();

    expect(clear_).toHaveBeenCalled();
    expect(clearArgs()[1]).toEqual({ id: "group-1" });
  });

  it("④ overlay가 없어도 위임은 호출된다(이전 레이어 정리를 그 함수가 담당하므로)", () => {
    render(<SatongMultiMap layoutOverlay={null} />);
    expect(render_).toHaveBeenCalled();
    const arg = renderArgs();
    expect(arg.overlay).toBeNull();
  });
});
