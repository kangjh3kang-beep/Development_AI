/**
 * ★렌더러블 등록 불변식 — active+mapEffect 컨트롤을 가진 레이어는 반드시
 * SATONG_RENDERABLE_LAYER_IDS에 등록돼야 한다.
 *
 * 미등록 시 레일 클릭이 early-return으로 레이어를 켜지 못하고 "지도에 표시하지
 * 않습니다" 거짓 배너가 노출된다(정직원칙 역위반). 이 함정은 실거래/POI(C1·C2 리뷰),
 * capacity(WS-D R1 BLOCKING)에서 **세 번 반복**됐다 — 신규 레이어 추가 시 이 테스트가
 * 등록 누락을 머지 전에 잡는다.
 */
import { describe, expect, it } from "vitest";

import { isRenderableSatongMapLayer } from "@/lib/satong-map-layers";
import { SATONG_MAP_SHELL_LAYERS } from "@/components/precheck/SatongMapShell";

describe("SATONG_RENDERABLE_LAYER_IDS 불변식", () => {
  it("★active + mapEffect 컨트롤 보유 레이어는 전부 renderable 등록", () => {
    const missing = SATONG_MAP_SHELL_LAYERS
      .filter((l) => l.status === "active" && l.controls?.some((c) => c.mapEffect))
      .filter((l) => !isRenderableSatongMapLayer(l.id))
      .map((l) => l.id);
    expect(missing).toEqual([]);
  });
});
