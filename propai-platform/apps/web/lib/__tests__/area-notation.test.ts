import { describe, it, expect } from "vitest";
import {
  EXCLUSIVE_TO_PYEONGHYEONG,
  PYEONG_SQM,
  formatAreaDual,
  formatExclusive,
  formatPyeonghyeong,
  toPyeonghyeong,
} from "../area-notation";

describe("면적 표기 SSOT — 전용은 ㎡, 공급은 평형", () => {
  /**
   * ★사용자가 지정한 계약. 이 셋이 이 표의 존재 이유다.
   * 역산 전용률이 71.4 / 74.6 / 74.7% 로 **일정하지 않으므로 공식으로는 못 만든다.**
   */
  it("★사용자 지정 대응을 만족한다 (59→25 · 74→30 · 84→34)", () => {
    for (const [sqm, pyeong] of [[59, 25], [74, 30], [84, 34]] as const) {
      const r = toPyeonghyeong(sqm);
      expect(r, `전용 ${sqm}㎡ 가 매칭 안 됨`).toBeTruthy();
      expect(r!.pyeong, `전용 ${sqm}㎡ → ${pyeong}평형이어야 한다`).toBe(pyeong);
      expect(r!.fromAnchor, `전용 ${sqm}㎡ 는 **관례 앵커**여야 한다(폴백 아님)`).toBe(true);
    }
  });

  it("★공식으로 대체할 수 없다 — 역산 전용률이 일정하지 않다", () => {
    // 이 검사가 있어야 «그냥 ÷0.75 하면 되잖아» 로 되돌아가는 것을 막는다
    const ratios = [[59, 25], [74, 30], [84, 34]].map(
      ([sqm, py]) => sqm / (py * PYEONG_SQM));
    const spread = Math.max(...ratios) - Math.min(...ratios);
    expect(spread, `전용률 편차 ${(spread * 100).toFixed(1)}%p — 공식 하나로 덮인다면 이 표는 불필요`)
      .toBeGreaterThan(0.02);
  });

  it("실거래 소수 면적도 앵커에 붙는다 (59.97·84.93)", () => {
    expect(toPyeonghyeong(59.97)?.pyeong).toBe(25);
    expect(toPyeonghyeong(84.93)?.pyeong).toBe(34);
    expect(toPyeonghyeong(59.97)?.fromAnchor).toBe(true);
  });

  it("★앵커 밖은 폴백이고 **폴백이라고 말한다**", () => {
    const off = toPyeonghyeong(200);
    expect(off?.fromAnchor, "앵커에 없는 면적이 앵커로 표기된다").toBe(false);
    expect(formatPyeonghyeong(200)).toContain("약");
    // ★두 모집단 — 앵커는 「약」이 붙지 않는다(지어낸 값과 구별)
    expect(formatPyeonghyeong(84)).not.toContain("약");
    expect(formatPyeonghyeong(84)).toBe("34평형");
  });

  it("★★전용을 평으로, 공급을 ㎡로 쓰지 않는다 — 이번 신고의 원인", () => {
    // 전용은 ㎡ 로만
    expect(formatExclusive(84)).toBe("84㎡");
    expect(formatExclusive(84)).not.toContain("평");
    // 평형은 평형으로만
    expect(formatPyeonghyeong(84)).toBe("34평형");
    expect(formatPyeonghyeong(84)).not.toContain("㎡");
    // 병행 표기는 **어느 쪽이 전용인지 말한다**
    expect(formatAreaDual(84)).toBe("전용 84㎡ (34평형)");
    // ★음성 대조군 — 전용 84 와 공급 84 는 **다른 값**이다(뒤바뀌면 실패)
    expect(toPyeonghyeong(84)!.pyeong).not.toBe(Math.round(84 / PYEONG_SQM));
  });

  it("★쓰레기 입력이 지어낸 값을 내지 않는다", () => {
    for (const bad of [0, -1, NaN, Infinity]) {
      expect(toPyeonghyeong(bad as number), `${bad} 가 값을 냈다`).toBeNull();
    }
    for (const bad of [null, undefined, 0, -5]) {
      expect(formatExclusive(bad as number)).toBe("—");
      expect(formatAreaDual(bad as number)).toBe("—");
    }
  });

  it("★앵커표가 비어 있지 않고 단조 증가한다(공허·역전 방지)", () => {
    expect(EXCLUSIVE_TO_PYEONGHYEONG.length).toBeGreaterThanOrEqual(8);
    for (let i = 1; i < EXCLUSIVE_TO_PYEONGHYEONG.length; i++) {
      const [pSqm, pPy] = EXCLUSIVE_TO_PYEONGHYEONG[i - 1];
      const [cSqm, cPy] = EXCLUSIVE_TO_PYEONGHYEONG[i];
      expect(cSqm, `앵커표 면적이 역전됐다: ${pSqm} → ${cSqm}`).toBeGreaterThan(pSqm);
      expect(cPy, `앵커표 평형이 역전됐다: ${pPy} → ${cPy}`).toBeGreaterThan(pPy);
    }
  });

  it("★평당 상수를 새로 만들지 않는다 — formatters 정본을 쓴다", async () => {
    const f = await import("../formatters");
    expect(PYEONG_SQM).toBe(f.PYEONG_SQM);
    const fs = await import("node:fs");
    const path = await import("node:path");
    const src = fs.readFileSync(path.resolve(__dirname, "../area-notation.ts"), "utf8");
    const code = src.split("\n").map((l) => l.replace(/\/\/.*$/, "")).join("\n")
      .replace(/\/\*[\s\S]*?\*\//g, "");
    expect(/\b3\.30[0-9]*\b/.test(code), "이 모듈이 평당 상수를 **자기가** 갖고 있다").toBe(false);
  });
});
