/**
 * ★거짓 "dominant" 를 만들지 않는다 — **값은 그대로, 주장만 사라진다**(2026-08-24).
 *
 * 종전 `selectionToSiteAnalysisPatch` 는 `dominantZoneCode: first.zoneType` 을 썼다.
 * 이름은 "우세(dominant)" 인데 값은 **첫 필지**였고, 실측 사례에서 그 둘은 **반대**였다
 * (자연녹지 4,576㎡·79% vs 보전관리 1,205㎡·21% 인데 보전관리를 표시).
 *
 * ★여기서 진짜 우세를 재계산하지 않는다 — 산식은 서버 하나뿐이고(면적합산 max + 동률·
 *   규제성격 판정), 선택 시점엔 그 판정이 없다. **모른다고 두는 것이 정직하다.**
 *
 * ★그리고 이 변경은 **하류 값을 바꾸지 않는다**: 소비처가 `dominantZoneCode ?? zoneCode` 로
 *   읽으므로 null 이면 `zoneCode`(=대표=first) 로 폴백한다. 그 사실을 아래 C 가 잠근다 —
 *   안 잠그면 "정직해졌지만 설계·수지 값이 바뀌었다"는 회귀를 못 본다.
 */
import { describe, expect, it } from "vitest";

import { selectionToSiteAnalysisPatch } from "@/components/precheck/satong-map-selection";
import { resolveDominantZone } from "@/lib/zoning-ssot";

const P = (address: string, zoneType: string, areaSqm: number) => ({
  id: address, address, source: "map" as const, zoneType, areaSqm, pnu: null,
});

describe("혼재 선택은 우세를 참칭하지 않는다", () => {
  it("★A) 용도지역이 섞이면 `dominantZoneCode` 는 null — 모르는 것을 안다고 하지 않는다", () => {
    const patch = selectionToSiteAnalysisPatch([
      P("충청북도 제천시 금성면 성내리 산 7-1", "보전관리지역", 326),
      P("충청북도 제천시 모산동 123-1", "자연녹지지역", 4576),
    ])!;
    expect(patch.zoneMixed).toBe(true); // 대상 존재 가드
    expect(patch.dominantZoneCode ?? null).toBeNull();
    // 대표값은 그대로 남는다(그건 참이다 — 첫 필지의 용도지역).
    expect(patch.zoneCode).toBe("보전관리지역");
  });

  it("B) 단일 용도지역이면 우세는 그 값이다(참이므로 채운다)", () => {
    const patch = selectionToSiteAnalysisPatch([
      P("충청북도 제천시 금성면 성내리 산 7-1", "보전관리지역", 326),
      P("충청북도 제천시 금성면 성내리 산 7-2", "보전관리지역", 423),
    ])!;
    expect(patch.zoneMixed).toBe(false);
    expect(patch.dominantZoneCode).toBe("보전관리지역");
  });

  it("★C) 무회귀 — 소비처가 읽는 **값은 종전과 같다**(폴백이 대표값을 준다)", () => {
    const patch = selectionToSiteAnalysisPatch([
      P("충청북도 제천시 금성면 성내리 산 7-1", "보전관리지역", 326),
      P("충청북도 제천시 모산동 123-1", "자연녹지지역", 4576),
    ])!;
    // `zoning-ssot.resolveDominantZone` = `dominantZoneCode ?? zoneCode` — 실제 소비 경로를 태운다.
    expect(resolveDominantZone(patch as never)).toBe("보전관리지역");
    // 종전(dominantZoneCode=first)에도 같은 값이었다 → **설계·수지 입력 무변경**.
  });
});
