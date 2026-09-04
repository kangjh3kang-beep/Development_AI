/**
 * 보류 사유 어휘 락 — **소비자가 침묵하지 않는다**.
 *
 * ★종전 결함(2026-09-04 실측): 화면이 자기 3종 목록으로 `_absent` 를 해석해, 생산자가 내는
 *   `insufficient_coverage` 가 `"—"` 로 떨어져 **사유가 소실**됐다. 목록은 곧 상한이 된다.
 *
 * ★어휘가 백엔드와 **같은지**는 여기서 재지 않는다 — 그건 파이썬이 이 파일을 읽어 대조한다
 *   (`apps/api/tests/test_absent_reason_consumer_coverage.py`). **한 계약을 두 곳에서 잠그면
 *   둘이 갈릴 때 어느 쪽이 정본인지 알 수 없다.** 여기서는 **행위**만 잠근다.
 */
import { describe, expect, it } from "vitest";

import {
  ABSENT_CODES,
  ABSENT_REASONS,
  ABSENT_SHORT,
  isAbsentCode,
  resolveAbsentLabel,
} from "../absent-reasons";

describe("resolveAbsentLabel — 어휘 안의 코드에는 **반드시** 이름이 있다", () => {
  it("★파생형 전수 — 닫힌 어휘의 모든 코드가 긴 문구·짧은 라벨 둘 다 갖는다", () => {
    // ★공허 진리 방지: 어휘가 비면 아래 forEach 가 0회 돌고 «위반 0» 으로 통과한다.
    expect(ABSENT_CODES.length).toBeGreaterThanOrEqual(7);
    for (const code of ABSENT_CODES) {
      expect(resolveAbsentLabel(code), `긴 문구 누락: ${code}`).toBeTruthy();
      expect(resolveAbsentLabel(code, { variant: "short" }), `짧은 라벨 누락: ${code}`).toBeTruthy();
      // ★raw 코드를 문구로 되돌려 주면 «이름을 붙였다» 가 거짓이 된다.
      expect(resolveAbsentLabel(code)).not.toBe(code);
      expect(resolveAbsentLabel(code, { variant: "short" })).not.toBe(code);
    }
  });

  it("★부분 덮어쓰기가 나머지를 침묵시키지 않는다 — 종전 결함을 되살리는 변이", () => {
    // 실거래 단가 열이 실제로 갖고 있던 부분 목록(3종). 생산자는 insufficient_coverage 도 낸다.
    const partial = { not_applicable: "해당없음", masked_by_source: "원천미제공" } as const;
    expect(resolveAbsentLabel("not_applicable", { overrides: partial, variant: "short" })).toBe("해당없음");
    // ★덮지 않은 코드가 **공용 어휘로 떨어진다** — 종전에는 여기가 `"—"` 였다.
    expect(resolveAbsentLabel("insufficient_coverage", { overrides: partial, variant: "short" }))
      .toBe(ABSENT_SHORT.insufficient_coverage);
    expect(resolveAbsentLabel("insufficient_coverage", { overrides: partial, variant: "short" }))
      .not.toBeNull();
  });

  it("★음성 대조군 — 어휘 밖·빈 값은 `null` 이다(모르는 것을 지어내지 않는다)", () => {
    // 이것이 없으면 «항상 뭔가 말한다» 는 구현도 만점을 받는다(위양성도 결함이다).
    expect(resolveAbsentLabel("zzz_not_in_vocabulary")).toBeNull();
    expect(resolveAbsentLabel("")).toBeNull();
    expect(resolveAbsentLabel(null)).toBeNull();
    expect(resolveAbsentLabel(undefined)).toBeNull();
    expect(resolveAbsentLabel(42)).toBeNull();
  });

  it("긴 문구와 짧은 라벨은 **다른 축**이다(한 벌로 뭉치면 표가 무너지거나 칩이 뜻을 못 전한다)", () => {
    for (const code of ABSENT_CODES) {
      expect(ABSENT_REASONS[code]).not.toBe(ABSENT_SHORT[code]);
      expect(ABSENT_SHORT[code].length).toBeLessThan(ABSENT_REASONS[code].length);
    }
  });

  it("isAbsentCode 는 런타임 JSON 을 신뢰하지 않는다", () => {
    expect(isAbsentCode("ambiguous")).toBe(true);
    expect(isAbsentCode("Ambiguous")).toBe(false);
    expect(isAbsentCode({ toString: () => "ambiguous" })).toBe(false);
  });
});
