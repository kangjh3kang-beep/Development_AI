/**
 * ★근거 문구는 거짓이면 **근거 없음보다 나쁘다** — 그 문구를 잠근다(2026-08-24).
 *
 * 종전 문구: "다필지 통합 **우세** 용도지역(dominant)".
 * 그런데 그 값의 출처는 `dominantZoneCode ?? zoneCode` 이고 **둘 다 대표(첫) 필지** 값이었다.
 * 실측 사례에서 그 값은 면적 우세와 **반대**였다(자연녹지 79% vs 보전관리 21% → 보전관리 표시).
 *
 * 근거 트레이스는 사용자가 "근거 보기" 를 눌러 **확인하러 오는 자리**다. 거기서 틀리면
 * 사용자는 틀린 근거를 믿고 판단한다 — 그래서 값보다 먼저 잠근다.
 *
 * ★변이로 확인: 이 문구는 **무잠금**이었다(거짓 문구로 되돌려도 전부 초록).
 */
import { describe, expect, it } from "vitest";

import { buildEvidenceItems } from "@/components/common/ContextHeader";

const base = { zoneLabel: "보전관리지역", landAreaSqm: 5881, parcelCount: 6 } as never;

function zoneBasis(isMulti: boolean): string {
  const items = buildEvidenceItems({ ...(base as object), isMultiParcel: isMulti } as never, null);
  const hit = items.find((i) => i.label === "용도지역");
  expect(hit, "용도지역 근거 항목이 있어야 한다(공허 진리 가드)").toBeTruthy();
  return hit!.basis ?? "";
}

describe("용도지역 근거 문구 — 참인 것만 말한다", () => {
  it("★다필지 근거는 '우세(dominant)' 를 **주장하지 않는다**", () => {
    const basis = zoneBasis(true);
    // ★핵심 — 되돌림 방지. 이 값의 출처는 대표 필지이지 면적 우세가 아니다.
    expect(basis).not.toMatch(/우세 용도지역\(dominant\)/);
    expect(basis).not.toMatch(/통합 우세/);
    // 무엇인지는 말해야 한다(고지 없음도 결함이다).
    expect(basis).toContain("대표(첫) 필지");
    // 진짜 우세를 어디서 보는지도 알려 준다.
    expect(basis).toContain("통합 종합분석");
  });

  it("★위양성 방지 — 단일 필지 근거는 종전 그대로(무회귀)", () => {
    expect(zoneBasis(false)).toBe("부지분석 확정 용도지역");
  });

  it("두 경로의 문구가 실제로 갈린다 — 같으면 위 단언이 잠금이 아니다", () => {
    expect(zoneBasis(true)).not.toBe(zoneBasis(false));
  });
});
