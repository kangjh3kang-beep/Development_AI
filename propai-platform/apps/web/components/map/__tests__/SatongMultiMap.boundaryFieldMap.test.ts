/**
 * ★경계 응답 → 런타임 필드 **매핑 락**(2026-08-23).
 *
 * `boundaryFeatureToMapFeature` 는 **서버 값이 화면으로 들어오는 유일한 문**이다. 그런데 변이로
 * 확인하니 이 매핑은 **아무 테스트도 태우지 않았다** — 필드 줄을 지워도 전부 초록이었다.
 * 한 줄이 빠지면 그 값은 화면에 **영영 안 온다**(백엔드는 정상, 테스트는 초록, 사용자만 못 본다).
 *
 * 그래서 새로 추가한 필드만이 아니라 **규제 요약이 쓰는 필드 전부**를 여기서 잠근다.
 */
import { describe, expect, it } from "vitest";

import { boundaryFeatureToMapFeature } from "@/components/map/SatongMultiMap";

/** 라이브 실측 형상(성내리 산 7-2) — 보전관리, 실효 60 / 법정 80 / 근거=조례. */
const SERVER = {
  pnu: "4315031022200070002",
  address: "충청북도 제천시 금성면 성내리 산 7-2",
  input_address: "충청북도 제천시 금성면 성내리 산 7-2",
  area_sqm: 423,
  zone_type: "보전관리지역",
  jimok: "임야",
  official_price_per_sqm: 2410,
  effective_far_pct: 60,
  effective_bcr_pct: 20,
  legal_far_pct: 80,
  far_basis: "조례 적용값(지자체 도시계획조례 적용값(법제처API))",
  current_far_pct: null,
  age_status: "no_building",
} as never;

describe("경계 응답 필드 매핑 — 한 줄이 빠지면 값이 화면에 영영 안 온다", () => {
  it("규제 요약이 쓰는 필드가 전부 런타임 이름으로 넘어온다", () => {
    const f = boundaryFeatureToMapFeature(SERVER);

    // 공허 진리 가드 — 변환 자체가 됐는지 먼저 본다.
    expect(f.pnu).toBe("4315031022200070002");

    expect(f.effectiveFarPct).toBe(60);
    expect(f.effectiveBcrPct).toBe(20);
    // ★신규 — 실효값이 "왜 그 값인지"를 말할 재료.
    expect(f.legalFarPct).toBe(80);
    expect(f.farBasis).toBe("조례 적용값(지자체 도시계획조례 적용값(법제처API))");
    // 종전에도 무잠금이었던 이웃 필드들도 함께 잠근다(같은 문을 통과한다).
    expect(f.areaSqm).toBe(423);
    expect(f.zoneType).toBe("보전관리지역");
    expect(f.officialPricePerSqm).toBe(2410);
    expect(f.ageStatus).toBe("no_building");
  });

  it("★무목업 — 서버가 안 준 값은 `null` 이다(0 이나 임의값으로 채우지 않는다)", () => {
    const f = boundaryFeatureToMapFeature({
      pnu: "1", address: "a",
    } as never);

    expect(f.effectiveFarPct).toBeNull();
    expect(f.legalFarPct).toBeNull();
    expect(f.farBasis).toBeNull();
    expect(f.currentFarPct).toBeNull();
    // ★0 이 아니다 — 0 은 "용적률 0%"라는 거짓 사실이 된다.
    expect(f.effectiveFarPct).not.toBe(0);
  });
});
