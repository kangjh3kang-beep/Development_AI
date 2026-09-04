/**
 * 비율(%) 표기 회귀락 — 0과 '미확보'를 구분하고, 반올림이 격차를 지우지 않는다.
 *
 * 이 표면의 목적은 "법정 한도는 이런데 실제 적용은 이렇다"를 나란히 보여주는 것이다.
 * 그래서 두 가지가 깨지면 안 된다:
 *  1. 정수 반올림 — 실효 79.6%가 "80%"가 되면 법정 80%와 같아 보여 설명이 사라진다.
 *  2. 0 → "-" — '측정했더니 0'과 '못 구했음'이 같아진다(비율은 0이 유효한 측정값).
 */

import { describe, expect, it } from "vitest";

import { formatPercent } from "@/lib/formatters";

describe("formatPercent", () => {
  it("★법정과 실효의 격차를 반올림으로 지우지 않는다", () => {
    expect(formatPercent(80)).toBe("80.0%");
    expect(formatPercent(79.6)).toBe("79.6%");
    // 정수 반올림이었다면 둘 다 "80%"가 되어 구분이 사라진다.
    expect(formatPercent(80)).not.toBe(formatPercent(79.6));
  });

  it("★0은 유효한 측정값이므로 '미확보'가 아니다", () => {
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatPercent(0)).not.toBe(formatPercent(null));
  });

  it("값이 없으면 '-'가 아니라 '미확보'라고 말한다", () => {
    // "-"는 0으로도 읽히고 '해당없음'으로도 읽힌다. 못 구했다는 뜻을 글자로 적는다.
    expect(formatPercent(null)).toBe("미확보");
    expect(formatPercent(undefined)).toBe("미확보");
    expect(formatPercent(Number.NaN)).toBe("미확보");
  });

  it("★다필지 면적가중 실효치의 원시 float가 화면에 새지 않는다", () => {
    // 나눗셈 결과가 그대로 렌더되면 152.83333333333334% 같은 값이 찍힌다.
    expect(formatPercent(152.83333333333334)).toBe("152.8%");
  });

  it("자릿수는 호출부가 정할 수 있다(기본 1자리)", () => {
    expect(formatPercent(79.66, 2)).toBe("79.66%");
    expect(formatPercent(79.66, 0)).toBe("80%");
  });
});

describe("표기 정합 — 같은 카드 안에서 자릿수가 갈리지 않는다", () => {
  it("★법정 상한과 실효치가 같은 자릿수로 나란히 읽힌다", () => {
    // R1 지적: §1은 포매터를 타는데 §1-B의 상한(capFar)·구조상한은 raw라, 비교의 짝이 갈렸다.
    // "법정 200%인데 실효 79.6%" 서사는 두 값이 같은 표기일 때만 성립한다.
    const 법정 = formatPercent(200);
    const 실효 = formatPercent(79.6);
    const 구조상한 = formatPercent(80);
    expect(법정).toBe("200.0%");
    expect(실효).toBe("79.6%");
    expect(구조상한).toBe("80.0%");
    // 셋 다 소수 1자리 — 자릿수 발산 없음.
    for (const v of [법정, 실효, 구조상한]) {
      expect(v).toMatch(/^\d+\.\d%$/);
    }
  });
});
