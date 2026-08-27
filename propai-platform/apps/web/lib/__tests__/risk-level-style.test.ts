/**
 * 종합 리스크 배지 — **미지 등급을 안전색으로 낮추지 않는다.**
 *
 * ★배경(실측 2026-08-27): 백엔드 사다리 `SEVERITY_ORDER` 5종 vs 화면 표 4종
 * (`중간` 누락) + 폴백이 `낮음`(초록)이라, 배지 **글자는 `중간` 인데 색은 초록**이었다.
 *
 * ★이 파일은 **판정**만 잠근다. 사다리↔표 **정합**과 **톤 구별성**은 백엔드 파생형 락
 * `apps/api/tests/test_risk_level_label_parity.py` 가 잠근다(오라클이 파이썬 SSOT 라
 * 프론트에서 동어반복이 되지 않게 일부러 나눴다).
 */

import { describe, expect, it } from "vitest";

import {
  allRiskTones,
  RISK_LEVEL_TONE,
  riskLevelStyle,
  riskLevelTextClass,
  riskToneClass,
  riskToneTextClass,
} from "../risk-level-style";

const LADDER = ["낮음", "보통", "중간", "높음", "극히 높음"] as const;
const UNKNOWN = "존재하지_않는_등급";

describe("riskLevelStyle — 미지 등급 폴백", () => {
  it("★두 모집단이 갈린다 — 알려진 등급과 미지 등급이 같은 색이면 안 된다", () => {
    const known = riskLevelStyle("낮음");
    const unknown = riskLevelStyle(UNKNOWN);
    // 공허한 참 방지: 둘 다 빈 문자열이면 아래 부등호가 무의미하다.
    expect(known.length).toBeGreaterThan(0);
    expect(unknown.length).toBeGreaterThan(0);
    expect(unknown).not.toBe(known);
  });

  it("미지 등급은 **안전색(success)** 을 쓰지 않는다", () => {
    const unknown = riskLevelStyle(UNKNOWN);
    expect(unknown).not.toContain("--status-success");
    // 음성 단언만 두면 폴백을 빈 문자열로 바꿔도 통과한다 → 실제 값도 못 박는다.
    expect(unknown).toContain("--text-tertiary");
  });

  it("사다리 5종이 **서로 다른 색**이고, 어느 것도 폴백으로 안 떨어진다", () => {
    const styles = LADDER.map((g) => riskLevelStyle(g));
    expect(new Set(styles).size).toBe(LADDER.length);
    const fallback = riskLevelStyle(UNKNOWN);
    for (const [i, s] of styles.entries()) {
      expect(s, `${LADDER[i]} 가 표에 없어 폴백으로 떨어졌다`).not.toBe(fallback);
    }
  });

  it("★결함을 만든 등급 — '중간'은 '낮음'·'보통'과 모두 다르다", () => {
    // 종전 배치는 '중간'과 '보통'이 **같은 색**이었다(oklab Δ 0.0000).
    expect(riskLevelStyle("중간")).not.toBe(riskLevelStyle("낮음"));
    expect(riskLevelStyle("중간")).not.toBe(riskLevelStyle("보통"));
  });
});

describe("riskLevelStyle — 입력 위생", () => {
  it("★두 모집단: 공백이 붙은 **실재 등급**은 살고, 공백뿐인 값은 폴백이다", () => {
    // 이 두 줄이 갈려야 `.trim()` 이 잠긴다. 종전엔 `"   "` 케이스만 있어
    // trim 이 있으나 없으나 결과가 같았다 — **원리적으로 판별 불가**였다(적대 리뷰 M-A).
    expect(riskLevelStyle("  중간  ")).toBe(riskLevelStyle("중간"));
    expect(riskLevelStyle("   ")).toBe(riskLevelStyle(UNKNOWN));
  });

  it("★문자열이 아닌 값에 던지지 않는다 — 소비처가 무타입이다", () => {
    // `result?.development_plans || {}` 라 risk_level 이 any 다. 종전 `표[x]` 는
    // 무엇이 와도 안 던졌는데, 가드 없는 `x.trim()` 은 TypeError → 렌더 폭발이었다.
    for (const v of [null, undefined, 3, {}, [], true]) {
      expect(() => riskLevelStyle(v)).not.toThrow();
      expect(riskLevelStyle(v)).not.toContain("--status-success");
    }
  });
});

describe("톤 팔레트", () => {
  it("등급마다 **서로 다른 톤 이름**을 쓴다", () => {
    const tones = LADDER.map((g) => RISK_LEVEL_TONE[g]);
    expect(tones.every(Boolean)).toBe(true);
    expect(new Set(tones).size).toBe(LADDER.length);
  });

  it("★글자색 축도 5등급이 서로 다르다 — 배너가 이 축을 쓴다", () => {
    // 배너는 단색 하나만 필요해 배지와 **다른 축**(text-only)을 쓴다.
    // 축이 둘이면 각각 잠가야 한다 — 한쪽만 잠그면 나머지가 무제한이다.
    const texts = LADDER.map((g) => riskLevelTextClass(g));
    expect(new Set(texts).size).toBe(LADDER.length);
    const fb = riskLevelTextClass(UNKNOWN);
    for (const [i, t] of texts.entries()) {
      expect(t, `${LADDER[i]} 가 폴백으로 떨어졌다`).not.toBe(fb);
    }
    expect(fb).not.toContain("--status-success");
  });

  it("모든 톤이 배경축·글자축 **양쪽**에 정의돼 있다", () => {
    for (const t of allRiskTones()) {
      expect(riskToneClass(t).length, `${t} 배경축 누락`).toBeGreaterThan(0);
      expect(riskToneTextClass(t).length, `${t} 글자축 누락`).toBeGreaterThan(0);
    }
  });

  it("톤 이름이 다르면 **클래스 문자열도 다르다**(이름만 다른 같은 색 금지)", () => {
    const all = allRiskTones();
    expect(all.length).toBeGreaterThanOrEqual(6); // 5등급 + 중립
    const classes = all.map((t) => riskToneClass(t));
    expect(new Set(classes).size).toBe(all.length);
  });
});
