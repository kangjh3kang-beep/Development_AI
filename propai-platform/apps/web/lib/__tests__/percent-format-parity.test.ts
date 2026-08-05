/**
 * 비율 표기 계약 — 0과 '미확보'를 같은 기호로 쓰지 않고, 원시 float를 화면에 흘리지 않는다.
 *
 * ★왜 이 파일이 있나(2026-08-03 R2 적대검증 H-1·H-2):
 *   #530이 §1 비율에 포매터를 도입했는데 **같은 카드 안의 §1-B는 원시 보간**이라
 *   `152.8%` 바로 아래에 `152.83333333333334%` 가 함께 떴다. 시나리오 표에서는
 *   기부체납 `0%`(안 냄)와 미확보가 똑같이 `"-"` 였고, 값이 없으면 `"%"`·`"+%"` 라는
 *   깨진 문자열이 나왔다.
 *
 *   비교 짝이 갈리면 사용자는 어느 쪽을 믿을지 알 수 없고, 0과 미확보가 같은 기호면
 *   '측정했더니 0'과 '못 구했음'이 구분되지 않는다.
 */
import { describe, it, expect } from "vitest";
import { formatPercent, formatPercentDelta, formatPercentPoint, formatPercentRange } from "@/lib/formatters";

describe("formatPercentDelta — 증감 비율", () => {
  it("값이 없으면 '미확보' — '+%' 같은 깨진 표기를 만들지 않는다", () => {
    expect(formatPercentDelta(null)).toBe("미확보");
    expect(formatPercentDelta(undefined)).toBe("미확보");
    expect(formatPercentDelta(Number.NaN)).toBe("미확보");
    expect(formatPercentDelta(null)).not.toContain("%");
  });

  it("0은 유효값 — 부호 없이 0.0%", () => {
    expect(formatPercentDelta(0)).toBe("0.0%");
  });

  it("양수에만 + 를 붙이고 소수 1자리로 고정한다", () => {
    expect(formatPercentDelta(20)).toBe("+20.0%");
    expect(formatPercentDelta(-5.25)).toBe("-5.3%");
  });

  it("★0과 미확보가 같은 표기가 되지 않는다", () => {
    expect(formatPercentDelta(0)).not.toBe(formatPercentDelta(null));
  });

  it("원시 float가 그대로 새지 않는다", () => {
    expect(formatPercentDelta(152.83333333333334)).toBe("+152.8%");
  });
});

describe("formatPercentRange — 비율 구간", () => {
  it("한쪽이라도 없으면 구간이 성립하지 않는다 — '~%' 금지", () => {
    expect(formatPercentRange(null, 300)).toBe("미확보");
    expect(formatPercentRange(200, null)).toBe("미확보");
    expect(formatPercentRange(null, null)).not.toContain("~");
  });

  it("두 끝의 자릿수가 같아 눈으로 견줄 수 있다", () => {
    expect(formatPercentRange(200, 249.99999)).toBe("200.0~250.0%");
  });

  it("0 하한은 유효값이다", () => {
    expect(formatPercentRange(0, 100)).toBe("0.0~100.0%");
  });
});

describe("formatPercent — 기존 계약 무회귀", () => {
  it("0은 0.0%, 없으면 미확보", () => {
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatPercent(null)).toBe("미확보");
  });

  it("★정수 반올림 금지 — 79.6이 법정 80과 같아 보이면 안 된다", () => {
    expect(formatPercent(79.6)).toBe("79.6%");
    expect(formatPercent(79.6)).not.toBe(formatPercent(80));
  });
});

describe("formatPercentPoint — 퍼센트 포인트(비율끼리의 차이)", () => {
  it("단위가 %가 아니라 %p — 섞으면 초과분이 절반으로 읽힌다", () => {
    expect(formatPercentPoint(60)).toBe("60.0%p");
    expect(formatPercentPoint(60)).not.toBe(formatPercent(60));
  });

  it("정수 반올림 금지 — 0.6%p 초과가 '1%p'가 되면 안 된다", () => {
    expect(formatPercentPoint(0.6)).toBe("0.6%p");
  });

  it("0은 유효값, 없으면 미확보", () => {
    expect(formatPercentPoint(0)).toBe("0.0%p");
    expect(formatPercentPoint(null)).toBe("미확보");
    expect(formatPercentPoint(0)).not.toBe(formatPercentPoint(null));
  });
});

describe("formatPercentDelta — 부호는 표시값 기준(R3 LOW-1·LOW-2)", () => {
  it("반올림해서 0이 되면 '증가'라고 말하지 않는다", () => {
    expect(formatPercentDelta(0.04)).toBe("0.0%");
    expect(formatPercentDelta(0.04)).not.toContain("+");
  });

  it("음의 0을 만들지 않는다", () => {
    expect(formatPercentDelta(-0.04)).toBe("0.0%");
    expect(formatPercentDelta(-0.04)).not.toContain("-");
  });

  it("실제로 표시될 만큼 커지면 부호가 붙는다", () => {
    expect(formatPercentDelta(0.05)).toBe("+0.1%");
    expect(formatPercentDelta(-0.05)).toBe("-0.1%");
  });
});
