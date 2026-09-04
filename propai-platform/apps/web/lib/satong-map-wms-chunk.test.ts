/**
 * VWorld WMS **레이어 개수 상한**(4)과 규제 오버레이 청크 — 사용자 지적 "규제 오버레이 타일
 * 조회 실패"의 결정적 원인을 잠근다.
 *
 * ★라이브 실측(2026-08-01, `/tiles/vworld/wms` 동일 bbox 사다리):
 *     1개 → 200 image/png 10879
 *     2개 → 200 image/png 13769
 *     3개 → 200 image/png 28178
 *     4개 → 200 image/png 28178
 *     5개 → **503 {"error":"VWorld WMS returned an XML exception (INVALID_RANGE)"}**
 *   레이어 종류·순서·줌(z7~z19)과 무관하게 **개수에서만** 갈린다.
 *
 * ★왜 심각했나: 규제 컨트롤이 정확히 5개라, 사용자가 5번째를 켜는 순간 한 요청에 5레이어가
 *   실려 나가고 **잘 되던 4개까지 함께 죽었다**(all-or-nothing). "하나 더 켰더니 전부
 *   사라졌다"가 정확한 증상이고, 그래서 원인이 특정 레이어로 보이지 않았다.
 */
import { describe, expect, it } from "vitest";

import {
  REGULATION_WMS_BY_CONTROL,
  VWORLD_WMS_MAX_LAYERS,
  resolveRegulationWmsLayerChunks,
} from "@/lib/satong-map-layers";
import type { SatongMapLayerState } from "@/lib/satong-map-layers";

/** 규제 컨트롤 n개를 켠 레이어 상태. ★정본 타입(enabledLayerIds/controlsByLayer)에 충실하게.
 *   대역이 실제 형태와 다르면 통과해도 아무것도 잠기지 않는다(대역 불충실 = 가짜 초록). */
function stateWith(controlIds: string[]): SatongMapLayerState {
  return {
    enabledLayerIds: ["zoning"],
    controlsByLayer: { zoning: controlIds },
  } as SatongMapLayerState;
}

const ALL_REGULATION_CONTROLS = Object.keys(REGULATION_WMS_BY_CONTROL);

describe("VWorld WMS 레이어 개수 상한", () => {
  it("★상한은 4다 — 실측에서 5개부터 503 INVALID_RANGE", () => {
    expect(VWORLD_WMS_MAX_LAYERS).toBe(4);
  });

  it("★규제 컨트롤이 상한보다 많다 — 그래서 청크가 필요하다(이 전제가 깨지면 재검토)", () => {
    expect(ALL_REGULATION_CONTROLS.length).toBeGreaterThan(VWORLD_WMS_MAX_LAYERS);
  });
});

describe("resolveRegulationWmsLayerChunks — 어떤 조합에서도 상한을 넘지 않는다", () => {
  it("zoning 레이어가 꺼져 있으면 청크가 없다", () => {
    expect(resolveRegulationWmsLayerChunks(undefined)).toEqual([]);
    expect(
      resolveRegulationWmsLayerChunks({ enabledLayerIds: [], controlsByLayer: {} } as SatongMapLayerState),
    ).toEqual([]);
  });

  it("컨트롤이 없으면 청크가 없다(빈 문자열 요청 금지)", () => {
    expect(resolveRegulationWmsLayerChunks(stateWith([]))).toEqual([]);
  });

  it.each([1, 2, 3, 4])("컨트롤 %i개는 청크 1장(상한 이하라 나눌 필요 없음)", (n) => {
    const chunks = resolveRegulationWmsLayerChunks(stateWith(ALL_REGULATION_CONTROLS.slice(0, n)));
    expect(chunks).toHaveLength(1);
    expect(chunks[0].split(",")).toHaveLength(n);
  });

  it("★★컨트롤 5개(전부 켬)는 2장으로 쪼갠다 — 종전엔 한 장에 5레이어라 전체가 503이었다", () => {
    const chunks = resolveRegulationWmsLayerChunks(stateWith(ALL_REGULATION_CONTROLS));
    expect(chunks.length).toBeGreaterThan(1);
    for (const c of chunks) {
      expect(c.split(",").length).toBeLessThanOrEqual(VWORLD_WMS_MAX_LAYERS);
    }
  });

  it("★불변식: **모든 부분집합**에서 어떤 청크도 상한을 넘지 않는다(전수 검사)", () => {
    const n = ALL_REGULATION_CONTROLS.length;
    let checked = 0;
    for (let mask = 1; mask < 1 << n; mask += 1) {
      const picked = ALL_REGULATION_CONTROLS.filter((_, i) => mask & (1 << i));
      const chunks = resolveRegulationWmsLayerChunks(stateWith(picked));
      for (const c of chunks) {
        expect(c.split(",").length).toBeLessThanOrEqual(VWORLD_WMS_MAX_LAYERS);
      }
      // 손실 금지 — 쪼개면서 레이어가 사라지면 규제가 조용히 안 그려진다.
      expect(chunks.join(",").split(",").filter(Boolean)).toHaveLength(picked.length);
      checked += 1;
    }
    expect(checked).toBe((1 << n) - 1); // 공허 통과 방지: 실제로 전 조합을 돌았는가
  });

  it("★청크는 원본 레이어를 중복 없이 보존한다(순서·집합 동일)", () => {
    const chunks = resolveRegulationWmsLayerChunks(stateWith(ALL_REGULATION_CONTROLS));
    const flat = chunks.join(",").split(",");
    expect(new Set(flat).size).toBe(flat.length);
    expect(flat).toEqual(ALL_REGULATION_CONTROLS.map((c) => REGULATION_WMS_BY_CONTROL[c]));
  });
});
