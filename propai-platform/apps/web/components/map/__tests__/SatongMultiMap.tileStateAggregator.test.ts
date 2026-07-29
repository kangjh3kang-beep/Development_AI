/**
 * 타일 실패 판정 — '배경지도가 실제로 안 보이는가'를 비율로 판정한다.
 *
 * ★실결함(라이브 실측 2026-07-30): 종전엔 타일 이벤트마다 상태를 그대로 덮어써
 *   마지막 이벤트가 승리했다. 그 결과 뷰포트 **36개 중 1개**만 실패해도
 *   "기본지도(VWorld) 타일 로드 실패 — 배경지도만 미표시입니다" 배너가 실제로 노출됐다
 *   (458×88px 가시 확인). 지도는 35개가 정상 렌더되고 있었는데도 사용자에겐 장애로 보였다.
 *   개별 타일 실패는 흔하다(빈 영역·일시 타임아웃) — 판정은 비율이어야 한다.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { makeTileStateAggregator } from "@/components/map/SatongMultiMap";

function run(sequence: boolean[], opts?: { minSamples?: number; failureRatio?: number }) {
  const states: string[] = [];
  const track = makeTileStateAggregator((s) => states.push(s), opts);
  sequence.forEach(track);
  return { states, last: states[states.length - 1] };
}

describe("타일 상태 집계", () => {
  it("★라이브 재현: 36개 중 1개 실패는 정상으로 판정한다(배너 미노출)", () => {
    const seq = Array.from({ length: 36 }, (_, i) => i !== 17); // 1개만 실패
    expect(run(seq).last).toBe("ready");
  });

  it("전부 실패하면 실패로 판정한다(진짜 배경지도 미표시)", () => {
    expect(run(Array.from({ length: 12 }, () => false)).last).toBe("error");
  });

  it("절반 이상 실패하면 실패로 판정한다", () => {
    const seq = [...Array.from({ length: 4 }, () => true), ...Array.from({ length: 8 }, () => false)];
    expect(run(seq).last).toBe("error");
  });

  it("성공이 다수면 실패가 섞여도 정상이다", () => {
    const seq = [...Array.from({ length: 20 }, () => true), false, false, false];
    expect(run(seq).last).toBe("ready");
  });

  it("표본이 적어도 성공이 하나라도 있으면 정상으로 본다(초기 깜빡임 방지)", () => {
    expect(run([false, true]).last).toBe("ready");
  });

  it("표본이 적고 전부 실패면 즉시 실패를 알린다(진짜 장애를 늦추지 않는다)", () => {
    expect(run([false]).last).toBe("error");
    expect(run([false, false]).last).toBe("error");
  });

  it("실패 후 회복되면 정상으로 돌아온다", () => {
    const seq = [...Array.from({ length: 8 }, () => false), ...Array.from({ length: 20 }, () => true)];
    expect(run(seq).last).toBe("ready");
  });

  it("임계치는 조정 가능하다", () => {
    const seq = [...Array.from({ length: 7 }, () => true), ...Array.from({ length: 3 }, () => false)];
    expect(run(seq).last).toBe("ready");                            // 기본 50%
    expect(run(seq, { failureRatio: 0.2 }).last).toBe("error");     // 20%면 실패
  });

  it("호출마다 상태를 통지한다(소비처가 최신값을 받는다)", () => {
    const onState = vi.fn();
    const track = makeTileStateAggregator(onState);
    track(true); track(false); track(true);
    expect(onState).toHaveBeenCalledTimes(3);
  });
});

describe("배선 — 타일 이벤트가 집계기를 반드시 거친다", () => {
  it("★onTileState를 이벤트에서 직접 호출하는 곳이 없다", () => {
    // 순수함수만 고정하면 '집계기를 우회해 이벤트마다 직접 세팅'하는 회귀를 못 잡는다
    // (변이 실증: 배선을 되돌려도 위 9건이 전부 초록이었다). 원 결함이 바로 그 형태였다.
    const src = readFileSync(
      resolve(process.cwd(), "components/map/SatongMultiMap.tsx"),
      "utf-8",
    );
    // 베이스맵 타일만 대상 — WMS 오버레이(지적편집도·규제·지적)는 각자의 노트 콜백을
    // 쓰는 게 정상이므로 제외한다(과도한 불변식은 정상 코드를 깨뜨린다).
    const baseHandlers = src
      .split("\n")
      .filter((l) => /^\s*(base|vworld)\.on\("tile(load|error)"/.test(l));
    expect(baseHandlers.length, "베이스맵 타일 핸들러를 찾지 못함").toBeGreaterThanOrEqual(4);
    for (const line of baseHandlers) {
      expect(line, `집계기 우회: ${line.trim().slice(0, 70)}`).toContain("track(");
      expect(line).not.toMatch(/onTileState\(/);
    }
  });
});
