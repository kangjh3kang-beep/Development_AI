/**
 * 종합 리스크 배지 — **미지 등급을 안전색으로 낮추지 않는다.**
 *
 * ★배경(실측 2026-08-27 · origin/main 5a79f510): 백엔드 사다리
 * `protection_zone_severity.SEVERITY_ORDER` 는 5종인데 화면 표는 4종이라
 * `"중간"`(제한보호구역)이 빠져 있었고, 폴백이 `RISK_LEVEL_STYLE["낮음"]` =
 * `--status-success`(초록)였다. → **중간 위험이 낮음과 똑같은 초록**으로 보였다.
 *
 * ★이 파일은 **판정**만 잠근다. 사다리↔표 **정합**은 백엔드 파생형 락
 * `apps/api/tests/test_risk_level_label_parity.py` 가 잠근다(오라클이 파이썬 SSOT 라
 * 프론트에서 동어반복이 되지 않게 일부러 나눴다).
 */

import { describe, expect, it } from "vitest";

import {
  RISK_LEVEL_STYLE,
  riskLevelStyle,
} from "../ComprehensiveAnalysisPanel";

describe("riskLevelStyle — 미지 등급 폴백", () => {
  it("★두 모집단이 갈린다 — 알려진 등급과 미지 등급이 같은 색이면 안 된다", () => {
    const known = riskLevelStyle("낮음");
    const unknown = riskLevelStyle("존재하지_않는_등급");

    // 공허한 참 방지: 둘 다 빈 문자열이면 아래 부등호가 무의미하다.
    expect(known.length).toBeGreaterThan(0);
    expect(unknown.length).toBeGreaterThan(0);

    expect(unknown).not.toBe(known);
  });

  it("미지 등급은 **안전색(success)** 을 쓰지 않는다", () => {
    const unknown = riskLevelStyle("존재하지_않는_등급");
    expect(unknown).not.toContain("--status-success");
    // 음성 단언만 두면 폴백을 빈 문자열로 바꿔도 통과한다 → 실제 값도 못 박는다.
    expect(unknown).toContain("--text-tertiary");
  });

  it("★결함을 만든 등급 — '중간'은 '낮음'과 다른 색이다", () => {
    const mid = riskLevelStyle("중간");
    expect(mid.length).toBeGreaterThan(0);
    expect(mid).not.toBe(riskLevelStyle("낮음"));
    // 미지값 폴백으로 떨어진 것도 아니어야 한다(표에 실제로 들어 있어야 한다).
    expect(mid).not.toBe(riskLevelStyle("존재하지_않는_등급"));
  });

  it("사다리 5종이 **서로 다른** 색을 갖는다(두 등급이 한 색이면 구별 불가)", () => {
    const grades = ["낮음", "보통", "중간", "높음", "극히 높음"];
    const styles = grades.map((g) => riskLevelStyle(g));
    expect(new Set(styles).size).toBe(grades.length);
    // 어느 하나라도 미지 폴백으로 떨어지면 위 단언이 통과할 수도 있으므로 따로 막는다.
    const fallback = riskLevelStyle("존재하지_않는_등급");
    for (const [i, s] of styles.entries()) {
      expect(s, `${grades[i]} 가 표에 없어 폴백으로 떨어졌다`).not.toBe(fallback);
    }
  });

  it("null/undefined/공백도 안전색으로 떨어지지 않는다", () => {
    for (const v of [null, undefined, "", "   "]) {
      expect(riskLevelStyle(v)).not.toContain("--status-success");
    }
  });

  it("표는 값이 아니라 **키**가 계약이다 — 키 집합을 노출한다", () => {
    // 파생형 락(백엔드)이 이 export 를 읽는 것은 아니지만, 표가 모듈 밖에서
    // 조회 가능해야 다음 사람이 색을 손으로 베끼지 않는다.
    expect(Object.keys(RISK_LEVEL_STYLE)).toContain("중간");
  });

  // ★부채 — 초록 안에 보이게 남긴다(커밋 메시지에만 적으면 드러나지 않는다).
  //   배지가 화면에 실제로 붙는 것까지는 이 파일이 잠그지 않는다. 배지는
  //   `devPlans` 조건부 렌더 안이라 상태를 만들어야 하고, 그 목 구성 비용이
  //   이 PR 범위를 넘는다. 현재 배선은 백엔드 락의 소스 검사(배지 렌더 줄이
  //   riskLevelStyle 을 태우는가)로만 잠겨 있다.
  it.todo(
    "렌더 락: devPlans.risk_level='중간' 상태를 만들어 배지 클래스에 amber 가 붙는지",
  );
});
