/**
 * VWorld 타일 회로차단기 — 상태 전이 계약.
 *
 * ★실장애 배경: 웹서버 인증키가 무효인 채 방치되자 팬/줌마다 타일 수십 개가 전부 실패했고,
 *   오류에 no-store가 붙어 캐시도 안 되고 서버 억제도 없어 실패 요청이 무한 반복됐다.
 *   그 결과 VWorld가 서버 IP를 차단해(도메인 전체 502) 키를 고쳐도 지도가 복구되지 않았다.
 *   이 파일은 "상류가 죽으면 두드림을 멈춘다"는 계약을 고정한다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  BREAKER_TUNING,
  breakerState,
  cooldownRemainingSec,
  recordFailure,
  recordSuccess,
  resetBreakers,
  shouldAttempt,
} from "@/lib/vworld-circuit-breaker";

const KEY = "test-upstream";
const { FAILURE_THRESHOLD, COOLDOWN_MS } = BREAKER_TUNING;

beforeEach(() => resetBreakers());

describe("회로차단기 상태 전이", () => {
  it("초기에는 닫혀 있고 호출을 허용한다", () => {
    expect(breakerState(KEY)).toBe("closed");
    expect(shouldAttempt(KEY)).toBe(true);
  });

  it("단발 실패로는 차단하지 않는다(일시 오류 오버리액션 방지)", () => {
    for (let i = 0; i < FAILURE_THRESHOLD - 1; i += 1) recordFailure(KEY);
    expect(breakerState(KEY)).toBe("closed");
    expect(shouldAttempt(KEY)).toBe(true);
  });

  it("★연속 실패가 임계치에 닿으면 열려서 상류 호출을 멈춘다", () => {
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure(KEY);
    expect(breakerState(KEY)).toBe("open");
    expect(shouldAttempt(KEY)).toBe(false);
    // 폭주 상황 재현 — 열린 동안은 몇 번을 호출해도 상류로 나가지 않는다.
    for (let i = 0; i < 50; i += 1) expect(shouldAttempt(KEY)).toBe(false);
  });

  it("성공하면 즉시 닫히고 실패 카운트가 초기화된다", () => {
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure(KEY);
    recordSuccess(KEY);
    expect(breakerState(KEY)).toBe("closed");
    expect(shouldAttempt(KEY)).toBe(true);
  });

  it("쿨다운이 끝나면 딱 1건만 탐색으로 흘린다(half-open)", () => {
    const t0 = 1_000_000;
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure(KEY, t0);
    const after = t0 + COOLDOWN_MS + 1;
    expect(breakerState(KEY, after)).toBe("half-open");
    expect(shouldAttempt(KEY, after)).toBe(true);   // 탐색 1건 통과
    expect(shouldAttempt(KEY, after)).toBe(false);  // 나머지는 계속 차단
  });

  it("탐색이 실패하면 쿨다운을 다시 시작한다(회복 안 됨)", () => {
    const t0 = 1_000_000;
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure(KEY, t0);
    const after = t0 + COOLDOWN_MS + 1;
    shouldAttempt(KEY, after);          // 탐색 진입
    recordFailure(KEY, after);          // 탐색 실패
    expect(breakerState(KEY, after + 1)).toBe("open");
    expect(shouldAttempt(KEY, after + 1)).toBe(false);
  });

  it("탐색이 성공하면 완전히 닫힌다", () => {
    const t0 = 1_000_000;
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure(KEY, t0);
    const after = t0 + COOLDOWN_MS + 1;
    shouldAttempt(KEY, after);
    recordSuccess(KEY);
    expect(breakerState(KEY, after + 1)).toBe("closed");
    expect(shouldAttempt(KEY, after + 1)).toBe(true);
  });

  it("남은 쿨다운을 초 단위로 알려준다(사용자 안내용)", () => {
    const t0 = 1_000_000;
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure(KEY, t0);
    expect(cooldownRemainingSec(KEY, t0)).toBe(COOLDOWN_MS / 1000);
    expect(cooldownRemainingSec(KEY, t0 + COOLDOWN_MS)).toBe(0);
  });

  it("키가 다르면 서로 간섭하지 않는다(WMS 장애가 WMTS를 막지 않음)", () => {
    for (let i = 0; i < FAILURE_THRESHOLD; i += 1) recordFailure("wms");
    expect(shouldAttempt("wms")).toBe(false);
    expect(shouldAttempt("wmts")).toBe(true);
  });
});
