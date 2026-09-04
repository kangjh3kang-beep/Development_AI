/**
 * identity churn 회귀망 — "리렌더가 지도 레이어를 전량 재생성하지 않는다".
 *
 * ★실결함: 오버레이 effect의 deps에 `onFeatureClick`(함수 identity)이 들어 있었고,
 *   소비처(LandScheduleClient 등)는 인라인 함수·인라인 배열·인라인 객체를 넘겼다.
 *   그래서 필지를 클릭할 때마다(=setHighlight로 리렌더) 폴리곤·마커·팝업이 전량
 *   파괴·재생성됐고, 경계 POST(타임아웃 45초)까지 새로 발화해 취소도 안 된 채 누적됐다.
 *
 * ★검증 방식과 그 한계(정직 고지):
 *   처음엔 Leaflet 생성자 호출 횟수를 세는 행위 테스트를 만들었으나 **공허했다** —
 *   jsdom에서는 Leaflet이 초기화를 끝내지 못해 `mapReady`가 참이 되지 않고, 그래서
 *   오버레이 effect가 아예 실행되지 않는다(카운터 0 vs 0 → 무엇을 바꿔도 통과).
 *   변이 주입으로 그 무력함을 확인하고 폐기했다.
 *   대신 **계약 자체를 소스에서 고정**한다: 문제의 근원은 "deps 배열에 무엇이 들어있는가"
 *   라는 정적 사실이므로, 정적으로 검증하는 것이 오히려 직접적이다.
 *   한계: 런타임 재생성 횟수를 재지는 않는다. 실제 성능 회귀는 브라우저 계측이 필요하다.
 */
import { readFileSync } from "node:fs";

import { __stripCommentsForScan } from "@/lib/source-invariant";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/** ★2026-08-16 — 종전에는 **원시 소스**를 그대로 돌려줬다. 이 파일의 정방향 `toContain`
 *  단언들이 전부 **주석 안 문자열로 충족**됐다(`/* onFeatureClickRef.current?.(feature) *​/`).
 *  이 파일은 메모리상 "배선 미변이로 4회 뚫림(identity churn 포함)" 사례의 그 파일이다 —
 *  **처방이 공용화됐는데 정작 환자에게 오지 않았다.** 공용 스트리퍼를 경유한다. */
function readSource(rel: string): string {
  return __stripCommentsForScan(readFileSync(resolve(process.cwd(), rel), "utf-8"), rel);
}

describe("identity churn — 오버레이 effect deps 계약", () => {
  it("★onFeatureClick이 deps에 있으면 안 된다(있으면 소비처 인라인 함수가 전량 재생성을 유발)", () => {
    const src = readSource("components/map/SatongMultiMap.tsx");
    // 오버레이 effect의 deps 배열: overlayFeatures와 priceRange가 함께 들어있는 블록.
    const depsBlocks = src
      .split("}, [")
      .slice(1)
      .map((chunk) => chunk.slice(0, chunk.indexOf("]")))
      .filter((deps) => deps.includes("overlayFeatures") && deps.includes("priceRange"));

    expect(depsBlocks.length, "오버레이 effect deps 블록을 찾지 못함").toBeGreaterThan(0);
    for (const deps of depsBlocks) {
      const lines = deps.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("//"));
      expect(lines, "onFeatureClick이 deps에 남아있다").not.toContain("onFeatureClick,");
    }
  });

  it("클릭 핸들러는 ref 경유로 호출된다(stale closure 없이 deps 제외를 가능케 하는 조건)", () => {
    const src = readSource("components/map/SatongMultiMap.tsx");
    // deps에서 뺄 수 있는 근거 = 이벤트 시점에 ref로 최신 값을 읽기 때문.
    expect(src).toContain("onFeatureClickRef.current?.(feature)");
    expect(src).not.toMatch(/on\("click", \(\) => onFeatureClick\?\./);
  });
});

describe("identity churn — 소비처 안정 참조", () => {
  it("★LandScheduleClient는 지도 prop을 인라인으로 넘기지 않는다", () => {
    const src = readSource("components/operations/LandScheduleClient.tsx");
    // 인라인 배열/객체/함수는 렌더마다 새 identity가 되어 경계 POST(45초)를 반복 발화시켰다.
    expect(src).not.toMatch(/selectedParcels=\{rows\.filter/);
    expect(src).not.toMatch(/onFeatureClick=\{\(feat\)/);
    expect(src).not.toMatch(/layerState=\{\{/);
    // 안정 참조로 승격됐는지
    expect(src).toContain("selectedParcels={mapSelectedParcels}");
    expect(src).toContain("layerState={mapLayerState}");
    expect(src).toContain("onFeatureClick={handleMapFeatureClick}");
  });
});

describe("identity churn — 레이어 토글 무변화 시 참조 보존", () => {
  it("★이미 켜진 레이어를 다시 켜도 새 Set을 만들지 않는다", () => {
    const src = readSource("components/precheck/SatongMapShell.tsx");
    // 무조건 new Set을 반환하면 mapLayerState memo가 재계산돼 오버레이·POI가 전량 재생성된다.
    expect(src).toContain("if (prev.has(layerId)) return prev;");
  });
});
